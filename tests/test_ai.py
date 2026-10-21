# -*- coding: utf-8 -*-
import json

import pytest

from core import config, rubrica
from core.ai_analyst import AIAnalyst, AnalisisFallido, CuotaAgotada, PROMPT_VERSION, ResourceExhausted
from core.parsing import validar_analisis, parsear_respuesta_ia, cargar_analisis_guardado


def criterio(nota, evidencia="suficiente"):
    return {"nota": nota, "evidencia_estado": evidencia, "evidencia": "cita de la ficha", "explicacion": "motivo"}


def criterios(*notas, evidencia="suficiente"):
    """Criterios en el orden de la rúbrica; una nota None queda sin evidencia ("ausente")."""
    return {c.clave: criterio(n, evidencia if n is not None else "ausente") for c, n in zip(rubrica.CRITERIOS, notas)}


# Respuesta válida con notas [5, 4, 4, 3, 3] => 83/100 definitivo
VALIDO = {
    "titulo_recuperado": "Reactivos", "organismo_recuperado": "Hospital",
    "comportamiento_pago": "181 reclamos", "objeto_principal": "Suministro de reactivos",
    "criterios": criterios(5, 4, 4, 3, 3),
    "requisitos_obligatorios": ["Registro ISP"], "requisitos_excluyentes": [],
    "datos_faltantes": [], "hechos_fuente": ["Contrato por 36 meses"], "inferencias": ["Volumen alto"],
    "veredicto": "Conviene", "puntos_criticos": ["a", "b", "c"], "riesgos": ["r1", "r2"], "motivo_archivo": None,
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

def test_validar_normaliza_notas_texto_y_listas():
    crit = dict(VALIDO["criterios"], comercial=dict(criterio("4"), evidencia_estado=" Suficiente "),
                capacidad=criterio(4.0))
    res = validar_analisis(dict(VALIDO, criterios=crit, riesgos="un solo riesgo", puntos_criticos=None))
    assert res["criterios"]["comercial"]["nota"] == 4 and res["criterios"]["comercial"]["evidencia_estado"] == "suficiente"
    assert res["criterios"]["capacidad"]["nota"] == 4
    assert res["riesgos"] == ["un solo riesgo"]
    assert res["puntos_criticos"] == [] and res["advertencias"] == []
    assert "score_ia" not in res   # El total no viene del modelo


@pytest.mark.parametrize("nota", [-1, 6, "4/5", 3.5, True, "abc"])
def test_validar_rechaza_notas_invalidas(nota):
    with pytest.raises(ValueError):
        validar_analisis(dict(VALIDO, criterios=dict(VALIDO["criterios"], comercial=criterio(nota))))


@pytest.mark.parametrize("criterios_malos", [
    None, [], "texto",
    {k: v for k, v in VALIDO["criterios"].items() if k != "economica"},   # Criterio ausente
    dict(VALIDO["criterios"], geografia=5),                               # Criterio que no es objeto
    dict(VALIDO["criterios"], geografia=dict(criterio(3), evidencia_estado="mucha")),
])
def test_validar_rechaza_criterios_ausentes_o_malformados(criterios_malos):
    with pytest.raises(ValueError):
        validar_analisis(dict(VALIDO, criterios=criterios_malos))


def test_validar_no_usa_notas_sin_evidencia():
    crit = dict(VALIDO["criterios"], geografia=criterio(4, "ausente"), economica=criterio(None, "parcial"))
    res = validar_analisis(dict(VALIDO, criterios=crit))
    assert res["criterios"]["geografia"]["nota"] is None and res["criterios"]["economica"]["nota"] is None
    assert len(res["advertencias"]) == 2


def test_validar_excluyentes():
    excl = [{"requisito": "Registro ISP", "estado": "incumplido_confirmado", "evidencia": "Exige registro vigente"},
            {"requisito": "Experiencia", "estado": "Incumplido_Confirmado", "evidencia": None},
            {"requisito": "Boleta", "estado": "no_verificable"}]
    res = validar_analisis(dict(VALIDO, requisitos_excluyentes=excl))
    assert [e["estado"] for e in res["requisitos_excluyentes"]] == ["incumplido_confirmado", "no_verificable", "no_verificable"]
    assert len(res["advertencias"]) == 1   # Un incumplimiento sin evidencia no se confirma
    for malo in ("texto", [{"estado": "cumplido"}], [{"requisito": "X", "estado": "quizas"}], ["X"]):
        with pytest.raises(ValueError):
            validar_analisis(dict(VALIDO, requisitos_excluyentes=malo))


def test_validar_exige_veredicto():
    with pytest.raises(ValueError):
        validar_analisis(dict(VALIDO, veredicto="  "))


def test_validar_rechaza_lista_de_tipo_incorrecto():
    with pytest.raises(ValueError):
        validar_analisis(dict(VALIDO, riesgos={"a": 1}))


@pytest.mark.parametrize("texto", ["", "   ", '{"criterios": {"comercial": ', "[1, 2]", "no es json"])
def test_parsear_respuesta_invalida(texto):
    with pytest.raises(ValueError):
        parsear_respuesta_ia(texto)


def test_parsear_respuesta_con_markdown():
    assert parsear_respuesta_ia("```json\n" + json.dumps(VALIDO) + "\n```")["veredicto"] == "Conviene"


def test_cargar_analisis_guardado_tolerante():
    assert cargar_analisis_guardado("{corrupto") is None
    assert cargar_analisis_guardado(None) is None
    assert cargar_analisis_guardado('{"riesgos": "texto"}')["riesgos"] == ["texto"]
    # Análisis histórico (sin rúbrica) o con estructuras corruptas: nunca rompe la UI
    an = cargar_analisis_guardado('{"veredicto": "ok", "criterios": "x", "requisitos_excluyentes": [1, {"requisito": "A"}]}')
    assert an["criterios"] == {} and an["rubrica"] is None and an["requisitos_excluyentes"] == [{"requisito": "A"}]


# --- Analista con modelo simulado ---

def test_analisis_valido_se_persiste(db_extraida):
    ia = AIAnalyst(db_extraida, modelo=ModeloFalso(json.dumps(VALIDO)))
    res = ia.analizar_licitacion("X")
    fila = db_extraida.obtener_licitacion("X")
    assert res["rubrica"]["score"] == 83 and res["rubrica"]["estado"] == "definitivo"
    assert fila["estado"] == "analizado" and fila["score_ia"] is None   # score_ia queda para la escala histórica
    assert (fila["score_idoneidad"], fila["score_estado"], fila["score_cobertura"]) == (83, "definitivo", 100)
    assert fila["rubrica_version"] == rubrica.RUBRICA_VERSION and fila["analisis_prompt_version"] == PROMPT_VERSION
    guardado = json.loads(fila["analisis_ia_json"])
    assert guardado["veredicto"] == "Conviene" and guardado["rubrica"]["version"] == rubrica.RUBRICA_VERSION
    assert guardado["criterios"]["comercial"]["nota"] == 5 and guardado["corpus_truncado"] is False


def test_el_total_del_modelo_se_ignora(db_extraida):
    """Si el modelo inventa un total, no se usa: Python lo calcula a partir de las notas."""
    AIAnalyst(db_extraida, modelo=ModeloFalso(json.dumps(dict(VALIDO, score_ia=10, score=99)))).analizar_licitacion("X")
    assert db_extraida.obtener_licitacion("X")["score_idoneidad"] == 83


def test_excluyente_confirmado_se_persiste_como_no_elegible(db_extraida):
    excl = [{"requisito": "Registro ISP", "estado": "incumplido_confirmado", "evidencia": "Exige registro ISP vigente"}]
    AIAnalyst(db_extraida, modelo=ModeloFalso(json.dumps(dict(VALIDO, requisitos_excluyentes=excl)))).analizar_licitacion("X")
    fila = db_extraida.obtener_licitacion("X")
    assert fila["score_estado"] == "no_elegible" and fila["score_idoneidad"] is None
    assert json.loads(fila["analisis_ia_json"])["rubrica"]["incumplidos"][0]["requisito"] == "Registro ISP"


def test_bio_vacia_es_insuficiente_sin_llamar_a_la_ia(db_extraida):
    db_extraida.guardar_perfil("reactivos", "", None, "   ")
    modelo = ModeloFalso(json.dumps(VALIDO))
    res = AIAnalyst(db_extraida, modelo=modelo).analizar_licitacion("X")
    fila = db_extraida.obtener_licitacion("X")
    assert modelo.prompts == []   # No se consumió la API
    assert res["rubrica"]["estado"] == "evaluacion_insuficiente" and "perfil" in res["rubrica"]["motivo"]
    assert fila["score_estado"] == "evaluacion_insuficiente" and fila["analisis_modelo"] is None


def test_corpus_truncado_queda_registrado(db_extraida, monkeypatch):
    monkeypatch.setattr(config, "IA_MAX_CHARS", 10)
    AIAnalyst(db_extraida, modelo=ModeloFalso(json.dumps(VALIDO))).analizar_licitacion("X")
    assert json.loads(db_extraida.obtener_licitacion("X")["analisis_ia_json"])["corpus_truncado"] is True


@pytest.mark.parametrize("modelo", [
    ModeloFalso(""),                                                                  # vacía
    ModeloFalso(json.dumps(VALIDO)[:120]),                                            # truncada
    ModeloFalso(json.dumps(dict(VALIDO, criterios=criterios(5, 4, 9, 3, 3)))),        # nota fuera de rango
    ModeloFalso(json.dumps({k: v for k, v in VALIDO.items() if k != "criterios"})),   # sin criterios
    ModeloFalso(json.dumps(dict(VALIDO, score_ia=8, criterios=None))),                # formato antiguo (score directo)
    ModeloFalso(error_texto=ValueError("blocked: SAFETY")),                           # bloqueada
    ModeloFalso(error_llamada=ConnectionError("red")),                                # fallo de red
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
    assert fila["score_idoneidad"] == 83 and fila["estado"] == "favorita"
    assert json.loads(fila["analisis_ia_json"])["veredicto"] == "Conviene"
    assert db_extraida.obtener_historial("X") == []   # Un fallo no reemplaza ni archiva nada


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


def test_prompt_describe_la_rubrica(db_con_perfil):
    prompt = AIAnalyst(db_con_perfil, modelo=ModeloFalso()).construir_prompt(
        db_con_perfil.obtener_perfil(), {"id_externo": "X", "titulo": "T", "descripcion_pro": "x"})
    for c in rubrica.CRITERIOS:
        assert f'"{c.clave}"' in prompt and f"peso {c.peso}%" in prompt
    assert rubrica.RUBRICA_VERSION in prompt and '"nota": null' in prompt
    assert "score_ia" not in prompt   # El modelo no entrega el total
    assert "fecha de cierre" in prompt and "probabilidad de ganarla" in prompt
    assert "La región de la licitación sola no basta" in prompt   # Geografía exige datos del perfil
    json.loads(prompt[prompt.index("{", prompt.index("FORMATO JSON")):prompt.rindex("}") + 1]
               .replace("entero 0-5 o null", "null"))   # La plantilla de salida es JSON bien formado


def test_prompt_con_perfil_incompleto():
    ia = AIAnalyst(None, modelo=ModeloFalso())
    prompt = ia.construir_prompt({}, {"id_externo": "X", "titulo": "T", "descripcion_pro": "x"})
    assert "No especificada" in prompt


def test_sin_api_key_lanza_value_error(db, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        AIAnalyst(db)
