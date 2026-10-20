# -*- coding: utf-8 -*-
"""
Módulo: Parsing y Validación (parsing)
-------------------------------------
Funciones puras (sin red ni base de datos) para:
1. Normalizar y comparar palabras clave.
2. Interpretar fechas de Mercado Público y llevarlas a formato ISO.
3. Extraer metadatos verificables desde el texto de la ficha técnica.
4. Validar la respuesta JSON del modelo de IA antes de persistirla.

Al no tener efectos secundarios, se prueban de forma determinista.
"""

import re
import json
import unicodedata
from datetime import datetime

from core import config

# Valores de relleno que nunca deben sobrescribir un dato real
MARCADORES = {"", "sin título", "sin titulo", "procesando...", "no detectado",
              "no disponible", "no informado", "none", "null", "sin fecha"}


def es_valor_util(valor):
    """Indicar si un valor es un dato real (no vacío ni marcador de posición)."""
    if valor is None:
        return False
    return str(valor).strip().lower() not in MARCADORES


# ===================================================================
# PALABRAS CLAVE
# ===================================================================

def normalizar_texto(texto):
    """Pasar a minúsculas y eliminar tildes para comparar sin distinguir acentos."""
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFKD", str(texto))
    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return sin_tildes.lower().strip()


def normalizar_keywords(cadena):
    """
    Convertir la cadena del perfil en una lista de términos normalizados.

    Acepta comas, punto y coma o saltos de línea como separadores y descarta
    los términos vacíos (una coma final no debe coincidir con todo).
    """
    if not cadena:
        return []
    terminos = (normalizar_texto(t) for t in re.split(r"[,;\n]", cadena))
    return [t for t in terminos if t]


def coincide_keywords(titulo, positivas, negativas=()):
    """
    Evaluar si un título es relevante para el perfil.

    Args:
        titulo (str): Título de la licitación.
        positivas (list): Términos normalizados de inclusión.
        negativas (list): Términos normalizados de exclusión.

    Returns:
        bool: True si contiene alguna positiva y ninguna negativa.
    """
    nombre = normalizar_texto(titulo)
    if not nombre or not positivas:
        return False
    if any(neg in nombre for neg in negativas):
        return False
    return any(pos in nombre for pos in positivas)


# ===================================================================
# FECHAS
# ===================================================================

_FORMATOS_FECHA = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d-%m-%Y",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y",
)


def parsear_fecha_hora(valor):
    """
    Interpretar una fecha en los formatos usados por la API, la ficha o la BD.

    Returns:
        datetime | None: None si el valor está vacío o no es una fecha válida.
        Nunca se sustituye por la fecha actual.
    """
    if not es_valor_util(valor):
        return None
    texto = str(valor).strip()
    for formato in _FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None


def fecha_iso(valor):
    """Convertir una fecha a 'YYYY-MM-DD' (formato ordenable) o None."""
    fecha = parsear_fecha_hora(valor)
    return fecha.strftime("%Y-%m-%d") if fecha else None


def formatear_fecha(valor, con_hora=False):
    """Formatear una fecha para la UI ('dd/mm/aaaa'), o None si no es válida."""
    fecha = parsear_fecha_hora(valor)
    if not fecha:
        return None
    return fecha.strftime("%d/%m/%Y %H:%M" if con_hora else "%d/%m/%Y")


def esta_cerrada(fecha_cierre, ahora=None):
    """
    Indicar si una licitación ya cerró. Una fecha desconocida se considera abierta
    para no descartar oportunidades por falta de datos.
    """
    cierre = parsear_fecha_hora(fecha_cierre)
    if not cierre:
        return False
    return cierre < (ahora or datetime.now())


# ===================================================================
# METADATOS DESDE LA FICHA TÉCNICA
# ===================================================================

def _buscar_linea(patron, texto):
    """Devolver el valor que sigue a una etiqueta en la misma línea, o None."""
    match = re.search(patron + r"[ \t]*:[ \t]*([^\n\r]*)", texto, flags=re.IGNORECASE)
    if not match:
        return None
    valor = match.group(1).strip()
    return valor if es_valor_util(valor) else None


def texto_ficha_valido(texto):
    """
    Verificar que el texto extraído corresponde a una ficha de licitación y no a
    una página de error o vacía.
    """
    if not texto or len(texto.strip()) < 200:
        return False
    marcadores = ("licitacion id", "fecha de cierre", "nombre de la licitacion")
    normalizado = normalizar_texto(texto[:5000])
    return any(m in normalizado for m in marcadores)


