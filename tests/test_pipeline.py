# -*- coding: utf-8 -*-
"""Pipeline completo con scraper e IA simulados (sin red, sin Selenium, sin Gemini)."""

from datetime import datetime

import pytest
import requests

from main import ejecutar_pipeline, describir_resumen
from core.ai_analyst import AnalisisFallido, CuotaAgotada
from core.scraper import LicitacionScraper, DriverNoDisponible
from tests.conftest import FICHA_EJEMPLO

AHORA = datetime(2026, 2, 10, 12, 0)


def _listado(n, prefijo="L", nombre="Reactivos de laboratorio", cierre="2099-01-01T10:00:00", estado=5):
    return [{"CodigoExterno": f"{prefijo}-{i}", "Nombre": nombre, "CodigoEstado": estado, "FechaCierre": cierre}
            for i in range(n)]


class ScraperFalso(LicitacionScraper):
    """Usa el filtrado real, pero simula la API y Selenium."""
    def __init__(self, db, listado=(), fallan=(), driver_roto=False):
        super().__init__(db)
        self.listado, self.fallan, self.driver_roto = list(listado), set(fallan), driver_roto
        self.extraidas = []

    def descubrir_licitaciones_del_dia(self, fecha=None):
        self.error_descubrimiento = None
        return self.listado

    def extraer_detalle_licitacion(self, codigo):
        if self.driver_roto:
            raise DriverNoDisponible("No se pudo iniciar Chrome")
        self.extraidas.append(codigo)
        if codigo in self.fallan:
            return {"link": None, "descripcion_pro": None, "error": "Timeout"}
        return {"link": f"http://mp/{codigo}", "descripcion_pro": FICHA_EJEMPLO, "error": None,
                "titulo": "Suministro de reactivos", "organismo": "HOSPITAL DE PRUEBA",
                "fecha_publicacion": "2026-02-05", "reclamos_pago_n": 181, "region": "Región de los Lagos"}


class AnalistaFalso:
    def __init__(self, db, fallan=(), cuota_en=None):
        self.db, self.fallan, self.cuota_en = db, set(fallan), cuota_en
        self.analizadas = []

    def analizar_licitacion(self, id_ext):
        if id_ext == self.cuota_en:
            raise CuotaAgotada("429")
        if id_ext in self.fallan:
            raise AnalisisFallido("JSON inválido")
        self.analizadas.append(id_ext)
        data = {"score_ia": 8, "veredicto": "ok", "puntos_criticos": [], "riesgos": []}
        self.db.guardar_analisis_ia(id_ext, 8, data)
        return data


def _correr(db, scraper, analista, **kw):
    kw.setdefault("max_procesar", 5)
    kw.setdefault("max_intentos", 3)
    return ejecutar_pipeline(db=db, scraper=scraper, analyst=analista, pausa=0, ahora=AHORA, **kw)


def test_registra_todas_y_procesa_limite_luego_retoma(db_con_perfil):
    db = db_con_perfil
    scraper = ScraperFalso(db, _listado(8))
    analista = AnalistaFalso(db)

    r1 = _correr(db, scraper, analista)
    assert r1["registradas"] == 8 and r1["intentadas"] == 5 and r1["analizadas"] == 5 and r1["en_cola"] == 3
    assert len(db.obtener_licitaciones()) == 8

    r2 = _correr(db, scraper, analista)   # Mismo listado: nada nuevo, retoma pendientes
    assert r2["registradas"] == 0 and r2["analizadas"] == 3 and r2["en_cola"] == 0
    assert len(db.obtener_licitaciones()) == 8
    assert len(set(analista.analizadas)) == 8 and len(analista.analizadas) == 8   # Sin duplicados


def test_limite_cuenta_intentos_no_exitos(db_con_perfil):
    db = db_con_perfil
    listado = _listado(8)
    scraper = ScraperFalso(db, listado, fallan={l["CodigoExterno"] for l in listado})
    r = _correr(db, scraper, AnalistaFalso(db))
    assert r["intentadas"] == 5 and r["fallidas"] == 5 and len(scraper.extraidas) == 5


def test_fallos_repetidos_pasan_a_error_y_son_visibles(db_con_perfil):
    db = db_con_perfil
    scraper = ScraperFalso(db, _listado(1), fallan={"L-0"})
    for _ in range(3):
        _correr(db, scraper, AnalistaFalso(db))
    fila = db.obtener_licitacion("L-0")
    assert fila["estado"] == "error" and fila["intentos"] == 3 and "Timeout" in fila["ultimo_error"]
    r = _correr(db, scraper, AnalistaFalso(db))
    assert r["intentadas"] == 0                       # Ya no se reintenta solo
    db.reintentar("L-0")
    assert db.obtener_licitacion("L-0")["estado"] == "pendiente"


def test_fallo_ia_no_repite_extraccion(db_con_perfil):
    db = db_con_perfil
    scraper = ScraperFalso(db, _listado(1))
    _correr(db, scraper, AnalistaFalso(db, fallan={"L-0"}))
    fila = db.obtener_licitacion("L-0")
    assert fila["estado"] == "extraido" and fila["intentos"] == 1
    assert fila["titulo"] == "Reactivos de laboratorio" or fila["titulo"] == "Suministro de reactivos"
    _correr(db, scraper, AnalistaFalso(db))
    assert scraper.extraidas == ["L-0"]               # Selenium solo una vez
    assert db.obtener_licitacion("L-0")["estado"] == "analizado"


