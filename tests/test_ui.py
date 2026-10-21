# -*- coding: utf-8 -*-
"""Helpers de presentación y páginas con streamlit.testing (BD temporal)."""

import json
import os
import sqlite3
from datetime import datetime, timedelta

import pytest
from streamlit.testing.v1 import AppTest

from core import rubrica
from core.database_mgr import DatabaseManager
from web import vistas as helpers

APP = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "app.py")
AHORA = datetime(2026, 10, 20, 12, 0)


def _v1(estado="definitivo", score=None, **kw):
    """Campos de un análisis con la rúbrica v1."""
    return dict({"rubrica_version": rubrica.RUBRICA_VERSION, "score_estado": estado, "score_idoneidad": score}, **kw)


def test_score_comparable_solo_con_la_rubrica():
    assert helpers.score_comparable({"score_ia": None}) is None
    assert helpers.score_comparable({"score_ia": "8"}) is None                 # Escala anterior: no se compara con 0-100
    assert helpers.score_comparable(_v1("definitivo", 83)) == 83
    assert helpers.score_comparable(_v1("provisional", 71)) == 71
    assert helpers.score_comparable(_v1("no_elegible")) is None
    assert helpers.score_comparable(_v1("evaluacion_insuficiente")) is None


def test_sugiere_descartar():
    r = rubrica.resultado_guardado
    assert helpers.sugiere_descartar(r(_v1("no_elegible")))
    assert helpers.sugiere_descartar(r(_v1("definitivo", 39))) and not helpers.sugiere_descartar(r(_v1("definitivo", 40)))
    assert helpers.sugiere_descartar(r({"score_ia": 4})) and not helpers.sugiere_descartar(r({"score_ia": 5}))
    assert not helpers.sugiere_descartar(r(_v1("evaluacion_insuficiente")))


def test_cierre_no_altera_el_score():
    """La urgencia se muestra aparte: la fecha de cierre no cambia el resultado ni su posición por score."""
    base = _v1("definitivo", 83, id_externo="X")
    hoy, lejos = dict(base, fecha_cierre="2026-10-20T18:00:00"), dict(base, fecha_cierre="2027-03-01T10:00:00")
    assert rubrica.resultado_guardado(hoy) == rubrica.resultado_guardado(lejos)
    assert helpers.clave_mayor_score(hoy) == helpers.clave_mayor_score(lejos)


def test_info_pago_distingue_procedencia():
    assert helpers.info_pago({"reclamos_pago_n": None, "reclamo_pago": None}) == (None, None)
    fuente, ia = helpers.info_pago({"reclamos_pago_n": 180, "reclamo_pago": "Riesgo alto"})
    assert "180" in fuente and "Fuente: Mercado Público" in fuente and ia == "Riesgo alto"
    # El antiguo heurístico ('0' en el texto => verde) ya no existe
    assert helpers.info_pago({"reclamos_pago_n": 0, "reclamo_pago": "No informado"})[1] is None
    # La fuente indica cuándo se leyó la ficha, si se registró
    fuente, _ = helpers.info_pago({"reclamos_pago_n": 3, "ficha_fecha": "2026-10-21T09:15:00"})
    assert fuente.endswith("(ficha leída el 21/10/2026)")


def test_agrupar_por_fecha_cronologico_con_formatos_mixtos():
    # BD antigua: mezcla dd/mm/aaaa con ISO; el orden debe seguir siendo cronológico
    lista = [{"fecha_publicacion": f, "id_externo": f or "n"} for f in ["30/09/2026", None, "2027-01-10", "2026-10-20"]]
    etiquetas = [e for e, _ in helpers.agrupar_por_fecha(lista)]
    assert etiquetas == ["Publicadas el 10/01/2027", "Publicadas el 20/10/2026", "Publicadas el 30/09/2026",
                         "Fecha de publicación no disponible"]


def test_titulo_de():
    assert helpers.titulo_de({"id_externo": "X", "titulo": "Sin título"}, {"titulo_recuperado": "IA"}) == "IA"
    assert helpers.titulo_de({"id_externo": "X", "titulo": "Real"}, {"titulo_recuperado": "IA"}) == "Real"
    assert helpers.titulo_de({"id_externo": "X", "titulo": None}) == "Licitación X"


