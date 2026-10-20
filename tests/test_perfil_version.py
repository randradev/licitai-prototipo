# -*- coding: utf-8 -*-
"""Versión del perfil: registro en cada análisis, detección de análisis desalineados y acciones correctivas."""

import json
import os
import sqlite3

import pytest
from streamlit.testing.v1 import AppTest

from core.ai_analyst import AIAnalyst, AnalisisFallido, CuotaAgotada
from core.database_mgr import DatabaseManager
from core.parsing import version_perfil
from main import reanalizar_lote
from tests.test_ai import ModeloFalso, VALIDO
from web import vistas

APP = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "app.py")
PERFIL = {"keywords_pos": "reactivos, microscopio", "keywords_neg": "limpieza", "bio_estrategica": "Laboratorio"}


# --- Versión del perfil (función pura) ---

def test_version_estable_ante_cambios_sin_significado():
    v = version_perfil(PERFIL)
    assert len(v) == 8
    assert version_perfil(dict(PERFIL, keywords_pos=" Microscopio,REACTIVOS , ")) == v   # orden, mayúsculas, espacios
    assert version_perfil(dict(PERFIL, bio_estrategica="  Laboratorio \n")) == v


def test_version_cambia_si_cambia_el_significado():
    v = version_perfil(PERFIL)
    assert version_perfil(dict(PERFIL, keywords_pos="reactivos")) != v
    assert version_perfil(dict(PERFIL, keywords_neg="")) != v
    assert version_perfil(dict(PERFIL, bio_estrategica="Otra cosa")) != v
    assert version_perfil(None) is None


# --- Registro en el análisis ---

def _db_con_extraida(tmp_path, ids=("X",)):
    db = DatabaseManager(str(tmp_path / "p.db"))
    db.guardar_perfil(PERFIL["keywords_pos"], PERFIL["keywords_neg"], None, PERFIL["bio_estrategica"])
    for i in ids:
        db.guardar_licitacion({"id_externo": i, "titulo": f"Reactivos {i}"})
        db.actualizar_detalle_profundo(i, None, "Licitación ID: ficha")
    return db


def test_analisis_registra_version_del_perfil(tmp_path):
    db = _db_con_extraida(tmp_path)
    AIAnalyst(db, modelo=ModeloFalso(json.dumps(VALIDO))).analizar_licitacion("X")
    assert db.obtener_licitacion("X")["analisis_perfil_version"] == version_perfil(PERFIL)
    assert f"Versión del perfil: {version_perfil(PERFIL)}" in vistas.detalles_tecnicos(db.obtener_licitacion("X"))


# --- Detección ---

def _l(id_, version, estado="analizado", ficha="ficha", analisis='{"veredicto": "ok"}', titulo="Reactivos"):
    return {"id_externo": id_, "estado": estado, "analisis_perfil_version": version, "descripcion_pro": ficha,
            "analisis_ia_json": analisis, "titulo": titulo}


def test_afectados_por_perfil():
    v = "nueva123"
    licits = [_l("AL_DIA", v), _l("ANTERIOR", "vieja456"), _l("SIN_REGISTRO", None), _l("FAV", "vieja456", estado="favorita"),
              _l("ARCHIVADA", "vieja456", estado="archivada"), _l("SIN_FICHA", "vieja456", ficha=None),
              _l("SIN_ANALISIS", None, estado="pendiente", analisis=None)]
    assert {l["id_externo"] for l in vistas.afectados_por_perfil(licits, v)} == {"ANTERIOR", "SIN_REGISTRO", "FAV"}
    assert not vistas.analisis_con_perfil_anterior(_l("A", v), v)
    assert not vistas.analisis_con_perfil_anterior(_l("B", None, analisis=None), v)


def test_cola_fuera_de_perfil():
    licits = [_l("SIGUE", None, estado="pendiente", titulo="Compra de reactivos"),
              _l("YA_NO", None, estado="pendiente", titulo="Servicio de guardias"),
              _l("NEGATIVA", None, estado="extraido", titulo="Reactivos y limpieza"),
              _l("ANALIZADA", None, estado="analizado", titulo="Servicio de guardias")]
    assert {l["id_externo"] for l in vistas.cola_fuera_de_perfil(licits, PERFIL)} == {"YA_NO", "NEGATIVA"}
    assert vistas.cola_fuera_de_perfil(licits, {"keywords_pos": ""}) == []   # Sin keywords no se quita nada


def test_chip_perfil_anterior_en_tarjeta():
    l = {"id_externo": "X", "titulo": "T", "score_ia": 8}
    assert "perfil anterior" in vistas.html_tarjeta(l, perfil_anterior=True)
    assert "perfil anterior" not in vistas.html_tarjeta(l)


# --- Re-análisis en lote ---

class AnalistaContador:
    def __init__(self, db, fallan=(), cuota_en=None):
        self.db, self.fallan, self.cuota_en, self.llamadas = db, set(fallan), cuota_en, []

    def analizar_licitacion(self, id_ext):
        self.llamadas.append(id_ext)
        if id_ext == self.cuota_en:
            raise CuotaAgotada("429")
        if id_ext in self.fallan:
            raise AnalisisFallido("JSON inválido")
        self.db.guardar_analisis_ia(id_ext, 7, {"veredicto": "nuevo"}, perfil_version="v")


