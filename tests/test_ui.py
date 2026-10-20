# -*- coding: utf-8 -*-
"""Helpers de presentación y botones principales con streamlit.testing (BD temporal)."""

import json
import os
import sqlite3
from datetime import datetime, timedelta

import pytest
from streamlit.testing.v1 import AppTest

from core.database_mgr import DatabaseManager

APP = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "app.py")
AHORA = datetime(2026, 10, 20, 12, 0)


@pytest.fixture
def helpers():
    import web.app as app
    return app


def test_score_y_color(helpers):
    assert helpers.score_de({"score_ia": None}) is None
    assert helpers.score_de({"score_ia": "8"}) == 8
    assert helpers.color_score(None) == "⚪"
    assert helpers.color_score(7) == "🟢" and helpers.color_score(4) == "🟡" and helpers.color_score(3) == "🔴"
    assert helpers.texto_score(None) == "Sin score"


def test_info_pago_distingue_procedencia(helpers):
    assert helpers.info_pago({"reclamos_pago_n": None, "reclamo_pago": None}) == (None, None)
    fuente, ia = helpers.info_pago({"reclamos_pago_n": 180, "reclamo_pago": "Riesgo alto"})
    assert "180" in fuente and "fuente" in fuente and ia == "Riesgo alto"
    # El antiguo heurístico ('0' en el texto => verde) ya no existe
    assert helpers.info_pago({"reclamos_pago_n": 0, "reclamo_pago": "No informado"})[1] is None


def test_agrupar_por_fecha_cronologico_con_formatos_mixtos(helpers):
    # BD antigua: mezcla dd/mm/aaaa con ISO; el orden debe seguir siendo cronológico
    lista = [{"fecha_publicacion": f, "id_externo": f or "n"} for f in ["30/09/2026", None, "2027-01-10", "2026-10-20"]]
    etiquetas = [e for e, _ in helpers.agrupar_por_fecha(lista)]
    assert etiquetas == ["Publicadas el 10/01/2027", "Publicadas el 20/10/2026", "Publicadas el 30/09/2026",
                         "Fecha de publicación no disponible"]


def test_titulo_de(helpers):
    assert helpers.titulo_de({"id_externo": "X", "titulo": "Sin título"}, {"titulo_recuperado": "IA"}) == "IA"
    assert helpers.titulo_de({"id_externo": "X", "titulo": "Real"}, {"titulo_recuperado": "IA"}) == "Real"
    assert helpers.titulo_de({"id_externo": "X", "titulo": None}) == "Licitación X"


def test_etiqueta_cierre(helpers):
    def et(cierre):
        return helpers.etiqueta_cierre({"fecha_cierre": cierre}, AHORA)
    assert et("2026-10-20T18:00:00") == "⏰ cierra hoy"
    assert et("2026-10-21T10:00:00") == "⏰ cierra mañana"
    assert et("2026-10-25T10:00:00") == "⏰ cierra en 5 días"
    assert et("2026-11-30T10:00:00") == "cierra en 41 días"
    assert et("2026-10-20T09:00:00") == "cerrada"
    assert et(None) == "cierre sin informar"


LISTA = [
    {"id_externo": "A", "titulo": "Reactivos clínicos", "organismo": "Hospital Uno", "region": "Región del Maule",
     "score_ia": 9, "fecha_cierre": "2026-11-30T10:00:00", "fecha_publicacion": "2026-10-01"},
    {"id_externo": "B", "titulo": "Microscopio", "organismo": "Municipalidad de Angol", "region": "Región de la Araucanía",
     "score_ia": 6, "fecha_cierre": "2026-10-22T10:00:00", "fecha_publicacion": "2026-10-15"},
    {"id_externo": "C", "titulo": "Centrífuga", "organismo": "Hospital Dos", "region": None,
     "score_ia": None, "fecha_cierre": None, "fecha_publicacion": None},
    {"id_externo": "D", "titulo": "Cerrada", "organismo": "Hospital Tres", "region": "Región del Maule",
     "score_ia": 8, "fecha_cierre": "2026-10-01T10:00:00", "fecha_publicacion": "2026-09-20"},
]


