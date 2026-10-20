# -*- coding: utf-8 -*-
import os
import sqlite3
from pathlib import Path

from core.migrar_datos import calcular_cambios, migrar
from tests.conftest import FICHA_EJEMPLO
from tests.test_database import ESQUEMA_ANTIGUO


def _bd_antigua(path):
    conn = sqlite3.connect(path)
    conn.execute(ESQUEMA_ANTIGUO)
    conn.executemany(
        "INSERT INTO licitaciones (id_externo, titulo, organismo, fecha_publicacion, descripcion_pro, estado, score_ia, analisis_ia_json)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("CON-FICHA", "Título IA", None, "09/02/2026", FICHA_EJEMPLO, "analizado", 8, '{"veredicto": "ok"}'),
            ("SIN-FICHA", "Pendiente", "No disponible", "Procesando...", None, "pendiente", None, None),
        ])
    conn.commit()
    conn.close()


def test_calcular_cambios_usa_la_ficha():
    cambios = calcular_cambios({"fecha_publicacion": "09/02/2026", "organismo": None, "titulo": "T",
                                "descripcion_pro": FICHA_EJEMPLO})
    assert cambios == {"fecha_publicacion": "2026-02-05", "organismo": "HOSPITAL DE PRUEBA",
                       "reclamos_pago_n": 181, "region": "Región de los Lagos"}


def test_simulacion_no_modifica_nada(tmp_path):
    path = str(tmp_path / "vieja.db")
    _bd_antigua(path)
    antes = Path(path).read_bytes()
    cambios, respaldo = migrar(path, aplicar=False)
    assert respaldo is None and set(cambios) == {"CON-FICHA", "SIN-FICHA"}
    assert Path(path).read_bytes() == antes


def test_aplicar_crea_respaldo_y_corrige_sin_borrar(tmp_path):
    path = str(tmp_path / "vieja.db")
    _bd_antigua(path)
    _, respaldo = migrar(path, aplicar=True)
    assert respaldo and os.path.exists(respaldo)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    filas = {r["id_externo"]: dict(r) for r in conn.execute("SELECT * FROM licitaciones")}
    conn.close()
    assert len(filas) == 2
    con = filas["CON-FICHA"]
    assert con["fecha_publicacion"] == "2026-02-05" and con["organismo"] == "HOSPITAL DE PRUEBA"
    assert con["reclamos_pago_n"] == 181 and con["score_ia"] == 8 and con["analisis_ia_json"] == '{"veredicto": "ok"}'
    assert filas["SIN-FICHA"]["fecha_publicacion"] is None

    # Idempotente: una segunda pasada no encuentra cambios
    assert migrar(path, aplicar=True) == ({}, None)