def test_reanalizar_lote(tmp_path):
    db = _db_con_extraida(tmp_path, ("A", "B", "C"))
    progreso = []
    r = reanalizar_lote(db, ["A", "B", "C"], analyst=AnalistaContador(db, fallan={"B"}), al_avanzar=lambda h, t: progreso.append((h, t)))
    assert r["reanalizadas"] == 2 and [i for i, _ in r["fallidas"]] == ["B"] and r["detenido_por"] is None
    assert progreso == [(1, 3), (2, 3), (3, 3)]
    assert not os.path.exists(db.db_path + ".lock")


def test_reanalizar_lote_cuota_detiene(tmp_path):
    db = _db_con_extraida(tmp_path, ("A", "B", "C"))
    analista = AnalistaContador(db, cuota_en="B")
    r = reanalizar_lote(db, ["A", "B", "C"], analyst=analista)
    assert r["reanalizadas"] == 1 and "429" in r["detenido_por"] and analista.llamadas == ["A", "B"]


def test_reanalizar_lote_respeta_bloqueo(tmp_path):
    db = _db_con_extraida(tmp_path)
    open(db.db_path + ".lock", "w").close()
    analista = AnalistaContador(db)
    r = reanalizar_lote(db, ["X"], analyst=analista)
    assert "en curso" in r["detenido_por"] and analista.llamadas == []


# --- Página Perfil ---

@pytest.fixture
def app_perfil(tmp_path, monkeypatch):
    path = str(tmp_path / "ui.db")
    monkeypatch.setenv("DATABASE_PATH", path)
    db = DatabaseManager(path)
    db.guardar_perfil(PERFIL["keywords_pos"], PERFIL["keywords_neg"], None, PERFIL["bio_estrategica"])
    v = version_perfil(PERFIL)
    conn = sqlite3.connect(path)
    conn.executemany(
        "INSERT INTO licitaciones (id_externo, titulo, estado, score_ia, analisis_ia_json, descripcion_pro, analisis_perfil_version)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        [("AL_DIA", "Reactivos 1", "analizado", 8, '{"veredicto": "ok"}', "ficha", v),
         ("VIEJA", "Reactivos 2", "analizado", 8, '{"veredicto": "ok"}', "ficha", "vieja456"),
         ("COLA_NO", "Servicio de guardias", "pendiente", None, None, None, None)])
    conn.commit()
    conn.close()
    return db


def _app_perfil():
    at = AppTest.from_file(APP, default_timeout=30)
    at.switch_page("paginas/perfil.py")
    return at.run()


def test_pagina_perfil_muestra_impacto_y_reanaliza_con_confirmacion(app_perfil, monkeypatch):
    import core.ai_analyst as ai
    llamadas = []

    def analizar_falso(self, id_ext):
        llamadas.append(id_ext)
        self.db.guardar_analisis_ia(id_ext, 6, {"veredicto": "nuevo"}, perfil_version=version_perfil(self.db.obtener_perfil()))

    monkeypatch.setenv("GEMINI_API_KEY", "falsa")
    monkeypatch.setattr(ai.genai, "configure", lambda **kw: None)
    monkeypatch.setattr(ai.genai, "GenerativeModel", lambda *a, **kw: object())
    monkeypatch.setattr(ai.AIAnalyst, "analizar_licitacion", analizar_falso)

    at = _app_perfil()
    assert not at.exception
    boton = next(b for b in at.button if b.key == "btn_reanalizar_lote")
    assert boton.label == "Actualizar 1 análisis" and boton.disabled          # Exige confirmación explícita
    at.checkbox(key="conf_reanalisis").check().run()
    next(b for b in at.button if b.key == "btn_reanalizar_lote").click().run()
    assert llamadas == ["VIEJA"]                                      # Solo el desalineado
    assert app_perfil.obtener_licitacion("VIEJA")["analisis_perfil_version"] == version_perfil(PERFIL)


def test_pagina_perfil_quita_de_la_cola(app_perfil):
    at = _app_perfil()
    next(b for b in at.button if b.key == "btn_quitar_cola").click().run()
    fila = app_perfil.obtener_licitacion("COLA_NO")
    assert fila["estado"] == "error" and "keywords" in fila["ultimo_error"]
    assert app_perfil.obtener_licitacion("VIEJA")["estado"] == "analizado"   # Lo analizado no se toca


def test_cambiar_perfil_marca_analisis_como_anteriores(app_perfil):
    at = _app_perfil()
    next(ta for ta in at.text_area if ta.label == "Describe tu empresa").input("Nueva bio")
    next(b for b in at.button if "Guardar cambios" in b.label).click().run()
    assert any("no cambian" in s.value for s in at.success)
    assert next(b for b in at.button if b.key == "btn_reanalizar_lote").label == "Actualizar 2 análisis"   # Ahora ambos quedan desalineados
