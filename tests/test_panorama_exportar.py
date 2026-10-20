# -*- coding: utf-8 -*-
"""Preparación de datos de los gráficos, exportación, trazabilidad, evaluación y registro de ejecuciones."""

import csv
import io
import json
from datetime import datetime

import pytest

from core.ai_analyst import AIAnalyst, PROMPT_VERSION
from core.exportar import a_csv, a_json, COLUMNAS_CSV
from core.parsing import dias_para_cierre
from main import ejecutar_pipeline
from tests.test_ai import ModeloFalso, VALIDO
from tests.test_pipeline import ScraperFalso, AnalistaFalso, _listado
from web import panorama

AHORA = datetime(2026, 10, 20, 12, 0)


def _l(id_, estado="analizado", score=8, creada="2026-10-20 15:00:00", **kw):
    base = {"id_externo": id_, "estado": estado, "score_ia": score, "fecha_creacion": creada, "titulo": f"Lic {id_}",
            "analisis_ia_json": '{"veredicto": "ok"}' if score is not None else None}
    base.update(kw)
    return base


# --- parsing ---

def test_dias_para_cierre():
    assert dias_para_cierre("2026-10-20T18:00:00", AHORA) == 0
    assert dias_para_cierre("2026-10-23T09:00:00", AHORA) == 3
    assert dias_para_cierre("2026-10-20T09:00:00", AHORA) == -1   # Cerró hoy más temprano
    assert dias_para_cierre("2026-10-01T09:00:00", AHORA) == -19
    assert dias_para_cierre(None, AHORA) is None


# --- Embudo ---

def test_embudo_sin_ejecuciones_es_none():
    assert panorama.datos_embudo([_l("A")], [], ahora=AHORA) is None


def test_embudo_no_duplica_ejecuciones_del_mismo_dia_y_excluye_previas():
    ejecuciones = [{"fecha_consulta": "2026-10-20", "total_listado": 1100},
                   {"fecha_consulta": "2026-10-20", "total_listado": 1109},   # Segunda ejecución del día
                   {"fecha_consulta": "2026-10-19", "total_listado": 900}]
    licits = [_l("A"), _l("B", estado="favorita"), _l("C", score=None, estado="pendiente"),
              _l("VIEJA", creada="2026-02-05 10:00:00")]   # Anterior a la primera ejecución registrada
    etapas = {e["etapa"]: e["cantidad"] for e in panorama.datos_embudo(licits, ejecuciones, ahora=AHORA)}
    assert etapas == {"Publicadas en el portal": 2009, "Coinciden con tu perfil": 3, "Analizadas por la IA": 2, "Favoritas": 1}


def test_embudo_respeta_periodo():
    ejecuciones = [{"fecha_consulta": "2026-10-20", "total_listado": 1000}, {"fecha_consulta": "2026-09-01", "total_listado": 500}]
    licits = [_l("A"), _l("B", creada="2026-09-01 10:00:00")]
    etapas = {e["etapa"]: e["cantidad"] for e in panorama.datos_embudo(licits, ejecuciones, dias=7, ahora=AHORA)}
    assert etapas["Publicadas en el portal"] == 1000 and etapas["Coinciden con tu perfil"] == 1


# --- Calendario, riesgo, histograma ---

def test_calendario_solo_activas_abiertas_ordenadas():
    licits = [_l("TARDE", fecha_cierre="2026-11-30T10:00:00", fecha_publicacion="2026-10-01"),
              _l("PRONTO", estado="favorita", fecha_cierre="2026-10-22T10:00:00"),
              _l("CERRADA", fecha_cierre="2026-10-01T10:00:00"),
              _l("ARCH", estado="archivada", fecha_cierre="2026-11-01T10:00:00"),
              _l("SINFECHA", fecha_cierre=None)]
    filas = panorama.datos_calendario(licits, AHORA)
    assert [f["id_externo"] for f in filas] == ["PRONTO", "TARDE"]
    assert filas[0]["favorita"] and filas[0]["dias"] == 2
    assert filas[0]["inicio"].date().isoformat() == "2026-10-20"   # Sin publicación: usa la fecha de registro


def test_calendario_titulos_repetidos_no_comparten_fila_y_detalle_legible():
    licits = [_l("A", fecha_cierre="2026-10-21T10:00:00", titulo="Reactivos"),
              _l("B", fecha_cierre="2026-10-30T10:00:00", titulo="Reactivos", score=None),
              _l("C", fecha_cierre="2026-10-20T18:00:00", titulo="Microscopio")]
    filas = panorama.datos_calendario(licits, AHORA)
    assert [f["fila"] for f in filas] == ["Microscopio", "Reactivos (A)", "Reactivos (B)"]
    assert len({f["fila"] for f in filas}) == 3
    assert [f["detalle"] for f in filas] == ["Cierra el 20/10 · hoy · score 8", "Cierra el 21/10 · mañana · score 8",
                                             "Cierra el 30/10 · en 10 días"]