def extraer_metadatos_ficha(texto):
    """
    Extraer datos verificables desde el texto plano de la ficha de Mercado Público.

    Todos los campos son opcionales: si una etiqueta no aparece se devuelve None
    en vez de un valor inventado.

    Returns:
        dict: titulo, organismo, fecha_publicacion (ISO), fecha_cierre (ISO con hora),
              reclamos_pago_n (int) y region.
    """
    texto = texto or ""
    reclamos = re.search(r"Reclamos recibidos por incumplir plazo de pago[ \t]*:[ \t]*(\d+)", texto, re.IGNORECASE)
    fecha_pub = _buscar_linea(r"Fecha de Publicaci[oó]n", texto)
    cierre = parsear_fecha_hora(_buscar_linea(r"Fecha de Cierre", texto))

    return {
        "titulo": _buscar_linea(r"Nombre de la licitaci[oó]n", texto),
        "organismo": _buscar_linea(r"Responsable de esta licitaci[oó]n", texto),
        "fecha_publicacion": fecha_iso(fecha_pub),
        "fecha_cierre": cierre.strftime("%Y-%m-%dT%H:%M:%S") if cierre else None,
        "reclamos_pago_n": int(reclamos.group(1)) if reclamos else None,
        "region": _buscar_linea(r"Regi[oó]n en que se genera la licitaci[oó]n", texto),
    }


# ===================================================================
# VALIDACIÓN DE LA RESPUESTA DE IA
# ===================================================================

def _a_lista_de_textos(valor):
    """Normalizar un campo de lista: un texto suelto pasa a lista de un elemento."""
    if valor is None:
        return []
    if isinstance(valor, str):
        return [valor.strip()] if valor.strip() else []
    if isinstance(valor, (list, tuple)):
        return [str(v).strip() for v in valor if v is not None and str(v).strip()]
    raise ValueError(f"Se esperaba una lista y se recibió {type(valor).__name__}")


def _a_texto(valor):
    """Normalizar un campo de texto opcional."""
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def parsear_respuesta_ia(texto):
    """
    Convertir el texto devuelto por el modelo en un diccionario.

    Tolera delimitadores Markdown (```json). Lanza ValueError si la respuesta
    está vacía o no es un objeto JSON.
    """
    if not texto or not texto.strip():
        raise ValueError("Respuesta vacía del modelo")
    limpio = texto.strip()
    if limpio.startswith("```"):
        limpio = re.sub(r"^```[a-zA-Z]*\s*", "", limpio)
        limpio = re.sub(r"\s*```$", "", limpio)
    try:
        data = json.loads(limpio)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido o truncado: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("La respuesta no es un objeto JSON")
    return data


def validar_analisis(data):
    """
    Validar y normalizar el análisis del modelo antes de guardarlo.

    Reglas:
        - score_ia: entero (acepta "8") dentro de [SCORE_MIN, SCORE_MAX].
        - veredicto: texto no vacío.
        - puntos_criticos / riesgos: listas de textos.
        - Campos recuperados: textos opcionales.

    Returns:
        dict: Análisis normalizado.

    Raises:
        ValueError: Si falta un campo obligatorio o tiene un valor fuera de rango.
    """
    if not isinstance(data, dict):
        raise ValueError("El análisis debe ser un objeto")

    score_raw = data.get("score_ia")
    if isinstance(score_raw, bool) or score_raw is None:
        raise ValueError(f"score_ia ausente o inválido: {score_raw!r}")
    try:
        score_float = float(str(score_raw).strip())
    except ValueError as e:
        raise ValueError(f"score_ia no numérico: {score_raw!r}") from e
    if not score_float.is_integer():
        raise ValueError(f"score_ia debe ser entero: {score_raw!r}")
    score = int(score_float)
    if not config.SCORE_MIN <= score <= config.SCORE_MAX:
        raise ValueError(f"score_ia fuera de rango {config.SCORE_MIN}-{config.SCORE_MAX}: {score}")

    veredicto = _a_texto(data.get("veredicto"))
    if not veredicto:
        raise ValueError("veredicto ausente")

    return {
        "titulo_recuperado": _a_texto(data.get("titulo_recuperado")),
        "organismo_recuperado": _a_texto(data.get("organismo_recuperado")),
        "comportamiento_pago": _a_texto(data.get("comportamiento_pago")),
        "score_ia": score,
        "veredicto": veredicto,
        "puntos_criticos": _a_lista_de_textos(data.get("puntos_criticos")),
        "riesgos": _a_lista_de_textos(data.get("riesgos")),
        "motivo_archivo": _a_texto(data.get("motivo_archivo")),
    }


def cargar_analisis_guardado(analisis_json):
    """
    Leer de forma tolerante el análisis guardado en la BD para mostrarlo en la UI.

    Nunca lanza excepciones: un JSON corrupto devuelve None y las listas
    guardadas como texto se convierten en listas.
    """
    if not analisis_json:
        return None
    try:
        data = json.loads(analisis_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    for campo in ("puntos_criticos", "riesgos"):
        try:
            data[campo] = _a_lista_de_textos(data.get(campo))
        except ValueError:
            data[campo] = []
    return data
