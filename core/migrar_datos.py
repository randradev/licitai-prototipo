# -*- coding: utf-8 -*-
"""
Módulo: Migración de Datos Existentes (migrar_datos)
---------------------------------------------------
Corrige los registros guardados por versiones anteriores usando el texto de la
ficha que ya está almacenado (no hace scraping ni llamadas a la IA):

- fecha_publicacion: fecha real de la ficha en ISO (antes se guardaba la fecha
  de procesamiento en formato dd/mm/aaaa). Si no aparece en la ficha -> NULL.
- organismo / titulo: solo si están vacíos o son marcadores de posición.
- reclamos_pago_n y region: extraídos literalmente de la ficha.

No borra filas ni toca los análisis de IA. Por defecto solo muestra los cambios
(modo simulación); con --aplicar crea antes una copia de seguridad de la BD.

Uso:
    python -m core.migrar_datos            # Simulación
    python -m core.migrar_datos --aplicar  # Copia de seguridad + aplicar
"""

import argparse
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from core import config
from core.database_mgr import DatabaseManager
from core.parsing import extraer_metadatos_ficha, es_valor_util


def crear_respaldo(db_path):
    """Copiar la BD con la API de backup de SQLite. Devuelve la ruta del respaldo."""
    base, ext = os.path.splitext(db_path)
    destino = f"{base}.backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}{ext or '.db'}"
    origen = sqlite3.connect(db_path)
    copia = sqlite3.connect(destino)
    try:
        origen.backup(copia)
    finally:
        copia.close()
        origen.close()
    return destino


def calcular_cambios(fila):
    """
    Calcular las columnas a corregir de una fila (función pura).

    Returns:
        dict: {columna: nuevo_valor} solo con los valores que cambian.
    """
    meta = extraer_metadatos_ficha(fila.get('descripcion_pro'))
    cambios = {}

    # La fecha previa era la de procesamiento: se reemplaza por la de la ficha o NULL
    if fila.get('fecha_publicacion') != meta['fecha_publicacion']:
        cambios['fecha_publicacion'] = meta['fecha_publicacion']

    if not es_valor_util(fila.get('organismo')) and meta['organismo']:
        cambios['organismo'] = meta['organismo']
    if not es_valor_util(fila.get('titulo')) and meta['titulo']:
        cambios['titulo'] = meta['titulo']
    for col in ('reclamos_pago_n', 'region'):
        if meta[col] is not None and fila.get(col) != meta[col]:
            cambios[col] = meta[col]
    return cambios


def migrar(db_path, aplicar=False):
    """
    Ejecutar la migración sobre la BD indicada.

    Returns:
        tuple: (dict id -> cambios, ruta del respaldo o None)
    """
    # Lectura en modo solo lectura: la simulación no modifica ni el esquema
    ro = sqlite3.connect(f"{Path(db_path).resolve().as_uri()}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row
    try:
        filas = [dict(f) for f in ro.execute("SELECT * FROM licitaciones")]
    finally:
        ro.close()

    todos = {}
    for fila in filas:
        cambios = calcular_cambios(fila)
        if cambios:
            todos[fila['id_externo']] = cambios

    respaldo = None
    if aplicar and todos:
        respaldo = crear_respaldo(db_path)
        DatabaseManager(db_path)  # Agrega las columnas nuevas (solo ADD COLUMN) tras el respaldo
        conn = sqlite3.connect(db_path)
        try:
            for id_ext, cambios in todos.items():
                sets = ", ".join(f"{col} = ?" for col in cambios)
                conn.execute(f"UPDATE licitaciones SET {sets} WHERE id_externo = ?", [*cambios.values(), id_ext])
            conn.commit()
        finally:
            conn.close()
    return todos, respaldo


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Corregir datos existentes desde el texto de las fichas.")
    parser.add_argument("--aplicar", action="store_true", help="Aplicar los cambios (crea un respaldo antes).")
    parser.add_argument("--db", default=None, help="Ruta de la BD (por defecto DATABASE_PATH).")
    args = parser.parse_args()

    ruta = args.db or config.ruta_db()
    if not os.path.exists(ruta):
        raise SystemExit(f"No existe la base de datos: {ruta}")

    cambios, respaldo = migrar(ruta, aplicar=args.aplicar)
    for id_ext, c in cambios.items():
        print(f"{id_ext}: {c}")
    print(f"\n{len(cambios)} licitaciones con cambios.")
    if args.aplicar:
        print(f"✅ Cambios aplicados. Respaldo: {respaldo}" if respaldo else "Nada que aplicar.")
    else:
        print("Modo simulación: no se modificó nada. Ejecuta con --aplicar para guardar los cambios.")