def _ids(lista):
    return [l["id_externo"] for l in lista]


def test_filtrar_y_ordenar(helpers):
    f = helpers.filtrar_y_ordenar
    assert _ids(f(LISTA, orden="Cierre más próximo", ahora=AHORA)) == ["D", "B", "A", "C"]
    assert _ids(f(LISTA, orden="Cierre más próximo", ocultar_cerradas=True, ahora=AHORA)) == ["B", "A", "C"]
    assert _ids(f(LISTA, orden="Mayor score", ahora=AHORA)) == ["A", "D", "B", "C"]
    assert _ids(f(LISTA, orden="Más recientes", ahora=AHORA)) == ["B", "A", "D", "C"]
    assert _ids(f(LISTA, texto="ANGOL", ahora=AHORA)) == ["B"]                      # Busca también en organismo
    assert _ids(f(LISTA, texto="centrifuga", ahora=AHORA)) == ["C"]                 # Sin tildes
    assert _ids(f(LISTA, score_min=8, orden="Mayor score", ahora=AHORA)) == ["A", "D"]  # Sin score queda fuera
    assert _ids(f(LISTA, regiones=["Región del Maule"], orden="Mayor score", ahora=AHORA)) == ["A", "D"]


def test_metricas_resumen(helpers):
    lista = [dict(l, estado="analizado") for l in LISTA] + [{"id_externo": "E", "estado": "error"}]
    m = helpers.metricas_resumen(lista, AHORA)
    assert m == {"activas": 3, "cierran_7": 1, "score_promedio": 7.5, "en_cola": 1}


def test_trazabilidad_y_evaluacion_desactualizada(helpers):
    assert "sin registro" in helpers.texto_trazabilidad({})
    texto = helpers.texto_trazabilidad({"analisis_fecha": "2026-10-20T10:00:00", "analisis_modelo": "m", "analisis_prompt_version": "v1"})
    assert "20/10/2026 10:00" in texto and "m" in texto and "v1" in texto
    assert helpers.evaluacion_desactualizada({"eval_fecha": "2026-10-19T10:00:00", "analisis_fecha": "2026-10-20T10:00:00"})
    assert not helpers.evaluacion_desactualizada({"eval_fecha": "2026-10-21T10:00:00", "analisis_fecha": "2026-10-20T10:00:00"})
    assert not helpers.evaluacion_desactualizada({"analisis_fecha": "2026-10-20T10:00:00"})


# --- App completa ---

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
    conn.commit()
    conn.close()
    return db


def _boton(at, key):
    return next(b for b in at.button if b.key == key)


def _app():
    return AppTest.from_file(APP, default_timeout=30).run()


def test_app_renderiza_sin_excepciones_con_datos_problematicos(app_db):
    at = _app()
    assert not at.exception
    assert any("Configura al menos una keyword" in w.value for w in at.sidebar.warning)
    etiquetas = [m.label for m in at.metric]
    assert "Oportunidades activas" in etiquetas and "Cierran en ≤ 7 días" in etiquetas


def test_botones_favorita_archivar_restaurar_reintentar(app_db):
    at = _app()
    _boton(at, "fav_A").click().run()
    assert app_db.obtener_licitacion("A")["estado"] == "favorita"
    _boton(at, "re_R").click().run()
    assert app_db.obtener_licitacion("R")["estado"] == "analizado"
    _boton(at, "retry_E").click().run()
    assert app_db.obtener_licitacion("E")["estado"] == "pendiente"
    _boton(at, "arc_N").click().run()
    assert app_db.obtener_licitacion("N")["estado"] == "archivada"
    assert not at.exception


def test_filtro_de_texto_en_la_ui(app_db):
    at = _app()
    at.text_input(key="f_txt_analizadas").input("prueba A").run()
    assert not at.exception
    assert any(e.label.endswith("cierra en 5 días") and "prueba A" in e.label for e in at.expander)
    assert not any("prueba C" in e.label for e in at.expander)