def test_extraccion_guarda_metadatos_de_la_fuente(db_con_perfil):
    db = db_con_perfil
    _correr(db, ScraperFalso(db, _listado(1)), AnalistaFalso(db))
    fila = db.obtener_licitacion("L-0")
    assert fila["fecha_publicacion"] == "2026-02-05"
    assert fila["reclamos_pago_n"] == 181 and fila["organismo"] == "HOSPITAL DE PRUEBA"


def test_cuota_agotada_detiene_sin_consumir_intentos(db_con_perfil):
    db = db_con_perfil
    r = _correr(db, ScraperFalso(db, _listado(3)), AnalistaFalso(db, cuota_en="L-0"))
    assert "429" in r["detenido_por"]
    fila = db.obtener_licitacion("L-0")
    assert fila["estado"] == "extraido" and fila["intentos"] == 0
    assert r["en_cola"] == 3


def test_driver_no_disponible_detiene_sin_consumir_intentos(db_con_perfil):
    db = db_con_perfil
    r = _correr(db, ScraperFalso(db, _listado(2), driver_roto=True), AnalistaFalso(db))
    assert "Chrome" in r["detenido_por"] and r["intentadas"] == 0
    assert db.obtener_licitacion("L-0")["intentos"] == 0
    assert describir_resumen(r)[0] == "error"


def test_sin_perfil_no_ejecuta(db):
    r = _correr(db, ScraperFalso(db, _listado(2)), AnalistaFalso(db))
    assert r["detenido_por"] and r["registradas"] == 0
    assert describir_resumen(r)[0] == "error"


def test_filtro_negativas_estado_y_cierre(db_con_perfil):
    db = db_con_perfil
    listado = (_listado(1, "OK")
               + _listado(1, "NEG", nombre="Reactivos y limpieza")
               + _listado(1, "EST", estado=8)
               + _listado(1, "CER", cierre="2026-02-01T10:00:00")
               + _listado(1, "SIN", cierre=None)
               + _listado(1, "OTRO", nombre="Servicio de guardias"))
    r = _correr(db, ScraperFalso(db, listado), AnalistaFalso(db))
    assert {l["id_externo"] for l in db.obtener_licitaciones()} == {"OK-0", "SIN-0"}
    assert r["descartadas_cerradas"] == 1


def test_pendiente_que_cierra_en_cola_pasa_a_error(db_con_perfil):
    db = db_con_perfil
    db.guardar_licitacion({"id_externo": "VIEJA", "titulo": "Reactivos", "fecha_cierre": "2026-02-01T10:00:00"})
    r = _correr(db, ScraperFalso(db, []), AnalistaFalso(db))
    assert r["cerradas_en_cola"] == 1
    assert db.obtener_licitacion("VIEJA")["estado"] == "error"


def test_mensajes_del_resumen(db_con_perfil):
    db = db_con_perfil
    assert describir_resumen(_correr(db, ScraperFalso(db, []), AnalistaFalso(db)))[0] == "info"
    assert describir_resumen(_correr(db, ScraperFalso(db, _listado(1)), AnalistaFalso(db)))[0] == "success"
    r = _correr(db, ScraperFalso(db, _listado(1, "F"), fallan={"F-0"}), AnalistaFalso(db))
    assert describir_resumen(r)[0] == "warning"


# --- HTTP de descubrimiento (requests simulado) ---

class _RespHTTP:
    def __init__(self, status=200, payload=None, json_error=False):
        self.status_code, self.reason, self._payload, self._json_error = status, "Reason", payload, json_error

    def json(self):
        if self._json_error:
            raise ValueError("no json")
        return self._payload


@pytest.mark.parametrize("comportamiento,fragmento", [
    (requests.Timeout("t"), "no respondió"),
    (requests.ConnectionError("https://api?ticket=SECRETO"), "Error de conexión"),
    (_RespHTTP(500), "500"),
    (_RespHTTP(200, json_error=True), "no es JSON"),
    (_RespHTTP(200, {"Codigo": 203, "Mensaje": "Ticket no válido"}), "Ticket no válido"),
])
def test_errores_http_descubrimiento(db, monkeypatch, comportamiento, fragmento):
    monkeypatch.setenv("MP_TICKET", "SECRETO")

    def falso_get(*args, **kwargs):
        assert kwargs.get("timeout")                       # Siempre con timeout
        if isinstance(comportamiento, Exception):
            raise comportamiento
        return comportamiento

    monkeypatch.setattr(requests, "get", falso_get)
    scraper = LicitacionScraper(db)
    assert scraper.descubrir_licitaciones_del_dia() == []
    assert fragmento in scraper.error_descubrimiento
    assert "SECRETO" not in scraper.error_descubrimiento


def test_descubrimiento_ok(db, monkeypatch):
    monkeypatch.setenv("MP_TICKET", "T")
    monkeypatch.setattr(requests, "get", lambda *a, **k: _RespHTTP(200, {"Listado": [{"CodigoExterno": "A"}]}))
    assert LicitacionScraper(db).descubrir_licitaciones_del_dia() == [{"CodigoExterno": "A"}]


def test_sin_ticket(db, monkeypatch):
    monkeypatch.delenv("MP_TICKET", raising=False)
    scraper = LicitacionScraper(db)
    assert scraper.descubrir_licitaciones_del_dia() == []
    assert "MP_TICKET" in scraper.error_descubrimiento


def test_error_de_chrome_se_convierte_en_driver_no_disponible(db, monkeypatch):
    import core.scraper as mod

    class ManagerRoto:
        def install(self):
            raise OSError("sin red")

    monkeypatch.setattr(mod, "ChromeDriverManager", ManagerRoto)
    with pytest.raises(DriverNoDisponible):
        LicitacionScraper(db).extraer_detalle_licitacion("X")
