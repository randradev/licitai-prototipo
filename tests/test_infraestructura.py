# -*- coding: utf-8 -*-
"""Bloqueo de ejecución, logging, espera de Selenium y configuración de Gemini."""

import logging
import os
import time

import pytest

import core.ai_analyst as ai_mod
from core import config
from core.ai_analyst import AIAnalyst
from core.scraper import esperar_texto_estable
from main import bloqueo_pipeline, ejecutar_pipeline, PipelineEnCurso, describir_resumen


# --- Gemini ---

def test_modelo_se_crea_con_json_y_temperatura_cero(db, monkeypatch):
    capturado = {}
    monkeypatch.setenv("GEMINI_API_KEY", "clave-falsa")
    monkeypatch.setattr(ai_mod.genai, "configure", lambda **kw: None)
    monkeypatch.setattr(ai_mod.genai, "GenerativeModel",
                        lambda nombre, generation_config: capturado.update(nombre=nombre, gc=generation_config))
    AIAnalyst(db)
    assert capturado["nombre"] == config.GEMINI_MODEL
    assert capturado["gc"] == {"response_mime_type": "application/json", "response_schema": ai_mod.esquema_respuesta(),
                               "temperature": 0.0}


def test_esquema_fija_las_claves_de_la_rubrica():
    """La salida estructurada impide claves traducidas (p. ej. 'capacity') y estados fuera de lista."""
    from core import rubrica
    from google.generativeai.types import generation_types
    esquema = ai_mod.esquema_respuesta()
    criterios = esquema["properties"]["criterios"]
    assert criterios["required"] == [c.clave for c in rubrica.CRITERIOS]
    capacidad = criterios["properties"]["capacidad"]
    assert capacidad["required"] == ["nota", "evidencia_estado", "evidencia", "explicacion"]
    assert capacidad["properties"]["nota"] == {"type": "integer", "nullable": True}
    assert capacidad["properties"]["evidencia_estado"]["enum"] == list(rubrica.EVIDENCIA_ESTADOS)
    estado = esquema["properties"]["requisitos_excluyentes"]["items"]["properties"]["estado"]
    assert estado["enum"] == list(rubrica.EXCLUYENTE_ESTADOS)
    assert "score_ia" not in esquema["properties"]   # El modelo no entrega el total
    # El SDK lo acepta y lo convierte a su formato (sin red)
    generation_types.to_generation_config_dict({"response_mime_type": "application/json", "response_schema": esquema})


# --- Bloqueo ---

def test_bloqueo_impide_ejecucion_simultanea(tmp_path):
    ruta = str(tmp_path / "x.db")
    with bloqueo_pipeline(ruta):
        assert os.path.exists(ruta + ".lock")
        with pytest.raises(PipelineEnCurso):
            with bloqueo_pipeline(ruta):
                pass
    assert not os.path.exists(ruta + ".lock")


def test_bloqueo_se_libera_ante_excepcion(tmp_path):
    ruta = str(tmp_path / "x.db")
    with pytest.raises(RuntimeError):
        with bloqueo_pipeline(ruta):
            raise RuntimeError("fallo")
    assert not os.path.exists(ruta + ".lock")


def test_bloqueo_huerfano_se_reemplaza(tmp_path):
    ruta = str(tmp_path / "x.db")
    open(ruta + ".lock", "w").close()
    viejo = time.time() - 3 * 3600
    os.utime(ruta + ".lock", (viejo, viejo))
    with bloqueo_pipeline(ruta, max_minutos=120):
        pass
    assert not os.path.exists(ruta + ".lock")


def test_pipeline_con_bloqueo_activo_no_ejecuta(db_con_perfil):
    open(db_con_perfil.db_path + ".lock", "w").close()
    r = ejecutar_pipeline(db=db_con_perfil, scraper=object(), analyst=object())
    assert "en curso" in r["detenido_por"]
    assert describir_resumen(r)[0] == "error"


# --- Selenium: espera hasta que el texto se estabilice ---

class DriverFalso:
    def __init__(self, textos):
        self.textos, self.lecturas = list(textos), 0

    def execute_script(self, _js):
        self.lecturas += 1
        return self.textos.pop(0) if len(self.textos) > 1 else self.textos[0]


def test_espera_texto_estable_devuelve_cuando_deja_de_cambiar():
    driver = DriverFalso(["a", "ab", "abc", "abcd", "abcd", "abcd", "abcd"])
    assert esperar_texto_estable(driver, max_segundos=5, intervalo=0) == "abcd"
    assert driver.lecturas == 6   # 4 cambios + 2 lecturas iguales adicionales


def test_espera_texto_estable_respeta_el_limite():
    class Creciente:
        n = 0
        def execute_script(self, _js):
            self.n += 1
            return "x" * self.n
    inicio = time.monotonic()
    texto = esperar_texto_estable(Creciente(), max_segundos=0.3, intervalo=0.05)
    assert texto and time.monotonic() - inicio < 2


# --- Logging ---

@pytest.fixture
def logger_limpio():
    raiz = logging.getLogger("licitai")
    previos = raiz.handlers[:]
    raiz.handlers = [h for h in previos if not getattr(h, "_licitai", False)]
    yield raiz
    for h in raiz.handlers:
        if getattr(h, "_licitai", False):
            h.close()
    raiz.handlers = previos


def _propios(logger):
    return [h for h in logger.handlers if getattr(h, "_licitai", False)]


def test_logging_a_archivo_opcional(logger_limpio, tmp_path, monkeypatch):
    archivo = tmp_path / "logs" / "licitai.log"
    monkeypatch.setenv("LICITAI_LOG_FILE", str(archivo))
    config.configurar_logging()
    config.configurar_logging()   # Idempotente: no duplica handlers
    assert len(_propios(logger_limpio)) == 2
    logging.getLogger("licitai.main").warning("mensaje de prueba ✅")
    for h in _propios(logger_limpio):
        h.flush()
    contenido = archivo.read_text(encoding="utf-8")
    assert "WARNING licitai.main: mensaje de prueba ✅" in contenido


def test_logging_sin_archivo_solo_consola(logger_limpio, monkeypatch, capsys):
    monkeypatch.delenv("LICITAI_LOG_FILE", raising=False)
    config.configurar_logging()
    assert len(_propios(logger_limpio)) == 1
    logging.getLogger("licitai.scraper").info("hola consola")
    assert "hola consola" in capsys.readouterr().out
