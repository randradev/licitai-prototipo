# -*- coding: utf-8 -*-
"""Rúbrica de idoneidad v1 (core/rubrica.py): cálculo, estados, rangos y lectura de análisis guardados."""

import pytest

from core import rubrica
from core.rubrica import calcular, etiqueta_de, redondear, resultado_guardado, texto_resultado
from tests.test_ai import criterios

EXCLUYENTE_CONFIRMADO = {"requisito": "Registro ISP", "estado": "incumplido_confirmado", "evidencia": "Exige registro ISP"}


def test_pesos_suman_100_y_hay_dos_esenciales():
    assert rubrica.PESO_TOTAL == 100
    assert [c.clave for c in rubrica.CRITERIOS if c.esencial] == ["comercial", "requisitos"]
    assert [c.clave for c in rubrica.CRITERIOS if c.bloqueante] == ["comercial"]   # v1.1


@pytest.mark.parametrize("notas, esperado", [((0, 0, 0, 0, 0), 0), ((5, 5, 5, 5, 5), 100)])
def test_score_minimo_y_maximo(notas, esperado):
    res = calcular(criterios(*notas))
    assert res["score"] == esperado and res["estado"] == "definitivo" and res["cobertura"] == 100


def test_ejemplo_de_la_especificacion():
    # La especificación indica 84, pero su propia fórmula da 83:
    # 35*(5/5) + 25*(4/5) + 20*(4/5) + 10*(3/5) + 10*(3/5) = 35 + 20 + 16 + 6 + 6 = 83.
    res = calcular(criterios(5, 4, 4, 3, 3))
    assert res["score"] == 83 and res["etiqueta"] == "Buena oportunidad" and res["pendientes"] == []


def test_excluyente_confirmado_no_se_compensa():
    res = calcular(criterios(5, 5, 5, 5, 5), [EXCLUYENTE_CONFIRMADO])
    assert res["estado"] == "no_elegible" and res["score"] is None and res["etiqueta"] is None
    assert "Registro ISP" in res["motivo"] and res["incumplidos"] == [EXCLUYENTE_CONFIRMADO]


def test_excluyente_no_verificable_o_sin_evidencia_no_excluye():
    for excl in ({"requisito": "X", "estado": "no_verificable", "evidencia": "No se menciona"},
                 {"requisito": "X", "estado": "incumplido_confirmado", "evidencia": None},
                 {"requisito": "X", "estado": "cumplido", "evidencia": "Lo cumple"}):
        assert calcular(criterios(5, 4, 4, 3, 3), [excl])["estado"] == "definitivo"


def test_no_elegible_prevalece_sobre_evidencia_insuficiente():
    assert calcular(criterios(None, None, 3, 3, 3), [EXCLUYENTE_CONFIRMADO])["estado"] == "no_elegible"


@pytest.mark.parametrize("notas", [(None, 4, 4, 3, 3), (None, None, None, None, None)])
def test_falta_compatibilidad_comercial_es_insuficiente(notas):
    res = calcular(criterios(*notas))
    assert res["estado"] == "evaluacion_insuficiente" and res["score"] is None
    assert "falta evidencia" in res["motivo"]


def test_requisitos_sin_evidencia_no_bloquean():
    """v1.1: los requisitos suelen estar en las bases PDF; sin ellos el score es provisional y se advierte."""
    res = calcular(criterios(5, None, 4, 3, 3))
    # (35 + 16 + 6 + 6) / 75 * 100 = 84
    assert res["estado"] == "provisional" and res["score"] == 84 and res["cobertura"] == 75
    assert rubrica.AVISO_REQUISITOS in res["advertencias"]


def test_bajo_encaje_comercial_se_informa_aunque_falte_lo_demas():
    """Caso real 4776-56-LR26: solo se pudo evaluar el encaje comercial (1/5)."""
    res = calcular(criterios(1, None, None, None, None))
    assert (res["estado"], res["score"], res["etiqueta"], res["cobertura"]) == ("provisional", 20, "Baja idoneidad", 35)
    assert rubrica.AVISO_REQUISITOS in res["advertencias"]


