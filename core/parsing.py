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
import hashlib
import unicodedata
from datetime import datetime

from core import config, rubrica

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


def version_perfil(perfil):
    """
    Huella corta del perfil tal como lo usa la IA (keywords y bio).

    Cambios que no alteran el significado (mayúsculas, tildes o espacios en las
    keywords, espacios al borde de la bio) no cambian la versión.

    Returns:
        str | None: 8 caracteres hexadecimales, o None si no hay perfil.
    """
    if not perfil:
        return None
    contenido = json.dumps({
        "pos": sorted(normalizar_keywords(perfil.get("keywords_pos"))),
        "neg": sorted(normalizar_keywords(perfil.get("keywords_neg"))),
        "bio": (perfil.get("bio_estrategica") or "").strip(),
    }, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(contenido.encode("utf-8")).hexdigest()[:8]


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
    return cierre < (ahora or config.ahora())


def dias_para_cierre(fecha_cierre, ahora=None):
    """
    Días calendario que faltan para el cierre (0 = cierra hoy, negativo = ya cerró).

    Returns:
        int | None: None si la fecha de cierre es desconocida.
    """
    cierre = parsear_fecha_hora(fecha_cierre)
    if not cierre:
        return None
    ahora = ahora or config.ahora()
    if cierre < ahora:
        return min(-1, (cierre.date() - ahora.date()).days)
    return (cierre.date() - ahora.date()).days


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


def _a_nota(valor, campo):
    """Nota de un criterio: entero (acepta "4" y 4.0) en [NOTA_MIN, NOTA_MAX], o None."""
    if valor is None:
        return None
    if isinstance(valor, bool):
        raise ValueError(f"{campo} inválida: {valor!r}")
    try:
        numero = float(str(valor).strip())
    except ValueError as e:
        raise ValueError(f"{campo} no numérica: {valor!r}") from e
    if not numero.is_integer():
        raise ValueError(f"{campo} debe ser entera: {valor!r}")
    nota = int(numero)
    if not rubrica.NOTA_MIN <= nota <= rubrica.NOTA_MAX:
        raise ValueError(f"{campo} fuera de rango {rubrica.NOTA_MIN}-{rubrica.NOTA_MAX}: {nota}")
    return nota


def _a_opcion(valor, opciones, campo):
    """Texto que debe ser una de las opciones (sin distinguir mayúsculas)."""
    texto = (_a_texto(valor) or "").lower()
    if texto not in opciones:
        raise ValueError(f"{campo} inválido: {valor!r} (se esperaba {', '.join(opciones)})")
    return texto


# Nombres alternativos que el modelo ha usado (o podría usar) para las claves:
# traducciones al inglés y variantes con tildes o con el nombre largo.
ALIAS_CRITERIOS = {
    "commercial": "comercial", "compatibilidad_comercial": "comercial",
    "requirements": "requisitos", "requisitos_obligatorios": "requisitos",
    "capacity": "capacidad", "capacidad_de_cumplimiento": "capacidad",
    "geography": "geografia", "viabilidad_geografica": "geografia", "viabilidad_geografica_y_logistica": "geografia",
    "economic": "economica", "viabilidad_economica": "economica", "viabilidad_economica_y_contractual": "economica",
}
ALIAS_CAMPOS_CRITERIO = {
    "estado_evidencia": "evidencia_estado", "evidence_status": "evidencia_estado", "evidence_state": "evidencia_estado",
    "note": "nota", "score": "nota", "grade": "nota",
    "evidence": "evidencia", "explanation": "explicacion",
}


def _clave(texto):
    """Clave comparable: sin tildes, minúsculas y con guiones bajos ('Geografía' -> 'geografia')."""
    return re.sub(r"[\s-]+", "_", normalizar_texto(texto))


def _con_alias(objeto, alias, canonicas, advertencias, contexto=""):
    """
    Renombrar las claves alternativas a su nombre canónico (solo si la canónica no viene)
    y dejar constancia en `advertencias`. Así un nombre traducido no descarta un análisis válido.
    """
    resultado = dict(objeto)
    for original in list(objeto):
        canonica = _clave(original)
        canonica = canonica if canonica in canonicas else alias.get(canonica)
        if canonica and canonica != original and canonica not in objeto:
            resultado[canonica] = resultado.pop(original)
            advertencias.append(f"La IA usó la clave «{original}»{contexto}; se interpretó como «{canonica}»")
    return resultado


def _validar_criterios(valor, advertencias):
    """
    Validar las notas por criterio de la rúbrica.

    Una nota con evidencia "ausente" se anula (no se usan notas sin respaldo) y
    queda registrada en `advertencias`; nunca se inventa una nota faltante.
    """
    if not isinstance(valor, dict):
        raise ValueError("criterios ausente o no es un objeto")
    valor = _con_alias(valor, ALIAS_CRITERIOS, {c.clave for c in rubrica.CRITERIOS}, advertencias)
    criterios = {}
    for c in rubrica.CRITERIOS:
        item = valor.get(c.clave)
        if isinstance(item, dict):
            item = _con_alias(item, ALIAS_CAMPOS_CRITERIO, {"nota", "evidencia_estado", "evidencia", "explicacion"},
                              advertencias, f" en {c.clave}")
        if not isinstance(item, dict):
            raise ValueError(f"criterio ausente o inválido: {c.clave}")
        nota = _a_nota(item.get("nota"), f"nota de {c.clave}")
        evidencia_estado = _a_opcion(item.get("evidencia_estado"), rubrica.EVIDENCIA_ESTADOS, f"evidencia_estado de {c.clave}")
        if nota is not None and evidencia_estado == "ausente":
            advertencias.append(f"{c.nombre}: la IA asignó nota {nota} sin evidencia; no se considera")
            nota = None
        elif nota is None and evidencia_estado != "ausente":
            advertencias.append(f"{c.nombre}: evidencia {evidencia_estado} pero sin nota; queda pendiente")
        criterios[c.clave] = {
            "nota": nota,
            "evidencia_estado": evidencia_estado,
            "evidencia": _a_texto(item.get("evidencia")),
            "explicacion": _a_texto(item.get("explicacion")),
        }
    return criterios


def _validar_excluyentes(valor, advertencias):
    """
    Validar los requisitos excluyentes. Un incumplimiento "confirmado" sin
    evidencia no puede confirmarse: pasa a "no_verificable" y se advierte.
    """
    if valor is None:
        return []
    if not isinstance(valor, (list, tuple)):
        raise ValueError("requisitos_excluyentes debe ser una lista")
    resultado = []
    for item in valor:
        if not isinstance(item, dict):
            raise ValueError("cada requisito excluyente debe ser un objeto")
        requisito = _a_texto(item.get("requisito"))
        if not requisito:
            raise ValueError("requisito excluyente sin descripción")
        estado = _a_opcion(item.get("estado"), rubrica.EXCLUYENTE_ESTADOS, "estado de requisito excluyente")
        evidencia = _a_texto(item.get("evidencia"))
        if estado == "incumplido_confirmado" and not evidencia:
            advertencias.append(f"Requisito «{requisito}»: incumplimiento sin evidencia; se trata como no verificable")
            estado = "no_verificable"
        resultado.append({"requisito": requisito, "estado": estado, "evidencia": evidencia})
    return resultado


def validar_analisis(data):
    """
    Validar y normalizar el análisis del modelo antes de guardarlo (rúbrica v1).

    Reglas:
        - criterios: los cinco de core/rubrica.py, cada uno con nota entera
          0-5 o null y evidencia_estado suficiente | parcial | ausente.
        - requisitos_excluyentes: lista de {requisito, estado, evidencia}.
        - veredicto: texto no vacío.
        - Listas (puntos críticos, riesgos, faltantes, hechos, inferencias...): listas de textos.
        - Campos recuperados y objeto_principal: textos opcionales.

    El modelo no entrega el total: lo calcula `core.rubrica.calcular`.

    Returns:
        dict: Análisis normalizado, con `advertencias` de las correcciones aplicadas.

    Raises:
        ValueError: Si falta un campo obligatorio o tiene un valor inválido.
    """
    if not isinstance(data, dict):
        raise ValueError("El análisis debe ser un objeto")

    advertencias = []
    criterios = _validar_criterios(data.get("criterios"), advertencias)
    excluyentes = _validar_excluyentes(data.get("requisitos_excluyentes"), advertencias)

    veredicto = _a_texto(data.get("veredicto"))
    if not veredicto:
        raise ValueError("veredicto ausente")

    return {
        "titulo_recuperado": _a_texto(data.get("titulo_recuperado")),
        "organismo_recuperado": _a_texto(data.get("organismo_recuperado")),
        "comportamiento_pago": _a_texto(data.get("comportamiento_pago")),
        "objeto_principal": _a_texto(data.get("objeto_principal")),
        "criterios": criterios,
        "requisitos_obligatorios": _a_lista_de_textos(data.get("requisitos_obligatorios")),
        "requisitos_excluyentes": excluyentes,
        "datos_faltantes": _a_lista_de_textos(data.get("datos_faltantes")),
        "hechos_fuente": _a_lista_de_textos(data.get("hechos_fuente")),
        "inferencias": _a_lista_de_textos(data.get("inferencias")),
        "veredicto": veredicto,
        "puntos_criticos": _a_lista_de_textos(data.get("puntos_criticos")),
        "riesgos": _a_lista_de_textos(data.get("riesgos")),
        "motivo_archivo": _a_texto(data.get("motivo_archivo")),
        "advertencias": advertencias,
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
    for campo in ("puntos_criticos", "riesgos", "requisitos_obligatorios", "datos_faltantes",
                  "hechos_fuente", "inferencias", "advertencias"):
        try:
            data[campo] = _a_lista_de_textos(data.get(campo))
        except ValueError:
            data[campo] = []
    # Estructuras de la rúbrica (ausentes en análisis históricos)
    for campo, tipo, vacio in (("criterios", dict, {}), ("rubrica", dict, None), ("requisitos_excluyentes", list, [])):
        if not isinstance(data.get(campo), tipo):
            data[campo] = vacio
    data["requisitos_excluyentes"] = [e for e in data["requisitos_excluyentes"] if isinstance(e, dict)]
    data["criterios"] = {k: v for k, v in data["criterios"].items() if isinstance(v, dict)}
    return data