def test_etiqueta_y_urgencia_de_cierre():
    def et(cierre):
        l = {"fecha_cierre": cierre}
        return helpers.etiqueta_cierre(l, AHORA), helpers.urgencia_cierre(l, AHORA)
    assert et("2026-10-20T18:00:00") == ("Cierra hoy", "bajo")
    assert et("2026-10-21T10:00:00") == ("Cierra mañana", "bajo")
    assert et("2026-10-25T10:00:00") == ("Cierra en 5 días", "medio")
    assert et("2026-11-30T10:00:00") == ("Cierra en 41 días", "")
    assert et("2026-10-20T09:00:00") == ("Cerrada", "")
    assert et(None) == ("Cierre sin informar", "")


def test_region_corta():
    assert helpers.region_corta("Región de los Lagos") == "Los Lagos"
    assert helpers.region_corta("Región de la Araucanía") == "Araucanía"
    assert helpers.region_corta("Región del Maule") == "Maule"
    assert helpers.region_corta("Región Metropolitana de Santiago") == "Metropolitana de Santiago"


def test_tarjeta_html_escapa_texto_externo():
    """El título y el organismo vienen del portal/IA: nunca deben inyectar HTML."""
    html = helpers.html_tarjeta({"id_externo": "X<1>", "titulo": "<script>alert(1)</script>", "organismo": "A & B",
                                 "score_ia": 9, "fecha_cierre": None, "region": "Región del Maule", "reclamos_pago_n": 5})
    assert "<script>" not in html and "&lt;script&gt;" in html and "A &amp; B" in html and "X&lt;1&gt;" in html
    assert helpers.COLOR_NIVEL["alto"] in html and "Maule" in html and "5 reclamos de pago" in html


LISTA = [
    _v1("definitivo", 92, id_externo="A", titulo="Reactivos clínicos", organismo="Hospital Uno", region="Región del Maule",
        fecha_cierre="2026-11-30T10:00:00", fecha_publicacion="2026-10-01"),
    _v1("provisional", 64, id_externo="B", titulo="Microscopio", organismo="Municipalidad de Angol",
        region="Región de la Araucanía", fecha_cierre="2026-10-22T10:00:00", fecha_publicacion="2026-10-15"),
    {"id_externo": "C", "titulo": "Centrífuga", "organismo": "Hospital Dos", "region": None,
     "score_ia": None, "fecha_cierre": None, "fecha_publicacion": None},
    _v1("definitivo", 85, id_externo="D", titulo="Cerrada", organismo="Hospital Tres", region="Región del Maule",
        fecha_cierre="2026-10-01T10:00:00", fecha_publicacion="2026-09-20"),
]


def _ids(lista):
    return [l["id_externo"] for l in lista]


def test_filtrar_y_ordenar():
    f = helpers.filtrar_y_ordenar
    assert _ids(f(LISTA, orden="Cierre más próximo", ahora=AHORA)) == ["D", "B", "A", "C"]
    assert _ids(f(LISTA, orden="Cierre más próximo", ocultar_cerradas=True, ahora=AHORA)) == ["B", "A", "C"]
    assert _ids(f(LISTA, orden="Mayor score", ahora=AHORA)) == ["A", "D", "B", "C"]
    assert _ids(f(LISTA, orden="Más recientes", ahora=AHORA)) == ["B", "A", "D", "C"]
    assert _ids(f(LISTA, texto="ANGOL", ahora=AHORA)) == ["B"]                      # Busca también en organismo
    assert _ids(f(LISTA, texto="centrifuga", ahora=AHORA)) == ["C"]                 # Sin tildes
    assert _ids(f(LISTA, score_min=80, orden="Mayor score", ahora=AHORA)) == ["A", "D"]  # Sin score queda fuera
    assert _ids(f(LISTA, score_min=0, ahora=AHORA)) == ["D", "B", "A", "C"]              # Mínimo 0 = sin filtro
    assert _ids(f(LISTA, regiones=["Región del Maule"], orden="Mayor score", ahora=AHORA)) == ["A", "D"]