def test_calendario_alto_por_fila_fijo():
    """El alto crece con la cantidad de filas (paso fijo): con pocas filas no se encima nada."""
    licits = [_l(i, fecha_cierre="2026-10-25T10:00:00", titulo=f"T{i}") for i in "ABC"]
    spec = panorama.grafico_calendario(panorama.datos_calendario(licits, AHORA), panorama.TEMAS["dark"], AHORA).to_dict()
    assert spec["height"] == {"step": 38}


def test_eje_de_conteo_sin_marcas_repetidas():
    assert panorama._eje_conteo(1).to_dict()["values"] == [0, 1]
    assert panorama._eje_conteo(4).to_dict()["values"] == [0, 1, 2, 3, 4]
    assert "values" not in panorama._eje_conteo(25).to_dict()


def test_riesgo_requiere_score_y_reclamos():
    licits = [_l("A", reclamos_pago_n=80), _l("B", reclamos_pago_n=None), _l("C", score=None, reclamos_pago_n=5),
              _l("D", estado="pendiente", reclamos_pago_n=5)]
    assert [f["id_externo"] for f in panorama.datos_riesgo(licits)] == ["A"]


def test_histograma_incluye_todos_los_valores():
    filas = panorama.datos_histograma([_l("A", score=8), _l("B", score=8), _l("C", score=3), _l("D", score=None)])
    assert len(filas) == 10 and {f["score"]: f["cantidad"] for f in filas}[8] == 2
    assert sum(f["cantidad"] for f in filas) == 3


def test_calibracion_por_tramo():
    licits = ([_l(f"S{i}", score=9, eval_postularia="si", eval_score="acertado") for i in range(3)]
              + [_l("N9", score=9, eval_postularia="no", eval_score="muy_alto")]
              + [_l("N3", score=3, eval_postularia="no", eval_score="acertado"), _l("SIN", score=7)])
    datos = panorama.datos_calibracion(licits)
    tramos = {t["tramo"]: t for t in datos["tramos"]}
    assert datos["total"] == 5
    assert tramos["9–10"]["n"] == 4 and tramos["9–10"]["pct_si"] == 75
    assert tramos["1–4"]["pct_si"] == 0 and tramos["5–6"]["pct_si"] is None
    assert datos["eval_score"] == {"acertado": 4, "muy_alto": 1, "muy_bajo": 0}


@pytest.mark.parametrize("tema", ["light", "dark"])
def test_graficos_se_construyen(tema):
    """Cada constructor produce una especificación Vega-Lite válida en ambos temas."""
    t = panorama.TEMAS[tema]
    licits = [_l("A", reclamos_pago_n=80, fecha_cierre="2026-11-01T10:00:00", eval_postularia="si")]
    graficos = [
        panorama.grafico_embudo(panorama.datos_embudo(licits, [{"fecha_consulta": "2026-10-20", "total_listado": 10}], ahora=AHORA), t),
        panorama.grafico_calendario(panorama.datos_calendario(licits, AHORA), t, AHORA),
        panorama.grafico_riesgo(panorama.datos_riesgo(licits), t),
        panorama.grafico_histograma(panorama.datos_histograma(licits), t),
        panorama.grafico_calibracion(panorama.datos_calibracion(licits)["tramos"], t),
    ]
    for g in graficos:
        assert "$schema" in g.to_dict()


# --- Exportación ---

FILA = {"id_externo": "X", "estado": "favorita", "titulo": "Reactivos", "organismo": "Hospital", "region": "Maule",
        "fecha_publicacion": "2026-10-20", "fecha_cierre": "2026-11-01T10:00:00", "link": "http://x", "reclamos_pago_n": 80,
        "score_ia": 8, "analisis_ia_json": json.dumps({"veredicto": "ok", "puntos_criticos": ["a", "b"], "riesgos": "r"}),
        "reclamo_pago": "Interpretación", "analisis_modelo": "m", "analisis_prompt_version": "v", "analisis_fecha": "2026-10-20T10:00:00",
        "eval_score": "acertado", "eval_postularia": "si", "eval_comentario": "bien", "eval_fecha": "2026-10-20T11:00:00",
        "notas": "PRIVADO", "checklist_json": '{"bases_leidas": true}', "descripcion_pro": "TEXTO FICHA"}


