# -*- coding: utf-8 -*-
"""Helpers de presentación y botones principales con streamlit.testing (BD temporal)."""

import json
import os
import sqlite3

import pytest
from streamlit.testing.v1 import AppTest

from core.database_mgr import DatabaseManager

APP = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "app.py")


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


def test_agrupar_por_fecha_cronologico(helpers):
    lista = [{"fecha_publicacion": f, "id_externo": f or "n"} for f in ["2026-09-30", None, "2027-01-10", "2026-02-09"]]
    etiquetas = [e for e, _ in helpers.agrupar_por_fecha(lista)]
    assert etiquetas == ["Publicadas el 10/01/2027", "Publicadas el 30/09/2026", "Publicadas el 09/02/2026",
                         "Fecha de publicación no disponible"]


def test_titulo_de(helpers):
    assert helpers.titulo_de({"id_externo": "X", "titulo": "Sin título"}, {"titulo_recuperado": "IA"}) == "IA"
    assert helpers.titulo_de({"id_externo": "X", "titulo": "Real"}, {"titulo_recuperado": "IA"}) == "Real"
    assert helpers.titulo_de({"id_externo": "X", "titulo": None}) == "Licitación X"


# --- App completa ---

@pytest.fixture
def app_db(tmp_path, monkeypatch):
    path = str(tmp_path / "ui.db")
    monkeypatch.setenv("DATABASE_PATH", path)
    db = DatabaseManager(path)
    # Incluye casos que antes rompían la UI: score NULL, JSON corrupto, lista guardada como texto
    analisis = json.dumps({"veredicto": "ok", "puntos_criticos": "texto suelto", "riesgos": ["r"]})
    filas = [("A", "analizado", 8, analisis), ("N", "analizado", None, None), ("C", "analizado", 5, "{corrupto"),
             ("F", "favorita", 9, analisis), ("R", "archivada", 3, analisis), ("E", "error", None, None)]
    conn = sqlite3.connect(path)
    conn.executemany(
        "INSERT INTO licitaciones (id_externo, titulo, fecha_publicacion, estado, score_ia, analisis_ia_json, ultimo_error)"
        " VALUES (?, ?, '2026-02-05', ?, ?, ?, ?)",
        [(i, f"Licitación de prueba {i}", e, s, a, "Timeout" if e == "error" else None) for i, e, s, a in filas])
    conn.commit()
    conn.close()
    return db


def _boton(at, key):
    return next(b for b in at.button if b.key == key)


def test_app_renderiza_sin_excepciones_con_datos_problematicos(app_db):
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("Configura al menos una keyword" in w.value for w in at.sidebar.warning)


def test_botones_favorita_archivar_restaurar_reintentar(app_db):
    at = AppTest.from_file(APP, default_timeout=30).run()
    _boton(at, "fav_A").click().run()
    assert app_db.obtener_licitacion("A")["estado"] == "favorita"
    _boton(at, "re_R").click().run()
    assert app_db.obtener_licitacion("R")["estado"] == "analizado"
    _boton(at, "retry_E").click().run()
    assert app_db.obtener_licitacion("E")["estado"] == "pendiente"
    _boton(at, "arc_N").click().run()
    assert app_db.obtener_licitacion("N")["estado"] == "archivada"
    assert not at.exception


def test_notas_persisten(app_db):
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_area(key="txt_F").input("Costos revisados")
    at.checkbox(key="chk_bases_leidas_F").check()
    next(b for b in at.button if "Guardar notas" in b.label).click().run()
    fila = app_db.obtener_licitacion("F")
    assert fila["notas"] == "Costos revisados"
    assert json.loads(fila["checklist_json"])["bases_leidas"] is True
    # Nueva sesión: los valores se recargan desde la BD
    at2 = AppTest.from_file(APP, default_timeout=30).run()
    assert at2.text_area(key="txt_F").value == "Costos revisados"


def test_guardar_perfil(app_db):
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.sidebar.text_area[0].input("reactivos, ")
    next(b for b in at.sidebar.button if "Guardar Cambios" in b.label).click().run()
    assert app_db.obtener_perfil()["keywords_pos"] == "reactivos, "
    assert not at.exception
