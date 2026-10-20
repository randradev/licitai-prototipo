# -*- coding: utf-8 -*-
from datetime import datetime

import pytest

from core.parsing import (
    normalizar_keywords, coincide_keywords, parsear_fecha_hora, fecha_iso, formatear_fecha,
    esta_cerrada, texto_ficha_valido, extraer_metadatos_ficha, es_valor_util,
)
from tests.conftest import FICHA_EJEMPLO


# --- Keywords ---

def test_keywords_descarta_vacios_y_normaliza():
    assert normalizar_keywords("Centrífuga, , Laboratorio Clínico,") == ["centrifuga", "laboratorio clinico"]
    assert normalizar_keywords(None) == []
    assert normalizar_keywords(" , ,") == []


def test_keywords_admite_saltos_de_linea_y_punto_y_coma():
    assert normalizar_keywords("a;b\nc") == ["a", "b", "c"]


def test_coincidencia_sin_tildes_ni_mayusculas():
    assert coincide_keywords("ADQUISICION LABORATORIO CLINICO", ["laboratorio clinico"])


def test_coma_final_no_coincide_con_todo():
    assert not coincide_keywords("Servicio de guardias", normalizar_keywords("reactivos,"))


def test_keyword_negativa_excluye():
    pos, neg = normalizar_keywords("reactivos"), normalizar_keywords("limpieza")
    assert coincide_keywords("Reactivos clínicos", pos, neg)
    assert not coincide_keywords("Reactivos y limpieza hospitalaria", pos, neg)


def test_sin_keywords_positivas_no_coincide_nada():
    assert not coincide_keywords("Reactivos", [])
    assert not coincide_keywords(None, ["reactivos"])


# --- Fechas ---

@pytest.mark.parametrize("valor,esperado", [
    ("05-02-2026 8:34:58", "2026-02-05"),
    ("2026-02-18T16:00:00", "2026-02-18"),
    ("05/02/2026", "2026-02-05"),
    ("2026-02-05", "2026-02-05"),
])
def test_fecha_iso_formatos(valor, esperado):
    assert fecha_iso(valor) == esperado


@pytest.mark.parametrize("valor", [None, "", "Procesando...", "Sin fecha", "31-02-2026", "mañana"])
def test_fecha_invalida_es_none_nunca_hoy(valor):
    assert fecha_iso(valor) is None
    assert parsear_fecha_hora(valor) is None


def test_orden_cronologico_iso_entre_meses_y_anios():
    fechas = ["30/09/2026", "10/01/2027", "09/02/2026", "05/03/2026"]
    # El formato antiguo ordenado como texto da un orden incorrecto
    assert sorted(fechas, reverse=True)[0] == "30/09/2026"
    iso = sorted((fecha_iso(f) for f in fechas), reverse=True)
    assert iso == ["2027-01-10", "2026-09-30", "2026-03-05", "2026-02-09"]


def test_formatear_fecha():
    assert formatear_fecha("2026-02-05") == "05/02/2026"
    assert formatear_fecha("2026-02-18T16:00:00", con_hora=True) == "18/02/2026 16:00"
    assert formatear_fecha(None) is None


def test_esta_cerrada():
    ahora = datetime(2026, 2, 10, 12, 0)
    assert esta_cerrada("2026-02-05T15:00:00", ahora)
    assert not esta_cerrada("2026-02-18T16:00:00", ahora)
    assert not esta_cerrada(None, ahora)          # Desconocida => se mantiene
    assert not esta_cerrada("Sin fecha", ahora)


# --- Ficha ---

def test_extraer_metadatos_ficha():
    meta = extraer_metadatos_ficha(FICHA_EJEMPLO)
    assert meta == {
        "titulo": "Suministro de reactivos para laboratorio clínico",
        "organismo": "HOSPITAL DE PRUEBA",
        "fecha_publicacion": "2026-02-05",
        "fecha_cierre": "2099-02-18T16:00:00",
        "reclamos_pago_n": 181,
        "region": "Región de los Lagos",
    }


def test_metadatos_ausentes_son_none():
    meta = extraer_metadatos_ficha("texto sin etiquetas conocidas")
    assert all(v is None for v in meta.values())
    assert all(v is None for v in extraer_metadatos_ficha(None).values())


def test_region_vacia_es_none():
    meta = extraer_metadatos_ficha("Región en que se genera la licitación:\n\nOtra cosa")
    assert meta["region"] is None


def test_texto_ficha_valido():
    assert texto_ficha_valido(FICHA_EJEMPLO)
    assert not texto_ficha_valido("No se pudo extraer el detalle técnico.")
    assert not texto_ficha_valido("x" * 5000)   # Mucho texto pero no es una ficha
    assert not texto_ficha_valido(None)


def test_es_valor_util():
    assert not es_valor_util("Sin título")
    assert not es_valor_util("No detectado")
    assert not es_valor_util("  ")
    assert not es_valor_util(None)
    assert es_valor_util("Hospital de Castro")
