# -*- coding: utf-8 -*-
"""
Módulo: Rúbrica de Idoneidad (rubrica)
-------------------------------------
Fuente única y versionada de la rúbrica del score (ver licitai-scoring-rubrica-v1.md):
1. Criterios, pesos, escala de notas y rangos de interpretación.
2. Cálculo del score 0-100 y de su estado a partir de las notas por criterio.
3. Lectura del resultado guardado en la BD, incluidos los análisis históricos (escala 1-10).

Funciones puras (sin red ni base de datos). El LLM entrega notas por criterio;
el total, la cobertura y el estado se calculan aquí, nunca los decide el modelo.

El score mide compatibilidad con el perfil de la empresa: NO es la
probabilidad de ganar la licitación. Pesos y umbrales son una hipótesis
inicial, aún no validada con evaluaciones humanas.
"""

from collections import namedtuple
from fractions import Fraction

from core import config

# Cámbiala si modificas criterios, pesos, escala, rangos o reglas de estado.
# v1.1: los requisitos obligatorios sin evidencia ya no bloquean la evaluación
#       (suelen estar en las bases PDF, que el prototipo no lee): el score queda
#       provisional y se advierte que hay que revisar las bases.
RUBRICA_VERSION = "v1.1"

# esencial: pesa en la decisión y se advierte si falta.
# bloqueante: sin su nota no hay evaluación posible (evaluacion_insuficiente).
Criterio = namedtuple("Criterio", "clave nombre peso esencial bloqueante")

CRITERIOS = (
    Criterio("comercial", "Compatibilidad comercial", 35, True, True),
    Criterio("requisitos", "Requisitos obligatorios", 25, True, False),
    Criterio("capacidad", "Capacidad de cumplimiento", 20, False, False),
    Criterio("geografia", "Viabilidad geográfica y logística", 10, False, False),
    Criterio("economica", "Viabilidad económica y contractual", 10, False, False),
)
AVISO_REQUISITOS = "Requisitos obligatorios no verificados en la ficha: revisa las bases de la licitación."
PESO_TOTAL = sum(c.peso for c in CRITERIOS)

NOTA_MIN, NOTA_MAX = 0, 5
ESCALA = {
    0: "Incompatible o incumplimiento demostrado",
    1: "Compatibilidad muy baja",
    2: "Compatibilidad parcial, con brechas importantes",
    3: "Compatibilidad razonable, con condiciones pendientes",
    4: "Buena compatibilidad, con brechas menores",
    5: "Compatibilidad completa, respaldada por evidencia suficiente",
}

EVIDENCIA_ESTADOS = ("suficiente", "parcial", "ausente")
EXCLUYENTE_ESTADOS = ("incumplido_confirmado", "no_verificable", "cumplido")

# Estados del score. `historico` = análisis anterior a la rúbrica (escala 1-10).
DEFINITIVO, PROVISIONAL = "definitivo", "provisional"
NO_ELEGIBLE, INSUFICIENTE = "no_elegible", "evaluacion_insuficiente"
HISTORICO = "historico"
ESTADOS_CON_NUMERO = (DEFINITIVO, PROVISIONAL)

ETIQUETAS_ESTADO = {
    DEFINITIVO: "Score definitivo",
    PROVISIONAL: "Score provisional",
    NO_ELEGIBLE: "No elegible",
    INSUFICIENTE: "Evaluación incompleta",
    HISTORICO: "Rúbrica anterior",
}

# Rangos de interpretación iniciales (límite inferior, etiqueta), de mayor a menor
RANGOS = (
    (90, "Idoneidad excelente"),
    (75, "Buena oportunidad"),
    (60, "Oportunidad potencial"),
    (40, "Encaje limitado"),
    (0, "Baja idoneidad"),
)
UMBRAL_ALTO = 75     # score >= UMBRAL_ALTO => verde
UMBRAL_MEDIO = 40    # score >= UMBRAL_MEDIO => amarillo, menor => rojo
UMBRAL_DESCARTE = 40  # bajo este score se muestra por qué podría no convenir