def test_mayor_score_agrupa_por_estado():
    """Primero los scores 0-100 (definitivo o provisional), luego la escala anterior y al final los sin número."""
    lista = [_v1("no_elegible", id_externo="NE"), {"id_externo": "H", "score_ia": 9}, _v1("definitivo", 50, id_externo="D50"),
             _v1("evaluacion_insuficiente", id_externo="I"), _v1("provisional", 70, id_externo="P70"), {"id_externo": "SIN"}]
    assert _ids(helpers.filtrar_y_ordenar(lista, orden="Mayor score", ahora=AHORA)) == ["P70", "D50", "H", "I", "NE", "SIN"]
    assert _ids(helpers.filtrar_y_ordenar(lista, score_min=5, ahora=AHORA)) == ["P70", "D50"]   # El 9/10 no pasa a 0-100


def test_metricas_resumen():
    lista = [dict(l, estado="analizado") for l in LISTA] + [{"id_externo": "E", "estado": "error"}]
    m = helpers.metricas_resumen(lista, AHORA)
    # Promedio solo de definitivos abiertos (A); el provisional B no se mezcla
    assert m == {"activas": 3, "cierran_7": 1, "score_promedio": 92.0, "n_definitivos": 1, "en_cola": 1}


def test_trazabilidad_sin_jerga_y_detalles_aparte():
    assert helpers.texto_trazabilidad({}) == "" and helpers.detalles_tecnicos({}) == []
    licit = {"analisis_fecha": "2026-10-20T10:00:00", "analisis_modelo": "m", "analisis_prompt_version": "v1",
             "analisis_perfil_version": "abc12345"}
    assert helpers.texto_trazabilidad(licit) == "Analizado el 20/10/2026 a las 10:00"
    assert helpers.detalles_tecnicos(licit) == ["Modelo: m", "Versión del prompt: v1", "Versión del perfil: abc12345"]
    assert "Detalles técnicos" in helpers.html_detalles_tecnicos(["<x>"]) and "&lt;x&gt;" in helpers.html_detalles_tecnicos(["<x>"])
    assert helpers.html_detalles_tecnicos([]) == ""


@pytest.mark.parametrize("tecnico,esperado", [
    ("Extracción: TimeoutException: Message: timeout", "no respondió a tiempo"),
    ("Extracción: No se encontró el enlace a la ficha en el buscador del portal", "No se encontró la licitación"),
    ("Extracción: Texto de la ficha insuficiente o no reconocido (12 caracteres)", "no se pudo leer completa"),
    ("IA: Respuesta de IA inválida: JSON inválido o truncado", "no entregó un análisis válido"),
    ("Cuota de Gemini agotada: 429 Resource has been exhausted", "límite de uso de la IA"),
    ("La licitación cerró antes de poder procesarse", "cerró antes"),
    ("Ya no coincide con las keywords del perfil", "palabras clave"),
    ("MP_TICKET no configurado en .env", "acceso a Mercado Público"),
    ("No se pudo iniciar Chrome: WebDriverException: x", "Google Chrome"),
    ("Ya hay una sincronización en curso (iniciada hace 2 min).", "en curso"),
    ("algo totalmente desconocido", "No se pudo completar"),
])
def test_mensaje_error_amigable(tecnico, esperado):
    mensaje = helpers.mensaje_error_amigable(tecnico)
    assert esperado in mensaje
    assert "Exception" not in mensaje and "429" not in mensaje and ".env" not in mensaje   # Sin jerga técnica


def test_mensaje_sincronizacion():
    base = {"analizadas": 0, "en_cola": 0, "fallidas": 0, "detenido_por": None, "error_descubrimiento": None}
    assert helpers.mensaje_sincronizacion(dict(base, analizadas=3), "success") == "3 licitaciones nuevas analizadas."
    assert helpers.mensaje_sincronizacion(dict(base, analizadas=1), "success") == "1 licitación nueva analizada."
    assert helpers.mensaje_sincronizacion(base, "info") == "No hubo licitaciones nuevas para analizar."
    texto = helpers.mensaje_sincronizacion(dict(base, analizadas=2, en_cola=3, fallidas=1,
                                                error_descubrimiento="La API de Mercado Público no respondió en 30 s"), "warning")
    assert "3 quedan en espera" in texto and "1 no se pudieron completar" in texto and "no respondió" in texto
    assert "API" not in texto
    error = helpers.mensaje_sincronizacion(dict(base, detenido_por="No hay palabras clave positivas en el perfil de negocio."), "error")
    assert "palabra clave" in error


