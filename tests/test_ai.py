# -*- coding: utf-8 -*-
import json

import pytest

from core import config
from core.ai_analyst import AIAnalyst, AnalisisFallido, CuotaAgotada, ResourceExhausted
from core.parsing import validar_analisis, parsear_respuesta_ia, cargar_analisis_guardado

VALIDO = {
    "titulo_recuperado": "Reactivos", "organismo_recuperado": "Hospital",
    "comportamiento_pago": "181 reclamos", "score_ia": 8, "veredicto": "Conviene",
    "puntos_criticos": ["a", "b", "c"], "riesgos": ["r1", "r2"], "motivo_archivo": None,
}


class _Respuesta:
    def __init__(self, texto=None, error=None):
        self._texto, self._error = texto, error

    @property
    def text(self):
        if self._error:
            raise self._error
        return self._texto


class ModeloFalso:
    """Simula genai.GenerativeModel sin red."""
    def __init__(self, texto=None, error_llamada=None, error_texto=None):
        self.texto, self.error_llamada, self.error_texto = texto, error_llamada, error_texto
        self.prompts = []

    def generate_content(self, prompt):
        self.prompts.append(prompt)
        if self.error_llamada:
            raise self.error_llamada
        return _Respuesta(self.texto, self.error_texto)


@pytest.fixture
def db_extraida(db_con_perfil):
    db = db_con_perfil
    db.guardar_licitacion({"id_externo": "X", "titulo": "Reactivos"})
    db.actualizar_detalle_profundo("X", "http://x", "Licitación ID: X\nTexto de la ficha")
    return db


# --- Validación pura ---

def test_validar_normaliza_score_texto_y_listas():
    data = dict(VALIDO, score_ia="8", riesgos="un solo riesgo", puntos_criticos=None)
    res = validar_analisis(data)
    assert res["score_ia"] == 8
    assert res["riesgos"] == ["un solo riesgo"]
    assert res["puntos_criticos"] == []


@pytest.mark.parametrize("score", [None, 0, 11, "8/10", 7.5, True, "abc"])
def test_validar_rechaza_scores_invalidos(score):
    with pytest.raises(ValueError):
        validar_analisis(dict(VALIDO, score_ia=score))


def test_validar_exige_veredicto():
    with pytest.raises(ValueError):
        validar_analisis(dict(VALIDO, veredicto="  "))


def test_validar_rechaza_lista_de_tipo_incorrecto():
    with pytest.raises(ValueError):
        validar_analisis(dict(VALIDO, riesgos={"a": 1}))


@pytest.mark.parametrize("texto", ["", "   ", '{"score_ia": 8, "veredi', "[1, 2]", "no es json"])
def test_parsear_respuesta_invalida(texto):
    with pytest.raises(ValueError):
        parsear_respuesta_ia(texto)


def test_parsear_respuesta_con_markdown():
    assert parsear_respuesta_ia("```json\n" + json.dumps(VALIDO) + "\n```")["score_ia"] == 8


def test_cargar_analisis_guardado_tolerante():
    assert cargar_analisis_guardado("{corrupto") is None
    assert cargar_analisis_guardado(None) is None
    assert cargar_analisis_guardado('{"riesgos": "texto"}')["riesgos"] == ["texto"]


# --- Analista con modelo simulado ---

def test_analisis_valido_se_persiste(db_extraida):
    ia = AIAnalyst(db_extraida, modelo=ModeloFalso(json.dumps(VALIDO)))
    res = ia.analizar_licitacion("X")
    fila = db_extraida.obtener_licitacion("X")
    assert res["score_ia"] == 8
    assert fila["estado"] == "analizado" and fila["score_ia"] == 8
    assert json.loads(fila["analisis_ia_json"])["veredicto"] == "Conviene"