def test_notas_persisten(app_db):
    at = _app()
    at.text_area(key="txt_F").input("Costos revisados")
    at.checkbox(key="chk_bases_leidas_F").check()
    next(b for b in at.button if "Guardar notas" in b.label).click().run()
    fila = app_db.obtener_licitacion("F")
    assert fila["notas"] == "Costos revisados"
    assert json.loads(fila["checklist_json"])["bases_leidas"] is True
    # Nueva sesión: los valores se recargan desde la BD
    at2 = _app()
    assert at2.text_area(key="txt_F").value == "Costos revisados"


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


def test_boton_reanalizar_guarda_nuevo_analisis(app_db, monkeypatch):
    import core.ai_analyst as ai
    _con_ficha(app_db, "F")
    llamadas = []

    def analizar_falso(self, id_ext):
        llamadas.append(id_ext)
        data = {"score_ia": 4, "veredicto": "nuevo", "puntos_criticos": [], "riesgos": []}
        self.db.guardar_analisis_ia(id_ext, 4, data, modelo="m", prompt_version="v")
        return data

    monkeypatch.setenv("GEMINI_API_KEY", "falsa")
    monkeypatch.setattr(ai.genai, "configure", lambda **kw: None)
    monkeypatch.setattr(ai.genai, "GenerativeModel", lambda *a, **kw: object())
    monkeypatch.setattr(ai.AIAnalyst, "analizar_licitacion", analizar_falso)
    at = _app()
    _boton(at, "iaf_F").click().run()
    assert llamadas == ["F"]
    fila = app_db.obtener_licitacion("F")
    assert fila["score_ia"] == 4 and fila["estado"] == "favorita" and json.loads(fila["analisis_ia_json"])["veredicto"] == "nuevo"
    assert any("re-analizada" in s.value for s in at.success)


def test_boton_reanalizar_fallido_conserva_anterior(app_db, monkeypatch):
    import core.ai_analyst as ai
    _con_ficha(app_db, "F")

    def analizar_roto(self, id_ext):
        raise ai.AnalisisFallido("Respuesta de IA inválida")

    monkeypatch.setenv("GEMINI_API_KEY", "falsa")
    monkeypatch.setattr(ai.genai, "configure", lambda **kw: None)
    monkeypatch.setattr(ai.genai, "GenerativeModel", lambda *a, **kw: object())
    monkeypatch.setattr(ai.AIAnalyst, "analizar_licitacion", analizar_roto)
    antes = app_db.obtener_licitacion("F")
    at = _app()
    _boton(at, "iaf_F").click().run()
    despues = app_db.obtener_licitacion("F")
    assert (despues["score_ia"], despues["analisis_ia_json"]) == (antes["score_ia"], antes["analisis_ia_json"])
    assert any("se conserva el análisis anterior" in e.value for e in at.error)


def test_boton_reanalizar_solo_si_hay_ficha(app_db):
    at = _app()
    assert not any(b.key == "iaf_F" for b in at.button)   # Sin texto extraído no hay nada que re-analizar


def test_guardar_perfil(app_db):
    at = _app()
    next(ta for ta in at.text_area if ta.label == "Keywords Positivas").input("reactivos, ")
    next(b for b in at.button if "Guardar Cambios" in b.label).click().run()
    assert app_db.obtener_perfil()["keywords_pos"] == "reactivos, "
    assert not at.exception


def test_panorama_con_ejecuciones_y_evaluaciones(app_db):
    inicio = datetime.now()
    app_db.registrar_ejecucion({"total_listado": 1100, "descubiertas": 6, "registradas": 6, "analizadas": 4, "fallidas": 0},
                               inicio, inicio, inicio.strftime("%Y-%m-%d"))
    for i in range(12):   # Supera el mínimo para dibujar la calibración
        id_ = f"EV{i}"
        app_db.guardar_licitacion({"id_externo": id_, "titulo": f"Evaluada {i}"})
        app_db.guardar_analisis_ia(id_, 3 + i % 7, {"veredicto": "ok"})
        app_db.guardar_evaluacion(id_, "acertado", ("si", "no", "tal_vez")[i % 3])
    at = _app()
    assert not at.exception
    textos = " ".join(m.value for m in at.markdown)
    assert "Embudo de filtrado" in textos and "Calibración" in textos
    assert not any("evaluaciones necesarias" in i.value for i in at.info)