def test_json_separa_procedencia_y_excluye_privados():
    doc = json.loads(a_json([FILA], ahora=AHORA))
    assert doc["version_esquema"] == 1 and doc["cantidad"] == 1 and doc["exportado"] == "2026-10-20T12:00:00"
    r = doc["licitaciones"][0]
    assert r["fuente"]["reclamos_pago_n"] == 80
    assert r["analisis"]["riesgos"] == ["r"] and r["analisis"]["interpretacion_pago"] == "Interpretación"
    assert r["evaluacion"] == {"score": "acertado", "postularia": "si", "comentario": "bien", "fecha": "2026-10-20T11:00:00"}
    texto = json.dumps(doc)
    assert "PRIVADO" not in texto and "bases_leidas" not in texto and "TEXTO FICHA" not in texto
    assert json.loads(a_json([FILA], incluir_ficha=True))["licitaciones"][0]["fuente"]["texto_ficha"] == "TEXTO FICHA"


def test_json_sin_analisis_ni_evaluacion():
    r = json.loads(a_json([{"id_externo": "Y", "estado": "analizado"}]))["licitaciones"][0]
    assert r["analisis"] is None and r["evaluacion"] is None


def test_csv_plano():
    filas = list(csv.DictReader(io.StringIO(a_csv([FILA]))))
    assert list(filas[0].keys()) == COLUMNAS_CSV
    assert filas[0]["puntos_criticos"] == "a | b" and filas[0]["eval_postularia"] == "si"
    assert "PRIVADO" not in a_csv([FILA]) and "TEXTO FICHA" not in a_csv([FILA])


# --- Trazabilidad, evaluación y ejecuciones en la BD ---

def test_analisis_guarda_trazabilidad(db_con_perfil):
    db = db_con_perfil
    db.guardar_licitacion({"id_externo": "X", "titulo": "T"})
    db.actualizar_detalle_profundo("X", None, "texto")
    AIAnalyst(db, modelo=ModeloFalso(json.dumps(VALIDO))).analizar_licitacion("X")
    fila = db.obtener_licitacion("X")
    assert fila["analisis_modelo"] and fila["analisis_prompt_version"] == PROMPT_VERSION
    assert datetime.fromisoformat(fila["analisis_fecha"])


def test_evaluacion_valida_e_invalida(db):
    db.guardar_licitacion({"id_externo": "X", "titulo": "T"})
    db.guardar_evaluacion("X", "muy_bajo", "no", "  ")
    fila = db.obtener_licitacion("X")
    assert fila["eval_score"] == "muy_bajo" and fila["eval_postularia"] == "no" and fila["eval_comentario"] is None
    with pytest.raises(ValueError):
        db.guardar_evaluacion("X", "excelente", "si")
    with pytest.raises(ValueError):
        db.guardar_evaluacion("X", "acertado", "quizas")


def test_reanalisis_conserva_evaluacion_y_queda_desactualizada(db):
    from web import vistas as app
    db.guardar_licitacion({"id_externo": "X", "titulo": "T"})
    db.guardar_analisis_ia("X", 7, {"veredicto": "a"})
    db.guardar_evaluacion("X", "acertado", "si")
    # Re-análisis posterior (forzamos un instante posterior para no depender del reloj)
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    conn.execute("UPDATE licitaciones SET eval_fecha = '2000-01-01T00:00:00' WHERE id_externo = 'X'")
    conn.commit(); conn.close()
    db.guardar_analisis_ia("X", 8, {"veredicto": "b"})
    fila = db.obtener_licitacion("X")
    assert fila["eval_score"] == "acertado" and app.evaluacion_desactualizada(fila)


def test_pipeline_registra_ejecucion(db_con_perfil):
    db = db_con_perfil
    ejecutar_pipeline(db=db, scraper=ScraperFalso(db, _listado(3) + _listado(2, "X", nombre="Otra cosa")),
                      analyst=AnalistaFalso(db), max_procesar=5, max_intentos=3, pausa=0, ahora=datetime(2026, 2, 10))
    ejecuciones = db.obtener_ejecuciones()
    assert len(ejecuciones) == 1
    e = ejecuciones[0]
    assert (e["total_listado"], e["relevantes"], e["registradas"], e["analizadas"]) == (5, 3, 3, 3)


def test_pipeline_bloqueado_no_registra_ejecucion(db_con_perfil):
    open(db_con_perfil.db_path + ".lock", "w").close()
    ejecutar_pipeline(db=db_con_perfil, scraper=object(), analyst=object())
    assert db_con_perfil.obtener_ejecuciones() == []
