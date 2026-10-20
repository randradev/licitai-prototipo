# -*- coding: utf-8 -*-
"""
Módulo: Exportación de Datos (exportar)
--------------------------------------
Convierte las licitaciones guardadas en un formato limpio e independiente del
esquema SQLite, pensado para precargar la demo pública y migrar a la V2.

Separa explícitamente el origen de cada dato:
- `fuente`: datos tomados literalmente de Mercado Público.
- `analisis`: salida de la IA (con su trazabilidad).
- `evaluacion`: juicio humano sobre el análisis.

Las notas internas y el checklist NO se exportan: son de gestión privada.
"""

import csv
import io
import json
from datetime import datetime

from core.parsing import cargar_analisis_guardado

VERSION_ESQUEMA = 1

COLUMNAS_CSV = [
    "id_externo", "titulo", "organismo", "region", "estado", "fecha_publicacion", "fecha_cierre", "link",
    "reclamos_pago_n", "score_ia", "veredicto", "puntos_criticos", "riesgos", "motivo_archivo",
    "interpretacion_pago_ia", "analisis_modelo", "analisis_prompt_version", "analisis_fecha",
    "eval_score", "eval_postularia", "eval_comentario", "eval_fecha",
]


def registro_exportable(licit, incluir_ficha=False):
    """Construir el registro exportable de una licitación (función pura)."""
    analisis = cargar_analisis_guardado(licit.get("analisis_ia_json"))
    registro = {
        "id_externo": licit["id_externo"],
        "estado": licit.get("estado"),
        "fuente": {
            "titulo": licit.get("titulo"),
            "organismo": licit.get("organismo"),
            "region": licit.get("region"),
            "fecha_publicacion": licit.get("fecha_publicacion"),
            "fecha_cierre": licit.get("fecha_cierre"),
            "link": licit.get("link"),
            "reclamos_pago_n": licit.get("reclamos_pago_n"),
        },
        "analisis": None,
        "evaluacion": None,
    }
    if analisis:
        registro["analisis"] = {
            "score_ia": licit.get("score_ia"),
            "veredicto": analisis.get("veredicto"),
            "puntos_criticos": analisis.get("puntos_criticos", []),
            "riesgos": analisis.get("riesgos", []),
            "motivo_archivo": licit.get("motivo_archivo"),
            "interpretacion_pago": licit.get("reclamo_pago"),
            "modelo": licit.get("analisis_modelo"),
            "prompt_version": licit.get("analisis_prompt_version"),
            "fecha": licit.get("analisis_fecha"),
        }
    if licit.get("eval_score") or licit.get("eval_postularia"):
        registro["evaluacion"] = {
            "score": licit.get("eval_score"),
            "postularia": licit.get("eval_postularia"),
            "comentario": licit.get("eval_comentario"),
            "fecha": licit.get("eval_fecha"),
        }
    if incluir_ficha:
        registro["fuente"]["texto_ficha"] = licit.get("descripcion_pro")
    return registro


def a_json(licitaciones, incluir_ficha=False, ahora=None):
    """Serializar a JSON con metadatos de la exportación."""
    documento = {
        "version_esquema": VERSION_ESQUEMA,
        "exportado": (ahora or datetime.now()).isoformat(timespec="seconds"),
        "cantidad": len(licitaciones),
        "licitaciones": [registro_exportable(l, incluir_ficha) for l in licitaciones],
    }
    return json.dumps(documento, ensure_ascii=False, indent=2)


def a_csv(licitaciones):
    """Serializar a CSV plano (sin el texto de la ficha). Las listas se unen con ' | '."""
    salida = io.StringIO()
    escritor = csv.DictWriter(salida, fieldnames=COLUMNAS_CSV, extrasaction="ignore")
    escritor.writeheader()
    for l in licitaciones:
        r = registro_exportable(l)
        f, a, e = r["fuente"], r["analisis"] or {}, r["evaluacion"] or {}
        escritor.writerow({
            "id_externo": r["id_externo"], "estado": r["estado"], **{k: f.get(k) for k in
            ("titulo", "organismo", "region", "fecha_publicacion", "fecha_cierre", "link", "reclamos_pago_n")},
            "score_ia": a.get("score_ia"), "veredicto": a.get("veredicto"),
            "puntos_criticos": " | ".join(a.get("puntos_criticos", [])),
            "riesgos": " | ".join(a.get("riesgos", [])),
            "motivo_archivo": a.get("motivo_archivo"), "interpretacion_pago_ia": a.get("interpretacion_pago"),
            "analisis_modelo": a.get("modelo"), "analisis_prompt_version": a.get("prompt_version"),
            "analisis_fecha": a.get("fecha"),
            "eval_score": e.get("score"), "eval_postularia": e.get("postularia"),
            "eval_comentario": e.get("comentario"), "eval_fecha": e.get("fecha"),
        })
    return salida.getvalue()