def redondear(valor):
    """Redondeo half-up a entero (83,5 -> 84), exacto con Fraction; `round()` usa redondeo bancario."""
    valor = Fraction(valor)
    return int((valor + Fraction(1, 2)) // 1)


def etiqueta_de(score):
    """Etiqueta del rango de interpretación de un score 0-100 (None si no hay score)."""
    if score is None:
        return None
    for desde, etiqueta in RANGOS:
        if score >= desde:
            return etiqueta
    return RANGOS[-1][1]


def nivel_de(score):
    """Nivel visual de un score 0-100: 'alto' | 'medio' | 'bajo' | 'nulo'."""
    if score is None:
        return "nulo"
    return "alto" if score >= UMBRAL_ALTO else "medio" if score >= UMBRAL_MEDIO else "bajo"


def calcular(criterios, excluyentes=(), objeto_identificado=True, perfil_completo=True):
    """
    Calcular score, estado y cobertura a partir de las notas ya validadas.

    Prevalencia: no_elegible > evaluacion_insuficiente > provisional > definitivo.

    - no_elegible: algún requisito excluyente con incumplimiento confirmado
      (con evidencia). Un requisito solo "no verificable" no lo activa.
    - evaluacion_insuficiente: perfil sin descripción, objeto principal no
      identificado o compatibilidad comercial sin nota (criterio bloqueante).
    - provisional: la compatibilidad comercial tiene nota y falta algún otro
      criterio; el score se normaliza sobre el peso evaluado (redondeo half-up).
      Si faltan los requisitos obligatorios se agrega AVISO_REQUISITOS.
    - definitivo: los cinco criterios tienen nota. Con pesos 35/25/20/10/10 y
      notas enteras el total ya es entero, sin redondeo.

    Args:
        criterios (dict): {clave: {"nota": int | None, "evidencia_estado": str, ...}}.
        excluyentes (list): [{"requisito", "estado", "evidencia"}].
        objeto_identificado (bool): Si se pudo determinar el objeto de la licitación.
        perfil_completo (bool): Si el perfil describe qué ofrece la empresa.

    Returns:
        dict: version, estado, score (0-100 | None), etiqueta, cobertura (% del
              peso evaluado), pendientes (nombres), incumplidos, motivo, advertencias.
    """
    criterios = criterios or {}
    evaluados = [c for c in CRITERIOS if (criterios.get(c.clave) or {}).get("nota") is not None]
    pendientes = [c for c in CRITERIOS if c not in evaluados]
    peso_evaluado = sum(c.peso for c in evaluados)
    cobertura = redondear(Fraction(100 * peso_evaluado, PESO_TOTAL))

    advertencias = [f"{c.nombre}: nota 5 sin evidencia suficiente" for c in evaluados
                    if criterios[c.clave]["nota"] == NOTA_MAX and criterios[c.clave].get("evidencia_estado") != "suficiente"]
    incumplidos = [e for e in (excluyentes or ()) if e.get("estado") == "incumplido_confirmado" and e.get("evidencia")]

    resultado = {
        "version": RUBRICA_VERSION, "estado": None, "score": None, "etiqueta": None, "cobertura": cobertura,
        "pendientes": [c.nombre for c in pendientes], "incumplidos": incumplidos, "motivo": None,
        "advertencias": advertencias,
    }

    if incumplidos:
        resultado["estado"] = NO_ELEGIBLE
        resultado["motivo"] = "No cumple un requisito excluyente: " + "; ".join(e["requisito"] for e in incumplidos)
        return resultado

    faltan_esenciales = [c.nombre for c in pendientes if c.bloqueante]
    motivos = []
    if not perfil_completo:
        motivos.append("el perfil no describe los productos o servicios de la empresa")
    if not objeto_identificado:
        motivos.append("no se pudo determinar el objeto principal de la licitación")
    if faltan_esenciales:
        motivos.append("falta evidencia para evaluar " + " y ".join(n.lower() for n in faltan_esenciales))
    if motivos:
        resultado["estado"] = INSUFICIENTE
        resultado["motivo"] = "No hay información suficiente: " + "; ".join(motivos) + "."
        return resultado

    puntos = sum(Fraction(c.peso * criterios[c.clave]["nota"], NOTA_MAX) for c in evaluados)
    if any(c.esencial for c in pendientes):
        advertencias.append(AVISO_REQUISITOS)
    if pendientes:
        resultado["estado"] = PROVISIONAL
        resultado["score"] = redondear(puntos * PESO_TOTAL / peso_evaluado)
        resultado["motivo"] = ("Score provisional: no se evaluó " + ", ".join(n.lower() for n in resultado["pendientes"])
                               + ". No es directamente comparable con un score definitivo.")
    else:
        resultado["estado"] = DEFINITIVO
        resultado["score"] = int(puntos)
    resultado["etiqueta"] = etiqueta_de(resultado["score"])
    return resultado


def resultado_guardado(licit):
    """
    Resultado del score vigente de una licitación de la BD, para mostrarlo.

    Los análisis sin `rubrica_version` son históricos (escala 1-10): se
    muestran tal cual, nunca se convierten a la escala 0-100.

    Returns:
        dict: estado (None si no hay análisis), valor, escala (100 | 10),
              etiqueta, nivel ('alto' | 'medio' | 'bajo' | 'nulo') y cobertura.
    """
    if licit.get("rubrica_version"):
        estado = licit.get("score_estado")
        valor = _entero(licit.get("score_idoneidad")) if estado in ESTADOS_CON_NUMERO else None
        return {"estado": estado, "valor": valor, "escala": 100,
                "etiqueta": etiqueta_de(valor) or ETIQUETAS_ESTADO.get(estado), "nivel": nivel_de(valor),
                "cobertura": _entero(licit.get("score_cobertura"))}
    valor = _entero(licit.get("score_ia"))
    if valor is None:
        return {"estado": None, "valor": None, "escala": 100, "etiqueta": None, "nivel": "nulo", "cobertura": None}
    nivel = "alto" if valor >= config.UMBRAL_ALTO else "medio" if valor >= config.UMBRAL_MEDIO else "bajo"
    return {"estado": HISTORICO, "valor": valor, "escala": config.SCORE_MAX,
            "etiqueta": ETIQUETAS_ESTADO[HISTORICO], "nivel": nivel, "cobertura": None}


def texto_resultado(res):
    """Texto corto del resultado: '83/100', '71/100 (provisional)', 'No elegible', '7/10 (rúbrica anterior)'."""
    estado = res.get("estado")
    if estado == DEFINITIVO:
        return f"{res['valor']}/100"
    if estado == PROVISIONAL:
        return f"{res['valor']}/100 (provisional)"
    if estado == HISTORICO:
        return f"{res['valor']}/{res['escala']} (rúbrica anterior)"
    return ETIQUETAS_ESTADO.get(estado, "Sin score")


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None