def test_anillo_distingue_cada_estado():
    anillo = lambda licit: helpers.html_anillo(rubrica.resultado_guardado(licit))
    definitivo = anillo(_v1("definitivo", 83))
    assert "--p:83%" in definitivo and "<b>83</b><small>/100</small>" in definitivo
    assert "<small>PROV.</small>" in anillo(_v1("provisional", 71))
    assert "NO ELEG." in anillo(_v1("no_elegible")) and helpers.COLOR_NIVEL["bajo"] in anillo(_v1("no_elegible"))
    assert "INCOMPL." in anillo(_v1("evaluacion_insuficiente")) and "SIN DATOS" not in anillo(_v1("evaluacion_insuficiente"))
    historico = anillo({"score_ia": 8})
    assert "--p:80%" in historico and "<b>8</b><small>/10 ANT.</small>" in historico
    assert "--p:0%" in anillo({}) and "–" in anillo({})


def test_chips_y_desglose():
    r = rubrica.resultado_guardado
    assert "Buena oportunidad" in "".join(helpers.chips_score(r(_v1("definitivo", 83))))
    provisional = "".join(helpers.chips_score(r(_v1("provisional", 71, score_cobertura=80))))
    assert "Provisional" in provisional and "Cobertura 80 %" in provisional
    assert "Escala anterior" in "".join(helpers.chips_score(r({"score_ia": 8})))
    assert helpers.chips_score(r({})) == []
    # Si no es definitivo, muestra lo que sí se sabe
    an = {"criterios": {"comercial": {"nota": 1}, "requisitos": {"nota": None}}}
    incompleto = "".join(helpers.chips_score(r(_v1("provisional", 20, score_cobertura=35)), an))
    assert "Encaje comercial 1/5" in incompleto and "l-bajo" in incompleto and "Requisitos: revisar bases" in incompleto
    assert "Encaje comercial" not in "".join(helpers.chips_score(r(_v1("definitivo", 83)), an))
    tabla = helpers.html_desglose({"criterios": {"comercial": {"nota": 5, "evidencia_estado": "suficiente",
                                                               "evidencia": "<i>cita</i>", "explicacion": "encaja"}}})
    assert "5/5" in tabla and "Peso 35 %" in tabla and "&lt;i&gt;cita&lt;/i&gt;" in tabla
    assert tabla.count("Sin nota") == 4   # Criterios sin nota no se inventan


def test_evaluacion_desactualizada():
    assert helpers.evaluacion_desactualizada({"eval_fecha": "2026-10-19T10:00:00", "analisis_fecha": "2026-10-20T10:00:00"})
    assert not helpers.evaluacion_desactualizada({"eval_fecha": "2026-10-21T10:00:00", "analisis_fecha": "2026-10-20T10:00:00"})
    assert not helpers.evaluacion_desactualizada({"analisis_fecha": "2026-10-20T10:00:00"})


# --- App completa (navegación superior: una página por archivo en web/paginas/) ---