def test_sin_aviso_de_requisitos_cuando_estan_evaluados():
    assert rubrica.AVISO_REQUISITOS not in calcular(criterios(5, 4, 4, None, 3))["advertencias"]


def test_objeto_no_identificado_o_perfil_incompleto_es_insuficiente():
    assert calcular(criterios(5, 4, 4, 3, 3), objeto_identificado=False)["estado"] == "evaluacion_insuficiente"
    res = calcular({}, perfil_completo=False)
    assert res["estado"] == "evaluacion_insuficiente" and "perfil" in res["motivo"]
    assert res["cobertura"] == 0 and len(res["pendientes"]) == 5   # No se inventan notas


def test_provisional_normaliza_sobre_peso_evaluado():
    # Falta geografía (10 %): (35 + 20 + 16 + 6) / 90 * 100 = 85,56 -> 86
    res = calcular(criterios(5, 4, 4, None, 3))
    assert res["estado"] == "provisional" and res["score"] == 86 and res["cobertura"] == 90
    assert res["pendientes"] == ["Viabilidad geográfica y logística"]
    assert "no es directamente comparable" in res["motivo"].lower()


def test_provisional_se_distingue_del_definitivo():
    provisional = calcular(criterios(5, 5, None, None, None))
    assert provisional["estado"] == "provisional" and provisional["score"] == 100 and provisional["cobertura"] == 60
    res = resultado_guardado({"rubrica_version": "v1", "score_estado": "provisional", "score_idoneidad": 100, "score_cobertura": 60})
    assert texto_resultado(res) == "100/100 (provisional)" and res["cobertura"] == 60


def test_redondeo_half_up():
    assert redondear(83.5) == 84 and redondear(84.5) == 85 and redondear(83.49) == 83   # round() daría 84 en 84,5
    # Provisional: (35*3/5 + 25*3/5 + 10*1/5) / 70 * 100 = 38/70*100 = 54,29 -> 54
    assert calcular(criterios(3, 3, None, 1, None))["score"] == 54


def test_nota_5_sin_evidencia_suficiente_se_advierte():
    crit = criterios(5, 4, 4, 3, 3)
    crit["comercial"]["evidencia_estado"] = "parcial"
    res = calcular(crit)
    assert res["score"] == 83 and len(res["advertencias"]) == 1   # Se advierte, no se corrige en silencio


@pytest.mark.parametrize("score, etiqueta", [
    (100, "Idoneidad excelente"), (90, "Idoneidad excelente"), (89, "Buena oportunidad"), (75, "Buena oportunidad"),
    (74, "Oportunidad potencial"), (60, "Oportunidad potencial"), (59, "Encaje limitado"), (40, "Encaje limitado"),
    (39, "Baja idoneidad"), (0, "Baja idoneidad"),
])
def test_etiquetas_en_los_limites(score, etiqueta):
    assert etiqueta_de(score) == etiqueta


def test_resultado_guardado_de_cada_estado():
    v1 = {"rubrica_version": "v1"}
    assert resultado_guardado(dict(v1, score_estado="definitivo", score_idoneidad=83))["etiqueta"] == "Buena oportunidad"
    no_eleg = resultado_guardado(dict(v1, score_estado="no_elegible", score_idoneidad=None))
    assert (no_eleg["valor"], no_eleg["etiqueta"]) == (None, "No elegible")
    insuf = resultado_guardado(dict(v1, score_estado="evaluacion_insuficiente"))
    assert texto_resultado(insuf) == "Evaluación incompleta"
    assert resultado_guardado({})["estado"] is None and texto_resultado(resultado_guardado({})) == "Sin score"


def test_historico_no_se_convierte_de_escala():
    res = resultado_guardado({"score_ia": 8, "rubrica_version": None})
    assert (res["estado"], res["valor"], res["escala"]) == ("historico", 8, 10)
    assert texto_resultado(res) == "8/10 (rúbrica anterior)"
