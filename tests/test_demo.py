# -*- coding: utf-8 -*-
"""Modo demo pública (LICITAI_DEMO / LICITAI_DEMO_FECHA; ver DEMO.md). Sin las variables, nada cambia."""

import sqlite3
from datetime import date, datetime

import pytest

from core import config
from core.parsing import dias_para_cierre, esta_cerrada
from test_ui import _app, _boton, app_db  # noqa: F401  (app_db es una fixture)


@pytest.fixture
def app_db_con_ficha(app_db):
    """Con texto de ficha y perfil, para que aparezcan «Actualizar análisis» y el re-análisis por lote."""
    app_db.guardar_perfil("prueba", "", None, "Empresa de prueba")
    conn = sqlite3.connect(app_db.db_path)
    conn.execute("UPDATE licitaciones SET descripcion_pro = 'Texto de la ficha' WHERE id_externo IN ('A', 'F')")
    conn.commit()
    conn.close()
    return app_db


@pytest.mark.parametrize("modo_demo", [False, True])
def test_botones_de_ia_y_sincronizacion(app_db_con_ficha, monkeypatch, modo_demo):
    monkeypatch.setattr(config, "MODO_DEMO", modo_demo)
    claves = {None: ["btn_sync", "ia_A"], "perfil": ["btn_reanalizar_lote"], "cola": ["btn_sync", "now_E"]}
    for pagina, botones in claves.items():
        at = _app(pagina)
        assert not at.exception, pagina
        if pagina == "perfil":   # El lote además exige confirmar; se confirma para aislar el efecto del modo demo
            at.checkbox(key="conf_reanalisis").check().run()
        for clave in botones:
            boton = _boton(at, clave)
            assert boton.disabled == modo_demo, clave
        assert any("Demo pública" in i.value for i in at.info) == modo_demo, pagina


def test_demo_no_bloquea_la_gestion(app_db, monkeypatch):
    """En la demo se puede seguir marcando favoritas, archivando y restaurando."""
    monkeypatch.setattr(config, "MODO_DEMO", True)
    at = _app()
    _boton(at, "fav_A").click().run()
    assert app_db.obtener_licitacion("A")["estado"] == "favorita"


def test_fecha_demo_fija_el_momento_actual(monkeypatch):
    monkeypatch.setattr(config, "FECHA_DEMO", date(2026, 10, 23))
    assert config.ahora().date() == date(2026, 10, 23)
    assert dias_para_cierre("2026-10-27T10:00:00") == 4
    assert not esta_cerrada("2026-10-27T10:00:00")


def test_sin_fecha_demo_se_usa_la_actual(monkeypatch):
    monkeypatch.setattr(config, "FECHA_DEMO", None)
    assert abs((config.ahora() - datetime.now()).total_seconds()) < 5


@pytest.mark.parametrize("valor, esperado", [("2026-10-23", date(2026, 10, 23)), (" 2026-10-23 ", date(2026, 10, 23)),
                                             ("", None), ("23/10/2026", None)])
def test_env_fecha(monkeypatch, valor, esperado):
    monkeypatch.setenv("LICITAI_PRUEBA_FECHA", valor)
    assert config._env_fecha("LICITAI_PRUEBA_FECHA") == esperado