@pytest.fixture
def app_db(tmp_path, monkeypatch):
    path = str(tmp_path / "ui.db")
    monkeypatch.setenv("DATABASE_PATH", path)
    db = DatabaseManager(path)
    # Incluye casos que antes rompían la UI: score NULL, JSON corrupto, lista guardada como texto
    analisis = json.dumps({"veredicto": "ok", "puntos_criticos": "texto suelto", "riesgos": ["r"]})
    cierre = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
    filas = [("A", "analizado", 8, analisis), ("N", "analizado", None, None), ("C", "analizado", 5, "{corrupto"),
             ("F", "favorita", 9, analisis), ("R", "archivada", 3, analisis), ("E", "error", None, None)]
    conn = sqlite3.connect(path)
    conn.executemany(
        "INSERT INTO licitaciones (id_externo, titulo, fecha_publicacion, fecha_cierre, estado, score_ia, analisis_ia_json,"
        " ultimo_error, reclamos_pago_n, region) VALUES (?, ?, '2026-02-05', ?, ?, ?, ?, ?, 40, 'Región del Maule')",
        [(i, f"Licitación de prueba {i}", cierre, e, s, a, "Timeout" if e == "error" else None) for i, e, s, a in filas])
    # Análisis con la rúbrica v1, uno por estado (incluye un caso sin datos de pago)
    analisis_v1 = json.dumps({
        "veredicto": "ok v1", "puntos_criticos": ["p"], "riesgos": ["r"],
        "criterios": {"comercial": {"nota": 5, "evidencia_estado": "suficiente", "evidencia": "cita", "explicacion": "x"}},
        "requisitos_excluyentes": [{"requisito": "Registro ISP", "estado": "incumplido_confirmado", "evidencia": "Lo exige"}],
        "datos_faltantes": ["Presupuesto"], "hechos_fuente": ["h"], "inferencias": ["i"],
        "rubrica": {"version": "v1", "motivo": "Motivo del estado", "advertencias": ["Advertencia de prueba"]}})
    estados_v1 = [("V1D", "definitivo", 83, 100), ("V1P", "provisional", 71, 80), ("V1N", "no_elegible", None, 100),
                  ("V1I", "evaluacion_insuficiente", None, 20)]
    conn.executemany(
        "INSERT INTO licitaciones (id_externo, titulo, fecha_publicacion, fecha_cierre, estado, analisis_ia_json, rubrica_version,"
        " score_estado, score_idoneidad, score_cobertura) VALUES (?, ?, '2026-02-05', ?, 'analizado', ?, 'v1', ?, ?, ?)",
        [(i, f"Licitación v1 {i}", cierre, analisis_v1, e, s, c) for i, e, s, c in estados_v1])
    conn.commit()
    conn.close()
    return db


def _html(at):
    return " ".join(str(e.proto) for e in at.get("html"))


def test_estados_del_score_se_renderizan(app_db):
    """Oportunidades distingue definitivo, provisional, no elegible, insuficiente y escala anterior."""
    at = _app()
    assert not at.exception
    html = _html(at)
    for texto in ("/100", "PROV.", "NO ELEG.", "INCOMPL.", "/10 ANT.", "Buena oportunidad", "Cobertura 80 %",
                  "Escala anterior", "Evaluación incompleta", "Encaje comercial 5/5", "Requisitos: revisar bases", "Desglose del score", "Motivo del estado",
                  "Advertencia de prueba", "Registro ISP", "no es la probabilidad"):
        assert texto in html, texto
    # Sin dato de la fuente: no se presume bajo riesgo de pago
    assert "Sin datos verificados sobre pagos" in html
    at = _app("favoritas")
    assert not at.exception


def _boton(at, key):
    return next(b for b in at.button if b.key == key)


def _app(pagina=None):
    at = AppTest.from_file(APP, default_timeout=30)
    if pagina:
        at.switch_page(f"paginas/{pagina}.py")
    return at.run()


@pytest.mark.parametrize("pagina", [None, "favoritas", "archivo", "cola", "panorama", "perfil"])
def test_todas_las_paginas_renderizan_sin_excepciones(app_db, pagina):
    at = _app(pagina)
    assert not at.exception
    assert any("Agrega al menos una palabra clave" in w.value for w in at.warning)


def test_oportunidades_kpis(app_db):
    at = _app()
    html = " ".join(str(e.proto) for e in at.get("html"))
    assert "Oportunidades activas" in html and "Cierran esta semana" in html and "En proceso" in html


def test_kpi_html_escapa():
    html = helpers.html_kpi("<b>", "<1>", "target", "alto", "<pie>")
    assert "&lt;b&gt;" in html and "&lt;1&gt;" in html and "&lt;pie&gt;" in html and "l-tinte-alto" in html


def test_botones_de_estado_en_cada_pagina(app_db):
    at = _app()
    _boton(at, "fav_A").click().run()
    assert app_db.obtener_licitacion("A")["estado"] == "favorita"
    _boton(at, "arc_N").click().run()
    assert app_db.obtener_licitacion("N")["estado"] == "archivada"

    at = _app("archivo")
    _boton(at, "re_R").click().run()
    assert app_db.obtener_licitacion("R")["estado"] == "analizado"

    at = _app("cola")
    _boton(at, "retry_E").click().run()
    assert app_db.obtener_licitacion("E")["estado"] == "pendiente"

    at = _app("favoritas")
    _boton(at, "back_F").click().run()
    assert app_db.obtener_licitacion("F")["estado"] == "analizado"
    assert not at.exception