@pytest.mark.parametrize("modelo", [
    ModeloFalso(""),                                         # vacía
    ModeloFalso('{"score_ia": 8'),                            # truncada
    ModeloFalso(json.dumps(dict(VALIDO, score_ia=15))),       # fuera de rango
    ModeloFalso(error_texto=ValueError("blocked: SAFETY")),   # bloqueada
    ModeloFalso(error_llamada=ConnectionError("red")),        # fallo de red
])
def test_respuestas_invalidas_no_persisten(db_extraida, modelo):
    with pytest.raises(AnalisisFallido):
        AIAnalyst(db_extraida, modelo=modelo).analizar_licitacion("X")
    fila = db_extraida.obtener_licitacion("X")
    assert fila["estado"] == "extraido" and fila["analisis_ia_json"] is None


def test_cuota_agotada(db_extraida):
    with pytest.raises(CuotaAgotada):
        AIAnalyst(db_extraida, modelo=ModeloFalso(error_llamada=ResourceExhausted("429"))).analizar_licitacion("X")


def test_reanalisis_fallido_conserva_anterior(db_extraida):
    AIAnalyst(db_extraida, modelo=ModeloFalso(json.dumps(VALIDO))).analizar_licitacion("X")
    db_extraida.cambiar_estado("X", "favorita")
    with pytest.raises(AnalisisFallido):
        AIAnalyst(db_extraida, modelo=ModeloFalso("basura")).analizar_licitacion("X")
    fila = db_extraida.obtener_licitacion("X")
    assert fila["score_ia"] == 8 and fila["estado"] == "favorita"
    assert json.loads(fila["analisis_ia_json"])["veredicto"] == "Conviene"


def test_sin_perfil_falla_controladamente(db):
    db.guardar_licitacion({"id_externo": "X", "titulo": "T"})
    db.actualizar_detalle_profundo("X", None, "texto")
    with pytest.raises(AnalisisFallido, match="perfil"):
        AIAnalyst(db, modelo=ModeloFalso(json.dumps(VALIDO))).analizar_licitacion("X")


def test_sin_descripcion_falla_controladamente(db_con_perfil):
    db_con_perfil.guardar_licitacion({"id_externo": "X", "titulo": "T"})
    with pytest.raises(AnalisisFallido):
        AIAnalyst(db_con_perfil, modelo=ModeloFalso(json.dumps(VALIDO))).analizar_licitacion("X")


def test_ia_no_borra_organismo_con_clave_mal_escrita(db_extraida):
    db_extraida.actualizar_datos_maestros("X", organismo="Hospital Real")
    data = {k: v for k, v in VALIDO.items() if k != "organismo_recuperado"}
    data["organism_recuperado"] = "Otro"
    AIAnalyst(db_extraida, modelo=ModeloFalso(json.dumps(data))).analizar_licitacion("X")
    assert db_extraida.obtener_licitacion("X")["organismo"] == "Hospital Real"


def test_prompt_trunca_y_delimita_corpus(db_con_perfil, monkeypatch):
    monkeypatch.setattr(config, "IA_MAX_CHARS", 100)
    ia = AIAnalyst(db_con_perfil, modelo=ModeloFalso())
    prompt = ia.construir_prompt(db_con_perfil.obtener_perfil(), {"id_externo": "X", "titulo": "T", "descripcion_pro": "Z" * 5000})
    assert "Z" * 100 in prompt and "Z" * 101 not in prompt
    assert "<<<CORPUS>>>" in prompt and "<<<FIN_CORPUS>>>" in prompt
    assert f"{config.SCORE_MIN} al {config.SCORE_MAX}" in prompt
    assert f"score_ia < {config.UMBRAL_DESCARTE}" in prompt


def test_prompt_con_perfil_incompleto():
    ia = AIAnalyst(None, modelo=ModeloFalso())
    prompt = ia.construir_prompt({}, {"id_externo": "X", "titulo": "T", "descripcion_pro": "x"})
    assert "No especificada" in prompt


def test_sin_api_key_lanza_value_error(db, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        AIAnalyst(db)