def test_filtro_de_texto_en_la_ui(app_db):
    at = _app()
    at.text_input(key="f_txt_analizadas").input("prueba A").run()
    assert not at.exception
    claves = {b.key for b in at.button}
    assert "fav_A" in claves and "fav_C" not in claves and "fav_N" not in claves


def test_notas_persisten(app_db):
    at = _app("favoritas")
    at.text_area(key="txt_F").input("Costos revisados")
    at.checkbox(key="chk_bases_leidas_F").check()
    next(b for b in at.button if "Guardar notas" in b.label).click().run()
    fila = app_db.obtener_licitacion("F")
    assert fila["notas"] == "Costos revisados"
    assert json.loads(fila["checklist_json"])["bases_leidas"] is True
    # Nueva sesión: los valores se recargan desde la BD
    at2 = _app("favoritas")
    assert at2.text_area(key="txt_F").value == "Costos revisados"
    assert at2.checkbox(key="chk_bases_leidas_F").value is True


def test_evaluacion_se_guarda(app_db):
    at = _app()
    at.radio(key="evs_lista_A").set_value("muy_alto")
    at.radio(key="evp_lista_A").set_value("tal_vez")
    at.text_input(key="evc_lista_A").input("Pide experiencia local")
    _boton(at, "evb_lista_A").click().run()
    fila = app_db.obtener_licitacion("A")
    assert (fila["eval_score"], fila["eval_postularia"], fila["eval_comentario"]) == ("muy_alto", "tal_vez", "Pide experiencia local")
    assert not at.exception


def test_evaluacion_incompleta_no_se_guarda(app_db):
    at = _app()
    at.radio(key="evs_lista_A").set_value("acertado")
    _boton(at, "evb_lista_A").click().run()
    assert app_db.obtener_licitacion("A")["eval_score"] is None


def _con_ficha(db, id_ext):
    conn = sqlite3.connect(db.db_path)
    conn.execute("UPDATE licitaciones SET descripcion_pro = 'Licitación ID: X ficha' WHERE id_externo = ?", (id_ext,))
    conn.commit()
    conn.close()


def _gemini_falso(monkeypatch, analizar):
    import core.ai_analyst as ai
    monkeypatch.setenv("GEMINI_API_KEY", "falsa")
    monkeypatch.setattr(ai.genai, "configure", lambda **kw: None)
    monkeypatch.setattr(ai.genai, "GenerativeModel", lambda *a, **kw: object())
    monkeypatch.setattr(ai.AIAnalyst, "analizar_licitacion", analizar)


def test_boton_reanalizar_guarda_nuevo_analisis(app_db, monkeypatch):
    _con_ficha(app_db, "F")
    llamadas = []

    def analizar_falso(self, id_ext):
        llamadas.append(id_ext)
        data = {"score_ia": 4, "veredicto": "nuevo", "puntos_criticos": [], "riesgos": []}
        self.db.guardar_analisis_ia(id_ext, 4, data, modelo="m", prompt_version="v")
        return data

    _gemini_falso(monkeypatch, analizar_falso)
    at = _app("favoritas")
    _boton(at, "iaf_F").click().run()
    assert llamadas == ["F"]
    fila = app_db.obtener_licitacion("F")
    assert fila["score_ia"] == 4 and fila["estado"] == "favorita" and json.loads(fila["analisis_ia_json"])["veredicto"] == "nuevo"
    assert any("Análisis actualizado" in s.value for s in at.success)


def test_boton_reanalizar_fallido_conserva_anterior(app_db, monkeypatch):
    import core.ai_analyst as ai
    _con_ficha(app_db, "A")

    def analizar_roto(self, id_ext):
        raise ai.AnalisisFallido("Respuesta de IA inválida")

    _gemini_falso(monkeypatch, analizar_roto)
    antes = app_db.obtener_licitacion("A")
    at = _app()
    _boton(at, "ia_A").click().run()
    despues = app_db.obtener_licitacion("A")
    assert (despues["score_ia"], despues["analisis_ia_json"]) == (antes["score_ia"], antes["analisis_ia_json"])
    assert any("se mantiene el anterior" in e.value for e in at.error)


def test_boton_reanalizar_solo_si_hay_ficha(app_db):
    at = _app("favoritas")
    assert not any(b.key == "iaf_F" for b in at.button)   # Sin texto extraído no hay nada que re-analizar


def test_guardar_perfil(app_db):
    at = _app("perfil")
    next(ta for ta in at.text_area if ta.label == "Palabras clave de interés").input("reactivos, ")
    next(b for b in at.button if "Guardar cambios" in b.label).click().run()
    assert app_db.obtener_perfil()["keywords_pos"] == "reactivos, "
    assert not at.exception


def test_panorama_con_ejecuciones_y_evaluaciones(app_db):
    inicio = datetime.now()
    app_db.registrar_ejecucion({"total_listado": 1100, "descubiertas": 6, "registradas": 6, "analizadas": 4, "fallidas": 0},
                               inicio, inicio, inicio.strftime("%Y-%m-%d"))
    for i in range(12):   # Supera el mínimo para dibujar la calibración
        id_ = f"EV{i}"
        app_db.guardar_licitacion({"id_externo": id_, "titulo": f"Evaluada {i}"})
        score = 10 * (i % 10) + 5
        app_db.guardar_analisis_ia(id_, None, {"veredicto": "ok"},
                                   rubrica={"version": "v1", "estado": "definitivo", "score": score, "cobertura": 100})
        app_db.guardar_evaluacion(id_, "acertado", ("si", "no", "tal_vez")[i % 3])
    at = _app("panorama")
    assert not at.exception
    textos = " ".join(m.value for m in at.markdown)
    assert "De lo publicado a tus oportunidades" in textos and "acertada es la IA" in textos
    assert not any("Evalúa al menos" in i.value for i in at.info)
    assert {b.label for b in at.get("download_button")} >= {"JSON", "Excel (CSV)"}


# --- En proceso: orden y análisis a pedido ---

def test_orden_cola_sigue_el_de_la_sincronizacion():
    lista = [{"id_externo": "ERR", "estado": "error", "fecha_cierre": "2026-10-22T10:00:00"},
             {"id_externo": "SIN", "estado": "pendiente", "fecha_cierre": None},
             {"id_externo": "LEJOS", "estado": "extraido", "fecha_cierre": "2026-12-01T10:00:00"},
             {"id_externo": "PRONTO", "estado": "pendiente", "fecha_cierre": "2026-10-25T10:00:00"}]
    assert _ids(helpers.orden_cola(lista)) == ["PRONTO", "LEJOS", "SIN", "ERR"]


@pytest.mark.parametrize("resultado, motivo, nivel, texto", [
    ("analizada", None, "success", "83/100"),
    ("fallida", "IA: Respuesta de IA inválida", "error", "no entregó un análisis válido"),
    ("cuota", "Cuota de Gemini agotada: 429", "error", "límite de uso"),
    ("en_curso", "Ya hay una sincronización en curso", "error", "en curso"),
    ("sin_navegador", "No se pudo iniciar Chrome", "error", "Google Chrome"),
    ("cerrada", "La licitación cerró antes", "warning", "cerró antes"),
    ("no_disponible", "x", "info", "ya no está en proceso"),
])
def test_mensaje_analisis_a_pedido(resultado, motivo, nivel, texto):
    licit = {"rubrica_version": "v1.1", "score_estado": "definitivo", "score_idoneidad": 83}
    n, m = helpers.mensaje_analisis_a_pedido(resultado, motivo, licit)
    assert n == nivel and texto in m and "429" not in m


def test_boton_analizar_ahora_en_proceso(app_db, monkeypatch):
    import main
    llamadas = []

    def analizar_falso(db, id_ext, **kw):
        llamadas.append(id_ext)
        db.guardar_analisis_ia(id_ext, None, {"veredicto": "a pedido"},
                               rubrica={"version": "v1.1", "estado": "definitivo", "score": 88, "cobertura": 100})
        return "analizada", None

    monkeypatch.setattr(main, "analizar_ahora", analizar_falso)
    at = _app("cola")
    assert not at.exception and any("Ordenadas como se procesarán" in c.value for c in at.caption)
    _boton(at, "now_E").click().run()
    assert llamadas == ["E"] and app_db.obtener_licitacion("E")["estado"] == "analizado"
    assert any("88/100" in s.value for s in at.success)
