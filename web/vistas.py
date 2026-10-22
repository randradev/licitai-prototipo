# -*- coding: utf-8 -*-
"""
Módulo: Vistas (vistas)
----------------------
Capa de presentación del dashboard. Contiene:
1. Helpers puros (sin Streamlit) para formatear, filtrar, resumir y redactar
   mensajes para el usuario final (sin jerga técnica).
2. Constructores de HTML para tarjetas, KPIs e insignias (todo texto externo se escapa).
3. Las funciones que dibujan cada página (las invoca web/paginas/*.py).

Los widgets interactivos (botones, formularios) son de Streamlit; el HTML solo
se usa para presentar información.
"""

import json
import logging
from datetime import datetime
from html import escape

import streamlit as st
from core import config, rubrica
from core.database_mgr import DatabaseManager
from core.exportar import a_csv, a_json
from core.parsing import (cargar_analisis_guardado, coincide_keywords, dias_para_cierre, es_valor_util, fecha_iso,
                          formatear_fecha, normalizar_keywords, normalizar_texto, parsear_fecha_hora, version_perfil)

log = logging.getLogger("licitai.web")

# Ítems del checklist de gestión (clave persistida -> etiqueta)
CHECKLIST_ITEMS = {"bases_leidas": "Bases leídas", "anexos_preparados": "Anexos preparados"}

# Evaluación humana del análisis (clave persistida -> etiqueta)
EVAL_SCORE_LABELS = {"acertado": "Acertado", "muy_alto": "Muy alto", "muy_bajo": "Muy bajo"}
POSTULARIA_LABELS = {"si": "Sí", "tal_vez": "Tal vez", "no": "No"}

ORDENES = ("Cierre más próximo", "Mayor score", "Más recientes")
ESTADOS_COLA = ("pendiente", "extraido", "error")

# Colores de marca del anillo de score (paleta de estado; ver web/estilos.py)
COLOR_NIVEL = {"alto": "#0ca30c", "medio": "#fab219", "bajo": "#d03b3b", "nulo": "#b8b3a7"}


# ===================================================================
# HELPERS DE PRESENTACIÓN (puros, sin Streamlit)
# ===================================================================

def score_comparable(licit):
    """Score 0-100 de la rúbrica (definitivo o provisional), o None (sin número, histórico o sin análisis)."""
    res = rubrica.resultado_guardado(licit)
    return res["valor"] if res["estado"] in rubrica.ESTADOS_CON_NUMERO else None


# Orden de "Mayor score": primero los que tienen score de la rúbrica, luego los históricos
# (otra escala, no comparables), luego los que no tienen número.
_GRUPO_ORDEN = {rubrica.DEFINITIVO: 0, rubrica.PROVISIONAL: 0, rubrica.HISTORICO: 1,
                rubrica.INSUFICIENTE: 2, rubrica.NO_ELEGIBLE: 3}


def clave_mayor_score(licit):
    res = rubrica.resultado_guardado(licit)
    return (_GRUPO_ORDEN.get(res["estado"], 4), -(res["valor"] or 0))


def sugiere_descartar(res):
    """True si el resultado indica que la licitación podría no convenir (para mostrar el motivo)."""
    if res["estado"] == rubrica.NO_ELEGIBLE:
        return True
    if res["estado"] in rubrica.ESTADOS_CON_NUMERO:
        return res["valor"] < rubrica.UMBRAL_DESCARTE
    return res["estado"] == rubrica.HISTORICO and res["valor"] < config.UMBRAL_DESCARTE


def titulo_de(licit, analisis=None):
    """Resolver el título a mostrar: dato de la fuente, luego IA, luego el ID."""
    if es_valor_util(licit.get('titulo')) and licit.get('titulo') != f"Licitación {licit['id_externo']}":
        return licit['titulo']
    if analisis and es_valor_util(analisis.get('titulo_recuperado')):
        return analisis['titulo_recuperado']
    return f"Licitación {licit['id_externo']}"


def organismo_de(licit):
    return licit['organismo'] if es_valor_util(licit.get('organismo')) else "Organismo no identificado"


def info_pago(licit):
    """
    Describir los reclamos de pago separando su procedencia.

    Returns:
        tuple: (texto_fuente | None, texto_ia | None). Si ambos son None no hay
               datos verificados.
    """
    n = licit.get('reclamos_pago_n')
    fuente = None
    if n is not None:
        fuente = f"{n} reclamos por pagos atrasados en los últimos 12 meses · Fuente: Mercado Público"
        leida = formatear_fecha(licit.get('ficha_fecha'))
        if leida:
            fuente += f" (ficha leída el {leida})"
    ia = licit.get('reclamo_pago') if es_valor_util(licit.get('reclamo_pago')) else None
    return fuente, ia


def etiqueta_cierre(licit, ahora=None):
    """Texto corto con la urgencia del cierre."""
    dias = dias_para_cierre(licit.get('fecha_cierre'), ahora)
    if dias is None:
        return "Cierre sin informar"
    if dias < 0:
        return "Cerrada"
    if dias == 0:
        return "Cierra hoy"
    if dias == 1:
        return "Cierra mañana"
    return f"Cierra en {dias} días"


def urgencia_cierre(licit, ahora=None):
    """Nivel visual del chip de cierre: 'bajo' (≤3 días), 'medio' (≤7), '' (resto)."""
    dias = dias_para_cierre(licit.get('fecha_cierre'), ahora)
    if dias is None or dias < 0:
        return ""
    return "bajo" if dias <= 3 else "medio" if dias <= 7 else ""


def region_corta(region):
    """'Región de los Lagos' -> 'Los Lagos'; 'Región Metropolitana de Santiago' -> 'Metropolitana de Santiago'."""
    texto = region.strip()
    for prefijo in ("Región de la ", "Región de los ", "Región del ", "Región de ", "Región "):
        if texto.startswith(prefijo):
            texto = texto[len(prefijo):] if prefijo != "Región de los " else "los " + texto[len(prefijo):]
            break
    return texto[:1].upper() + texto[1:]


def texto_trazabilidad(licit):
    """Fecha del análisis vigente, en lenguaje de usuario (o '' si no se registró)."""
    if not licit.get('analisis_fecha'):
        return ""
    fecha = parsear_fecha_hora(licit['analisis_fecha'])
    return f"Analizado el {fecha.strftime('%d/%m/%Y')} a las {fecha.strftime('%H:%M')}" if fecha else ""


def detalles_tecnicos(licit):
    """Datos técnicos del análisis (modelo, prompt, perfil) para el desplegable «Detalles técnicos»."""
    if not licit.get('analisis_fecha'):
        return []
    return [f"Modelo: {licit.get('analisis_modelo') or '—'}",
            f"Versión del prompt: {licit.get('analisis_prompt_version') or '—'}",
            f"Versión del perfil: {licit.get('analisis_perfil_version') or '—'}"]


def analisis_con_perfil_anterior(licit, version_actual):
    """
    True si el análisis vigente se hizo con un perfil distinto al actual.
    Los análisis sin versión registrada (anteriores a esta función) también cuentan.
    """
    return bool(licit.get('analisis_ia_json')) and licit.get('analisis_perfil_version') != version_actual


def afectados_por_perfil(licitaciones, version_actual, estados=('analizado', 'favorita')):
    """Análisis activos hechos con un perfil anterior (candidatos a re-analizar)."""
    return [l for l in licitaciones if l.get('estado') in estados and l.get('descripcion_pro')
            and analisis_con_perfil_anterior(l, version_actual)]


def con_rubrica_anterior(licitaciones, estados=('analizado', 'favorita')):
    """Análisis activos hechos sin la rúbrica vigente (p. ej. históricos 1-10): candidatos a re-evaluar a pedido."""
    return [l for l in licitaciones if l.get('estado') in estados and l.get('descripcion_pro')
            and l.get('analisis_ia_json') and l.get('rubrica_version') != rubrica.RUBRICA_VERSION]


def cola_fuera_de_perfil(licitaciones, perfil):
    """Pendientes/extraídas cuyo título ya no coincide con las keywords del perfil."""
    positivas = normalizar_keywords((perfil or {}).get('keywords_pos'))
    negativas = normalizar_keywords((perfil or {}).get('keywords_neg'))
    if not positivas:
        return []
    return [l for l in licitaciones if l.get('estado') in ('pendiente', 'extraido')
            and not coincide_keywords(l.get('titulo'), positivas, negativas)]


def evaluacion_desactualizada(licit):
    """True si la evaluación humana es anterior al análisis vigente (hubo re-análisis)."""
    return bool(licit.get('eval_fecha') and licit.get('analisis_fecha') and licit['eval_fecha'] < licit['analisis_fecha'])


def agrupar_por_fecha(lista):
    """
    Agrupar por fecha de publicación en orden cronológico descendente;
    las licitaciones sin fecha válida quedan en un grupo final.

    Returns:
        list: [(etiqueta, [licitaciones]), ...]
    """
    grupos, sin_fecha = {}, []
    for l in lista:
        clave = fecha_iso(l.get('fecha_publicacion'))   # Normaliza formatos mixtos (BDs antiguas)
        if clave:
            grupos.setdefault(clave, []).append(l)
        else:
            sin_fecha.append(l)
    resultado = [(f"Publicadas el {formatear_fecha(k)}", grupos[k]) for k in sorted(grupos, reverse=True)]
    if sin_fecha:
        resultado.append(("Fecha de publicación no disponible", sin_fecha))
    return resultado


def filtrar_y_ordenar(lista, texto="", score_min=None, regiones=(), orden=ORDENES[0], ocultar_cerradas=False, ahora=None):
    """
    Aplicar los filtros de la vista de lista (función pura).

    - texto: busca en título y organismo, sin distinguir mayúsculas ni tildes.
    - score_min: mínimo en la escala 0-100 de la rúbrica. Con un mínimo > 0 quedan
      fuera las que no tienen score comparable (no elegibles, insuficientes, históricas).
    - regiones: si se indica, solo esas regiones.
    - orden: 'Cierre más próximo' (sin fecha al final), 'Mayor score' o 'Más recientes'.
    """
    busqueda = normalizar_texto(texto)
    resultado = []
    for l in lista:
        if busqueda and busqueda not in normalizar_texto(f"{l.get('titulo') or ''} {l.get('organismo') or ''}"):
            continue
        s = score_comparable(l)
        if score_min and (s is None or s < score_min):
            continue
        if regiones and l.get('region') not in regiones:
            continue
        if ocultar_cerradas and (dias_para_cierre(l.get('fecha_cierre'), ahora) or 0) < 0:
            continue
        resultado.append(l)

    if orden == "Mayor score":
        return sorted(resultado, key=clave_mayor_score)
    if orden == "Cierre más próximo":
        def clave_cierre(l):
            cierre = parsear_fecha_hora(l.get('fecha_cierre'))
            return (cierre is None, cierre or datetime.max, clave_mayor_score(l))
        return sorted(resultado, key=clave_cierre)
    return sorted(resultado, key=lambda l: fecha_iso(l.get('fecha_publicacion')) or "", reverse=True)


def metricas_resumen(licitaciones, ahora=None):
    """Indicadores de la cabecera. El promedio usa solo scores definitivos (los provisionales no son comparables)."""
    activas = [l for l in licitaciones if l.get('estado') in ('analizado', 'favorita')
               and (dias_para_cierre(l.get('fecha_cierre'), ahora) or 0) >= 0]
    resultados = [rubrica.resultado_guardado(l) for l in activas]
    scores = [r["valor"] for r in resultados if r["estado"] == rubrica.DEFINITIVO]
    return {
        "activas": len(activas),
        "cierran_7": sum(1 for l in activas if (d := dias_para_cierre(l.get('fecha_cierre'), ahora)) is not None and d <= 7),
        "score_promedio": round(sum(scores) / len(scores), 1) if scores else None,
        "n_definitivos": len(scores),
        "en_cola": sum(1 for l in licitaciones if l.get('estado') in ESTADOS_COLA),
    }


# --- Mensajes para el usuario final (sin jerga técnica; el detalle va al log) ---

def mensaje_error_amigable(texto):
    """Traducir un error técnico guardado (ultimo_error, detenido_por...) a lenguaje de usuario."""
    t = normalizar_texto(texto or "")
    reglas = [
        ("cerro antes", "La licitación cerró antes de poder analizarla."),
        ("keywords", "Ya no coincide con tus palabras clave de interés."),
        ("cuota", "Se alcanzó el límite de uso de la IA. Lo pendiente se analizará en la próxima sincronización."),
        ("sincronizacion en curso", "Ya hay una sincronización en curso. Espera a que termine e inténtalo de nuevo."),
        ("palabras clave", "Agrega al menos una palabra clave de interés en Perfil para empezar a buscar."),
        ("gemini_api_key", "Falta configurar el acceso a la IA (clave de Gemini en la configuración de la app)."),
        ("mp_ticket", "Falta configurar el acceso a Mercado Público (ticket de la API en la configuración de la app)."),
        ("chrome", "No se pudo abrir el navegador para leer el portal. Revisa que Google Chrome esté instalado."),
        ("no respondio", "Mercado Público no respondió a tiempo. Inténtalo más tarde."),
        ("timeout", "El portal de Mercado Público no respondió a tiempo."),
        ("api", "No se pudo consultar Mercado Público. Inténtalo más tarde."),
        ("no se encontro el enlace", "No se encontró la licitación en el buscador del portal."),
        ("texto de la ficha", "La ficha del portal no se pudo leer completa."),
        ("perfil de negocio", "Completa tu perfil de negocio para poder analizar licitaciones."),
        ("ia:", "La IA no entregó un análisis válido."),
        ("extraccion:", "No se pudo leer la ficha en el portal."),
    ]
    for patron, mensaje in reglas:
        if patron in t:
            return mensaje
    return "No se pudo completar el proceso."


def mensaje_sincronizacion(resumen, nivel):
    """Mensaje final de la sincronización para el usuario (el resumen técnico queda en el log)."""
    if nivel == "error":
        return mensaje_error_amigable(resumen.get("detenido_por") or resumen.get("error_descubrimiento"))
    partes = []
    n = resumen.get("analizadas", 0)
    if n:
        partes.append(f"{n} {'licitación nueva analizada' if n == 1 else 'licitaciones nuevas analizadas'}.")
    else:
        partes.append("No hubo licitaciones nuevas para analizar.")
    if resumen.get("en_cola"):
        partes.append(f"{resumen['en_cola']} quedan en espera para la próxima sincronización.")
    if resumen.get("fallidas"):
        partes.append(f"{resumen['fallidas']} no se pudieron completar y se reintentarán.")
    for aviso in (resumen.get("detenido_por"), resumen.get("error_descubrimiento")):
        if aviso:
            partes.append(mensaje_error_amigable(aviso))
    return " ".join(partes)


# ===================================================================
# HTML (presentación; todo texto externo se escapa)
# ===================================================================

def _chip(texto, icono=None, nivel=""):
    ico = f'<span class="l-ico">{icono}</span>' if icono else ""
    return f'<span class="l-chip {"l-" + nivel if nivel else ""}">{ico}{escape(str(texto))}</span>'


def html_anillo(res):
    """
    Resultado del score como anillo de progreso con el valor al centro (degradado cónico: sin SVG).
    Cada estado se distingue por el texto central, no solo por el color.
    """
    estado, valor = res["estado"], res["valor"]
    nivel, avance = res["nivel"], round(100 * valor / res["escala"]) if valor is not None else 0
    centro, pie = {
        rubrica.DEFINITIVO: (valor, "/100"),
        rubrica.PROVISIONAL: (valor, "PROV."),
        rubrica.HISTORICO: (valor, f"/{res['escala']} ANT."),
        rubrica.NO_ELEGIBLE: ("✕", "NO ELEG."),
        rubrica.INSUFICIENTE: ("?", "INCOMPL."),
    }.get(estado, ("–", "SCORE"))
    if estado == rubrica.NO_ELEGIBLE:
        nivel, avance = "bajo", 100
    titulo = rubrica.texto_resultado(res) if estado else "Sin análisis"
    return (f'<div class="l-anillo" title="{escape(titulo)}" '
            f'style="--p:{avance}%; --c:{COLOR_NIVEL[nivel]}">'
            f'<div class="l-anillo-txt"><b>{centro}</b><small>{pie}</small></div></div>')


def chips_score(res, analisis=None):
    """
    Chips con la interpretación del score y su estado (definitivo, provisional, especial o histórico).
    Si el score no es definitivo, también muestra lo que sí se sabe: el encaje comercial y
    si los requisitos quedaron por revisar en las bases.
    """
    estado = res["estado"]
    if estado == rubrica.HISTORICO:
        return [_chip("Escala anterior (1–10)", "history")]
    chips = {
        rubrica.DEFINITIVO: lambda: [_chip(res["etiqueta"], "insights", res["nivel"])],
        rubrica.PROVISIONAL: lambda: [_chip(f"Provisional · {res['etiqueta']}", "pending", "medio"),
                                      _chip(f"Cobertura {res['cobertura']} %", "rule")],
        rubrica.NO_ELEGIBLE: lambda: [_chip("No elegible", "block", "bajo")],
        rubrica.INSUFICIENTE: lambda: [_chip("Evaluación incompleta", "help")],
    }.get(estado, list)()
    criterios = (analisis or {}).get("criterios") or {}
    if estado in (rubrica.PROVISIONAL, rubrica.INSUFICIENTE, rubrica.NO_ELEGIBLE) and criterios:
        comercial = (criterios.get("comercial") or {}).get("nota")
        if isinstance(comercial, int):
            nivel = "alto" if comercial >= 4 else "medio" if comercial >= 2 else "bajo"
            chips.append(_chip(f"Encaje comercial {comercial}/{rubrica.NOTA_MAX}", "storefront", nivel))
        if (criterios.get("requisitos") or {}).get("nota") is None:
            chips.append(_chip("Requisitos: revisar bases", "description"))
    return chips


EVIDENCIA_LABELS = {"suficiente": "Evidencia suficiente", "parcial": "Evidencia parcial", "ausente": "Sin evidencia"}
EXCLUYENTE_LABELS = {"incumplido_confirmado": "No se cumple (confirmado)", "no_verificable": "No verificable",
                     "cumplido": "Se cumple"}


def html_desglose(analisis):
    """Tabla de la rúbrica: nota, peso, estado de evidencia y justificación de cada criterio."""
    criterios = (analisis or {}).get("criterios") or {}
    filas = []
    for c in rubrica.CRITERIOS:
        item = criterios.get(c.clave) or {}
        nota = item.get("nota")
        nota_txt = f"{nota}/{rubrica.NOTA_MAX}" if isinstance(nota, int) else "Sin nota"
        detalle = " · ".join(escape(str(x)) for x in (item.get("explicacion"), item.get("evidencia")) if x)
        filas.append(f'<tr><td><b>{escape(c.nombre)}</b><br><span class="l-nota">Peso {c.peso} %</span></td>'
                     f'<td class="l-crit-nota">{nota_txt}</td>'
                     f'<td>{escape(EVIDENCIA_LABELS.get(item.get("evidencia_estado"), "—"))}'
                     f'{"<br><span class=l-nota>" + detalle + "</span>" if detalle else ""}</td></tr>')
    return ('<table class="l-crit"><thead><tr><th>Criterio</th><th>Nota</th><th>Evidencia</th></tr></thead>'
            f'<tbody>{"".join(filas)}</tbody></table>')


def html_tarjeta(licit, analisis=None, ahora=None, perfil_anterior=False):
    """Cabecera de tarjeta: anillo de score, título, organismo y chips de contexto."""
    res = rubrica.resultado_guardado(licit)
    chips = chips_score(res, analisis) + [_chip(etiqueta_cierre(licit, ahora), "schedule", urgencia_cierre(licit, ahora))]
    if es_valor_util(licit.get('region')):
        chips.append(_chip(region_corta(licit['region']), "location_on"))
    if licit.get('reclamos_pago_n') is not None:
        chips.append(_chip(f"{licit['reclamos_pago_n']} reclamos de pago", "payments"))
    if perfil_anterior:
        chips.append(_chip("Analizada con un perfil anterior", "history", "medio"))
    return (f'<div class="l-tarjeta">{html_anillo(res)}<div class="l-cuerpo">'
            f'<p class="l-titulo">{escape(titulo_de(licit, analisis))}</p>'
            f'<p class="l-org">{escape(organismo_de(licit))} · <span class="l-id">{escape(licit["id_externo"])}</span></p>'
            f'<div class="l-chips">{"".join(chips)}</div></div></div>')


def html_lista(items):
    return '<ul class="l-lista">' + "".join(f"<li>{escape(str(i))}</li>" for i in items) + "</ul>"


def html_cabecera(titulo, subtitulo="", icono="radar"):
    sub = f"<p>{escape(subtitulo)}</p>" if subtitulo else ""
    return (f'<div class="l-cabecera"><div class="l-ico-pag"><span>{icono}</span></div>'
            f'<div><h1>{escape(titulo)}</h1>{sub}</div></div>')


def html_kpi(etiqueta, valor, icono, tinte="acento", pie=""):
    pie_html = f'<div class="l-kpi-pie">{escape(pie)}</div>' if pie else ""
    return (f'<div class="l-kpi"><div class="l-kpi-top"><span class="l-kpi-label">{escape(etiqueta)}</span>'
            f'<span class="l-kpi-ico l-tinte-{tinte}">{icono}</span></div>'
            f'<div class="l-kpi-valor">{escape(str(valor))}</div>{pie_html}</div>')


def html_vacio(titulo, texto, icono="inbox"):
    return (f'<div class="l-vacio"><span class="l-ico">{icono}</span>'
            f'<h4>{escape(titulo)}</h4><p>{escape(texto)}</p></div>')


def html_detalles_tecnicos(lineas):
    if not lineas:
        return ""
    return ('<details class="l-tec"><summary>Detalles técnicos</summary><div>'
            + "<br>".join(escape(x) for x in lineas) + '</div></details>')


# ===================================================================
# COMPONENTES COMPARTIDOS
# ===================================================================

def db():
    """Gestor de BD (uno por ejecución del script)."""
    return DatabaseManager()


def seccion(texto):
    st.html(f'<div class="l-seccion">{escape(texto)}</div>')


def vacio(titulo, texto, icono="inbox"):
    st.html(html_vacio(titulo, texto, icono))


def mostrar_mensaje_pendiente():
    """Mostrar (una vez) el resultado de la última acción, sobreviviendo al rerun."""
    mensaje = st.session_state.pop('ultimo_mensaje', None)
    if mensaje:
        nivel, texto = mensaje
        iconos = {"success": ":material/check_circle:", "error": ":material/error:",
                  "warning": ":material/warning:", "info": ":material/info:"}
        getattr(st, nivel, st.info)(texto, icon=iconos.get(nivel))


def cabecera(base, titulo, subtitulo, icono):
    """Cabecera común: título de la página a la izquierda; sincronización a la derecha."""
    c1, c2 = st.columns([3, 1.6], vertical_alignment="bottom")
    c1.html(html_cabecera(titulo, subtitulo, icono))
    with c2:
        ejecuciones = base.obtener_ejecuciones()
        if ejecuciones:
            u = ejecuciones[0]
            inicio = parsear_fecha_hora(u["inicio"])
            cuando = inicio.strftime("%d/%m %H:%M") if inicio else "—"
            st.html(f'<div class="l-sync">Última sincronización <b>{cuando}</b> · {u["analizadas"]} analizadas</div>')
        if st.button("Sincronizar ahora", icon=":material/sync:", type="primary", width="stretch", key="btn_sync",
                     help=f"Busca las licitaciones publicadas hoy y analiza hasta {config.MAX_PROCESAR} nuevas. "
                          "Puede tardar unos minutos."):
            with st.status("Buscando y analizando licitaciones…", expanded=False) as status:
                try:
                    # Importación diferida para evitar dependencias circulares
                    from main import ejecutar_pipeline, describir_resumen
                    resumen = ejecutar_pipeline(db=base)
                    nivel, _ = describir_resumen(resumen)
                    mensaje = mensaje_sincronizacion(resumen, nivel)
                    status.update(label="Sincronización finalizada", state="error" if nivel == "error" else "complete")
                except Exception:
                    log.exception("Error inesperado en la sincronización")
                    nivel, mensaje = "error", "Ocurrió un error inesperado durante la sincronización. El detalle quedó registrado."
                    status.update(label="No se pudo completar la sincronización", state="error")
            st.session_state['ultimo_mensaje'] = (nivel, mensaje)
            st.rerun()

    perfil = base.obtener_perfil() or {}
    if not normalizar_keywords(perfil.get('keywords_pos')):
        st.warning("Agrega al menos una palabra clave de interés en **Perfil** para empezar a buscar licitaciones.",
                   icon=":material/tune:")
    mostrar_mensaje_pendiente()


def _render_pago(licit):
    """Reclamos de pago con su procedencia: fuente oficial, lectura de la IA o sin datos."""
    fuente, ia = info_pago(licit)
    if fuente:
        st.html(f'<div class="l-pago"><span class="l-ico">verified</span>{escape(fuente)}</div>')
    if ia:
        st.html(f'<div class="l-nota">Lectura de la IA (sin verificar): {escape(ia)}</div>')
    if not fuente:
        # La ausencia de reclamos en el texto no equivale a bajo riesgo de pago
        st.html('<div class="l-nota">Sin datos verificados sobre pagos del organismo.</div>')


def _fechas_y_trazabilidad(l, con_analisis=True):
    cierre = formatear_fecha(l.get('fecha_cierre'), con_hora=True) or "No disponible"
    publicacion = formatear_fecha(l.get('fecha_publicacion')) or "No disponible"
    st.html(f'<div class="l-dato"><b>Publicación</b> {publicacion} &nbsp;·&nbsp; <b>Cierre</b> {cierre}</div>')
    if con_analisis:
        traza = texto_trazabilidad(l)
        if traza:
            st.html(f'<div class="l-nota">{escape(traza)}</div>' + html_detalles_tecnicos(detalles_tecnicos(l)))


def _reanalizar(base, id_externo):
    """Ejecutar un nuevo análisis real con Gemini; si falla se conserva el anterior."""
    from core.ai_analyst import AIAnalyst, AnalisisFallido, CuotaAgotada
    with st.spinner("Actualizando el análisis…"):
        try:
            analisis = AIAnalyst(base).analizar_licitacion(id_externo)
        except (ValueError, AnalisisFallido, CuotaAgotada) as e:
            log.warning(f"Re-análisis fallido de {id_externo}: {e}")
            motivo = mensaje_error_amigable(f"IA: {e}" if not isinstance(e, ValueError) else "GEMINI_API_KEY")
            st.session_state['ultimo_mensaje'] = ("error", f"No se pudo actualizar el análisis; se mantiene el anterior. {motivo}")
        else:
            res = rubrica.resultado_guardado(base.obtener_licitacion(id_externo) or {})
            st.session_state['ultimo_mensaje'] = ("success", f"Análisis actualizado: {rubrica.texto_resultado(res)}.")
    st.rerun()


def _form_evaluacion(base, l, prefijo):
    """
    Formulario de evaluación humana del análisis vigente. Las respuestas
    alimentan el gráfico de calibración y el dataset de la V2.
    """
    id_ext = l['id_externo']
    if evaluacion_desactualizada(l):
        st.warning("El análisis cambió desde tu última evaluación. Revísala.", icon=":material/history:")
    with st.form(f"eval_{prefijo}_{id_ext}", border=False):
        opciones_score = list(EVAL_SCORE_LABELS)
        opciones_post = list(POSTULARIA_LABELS)
        c1, c2 = st.columns(2)
        eval_score = c1.radio("¿El score de la IA es acertado?", opciones_score, format_func=EVAL_SCORE_LABELS.get,
                              index=opciones_score.index(l['eval_score']) if l.get('eval_score') in opciones_score else None,
                              horizontal=True, key=f"evs_{prefijo}_{id_ext}")
        postularia = c2.radio("¿Postularías?", opciones_post, format_func=POSTULARIA_LABELS.get,
                              index=opciones_post.index(l['eval_postularia']) if l.get('eval_postularia') in opciones_post else None,
                              horizontal=True, key=f"evp_{prefijo}_{id_ext}")
        comentario = st.text_input("Comentario (opcional)", value=l.get('eval_comentario') or "", key=f"evc_{prefijo}_{id_ext}",
                                   placeholder="Ej.: pide experiencia local que no tenemos")
        if st.form_submit_button("Guardar evaluación", icon=":material/check:", key=f"evb_{prefijo}_{id_ext}"):
            if not eval_score or not postularia:
                st.warning("Responde ambas preguntas para guardar tu evaluación.")
            else:
                base.guardar_evaluacion(id_ext, eval_score, postularia, comentario)
                st.session_state['ultimo_mensaje'] = ("success", "Evaluación guardada. ¡Gracias! Esto ayuda a medir qué tan acertada es la IA.")
                st.rerun()


def _render_rubrica(l, an, simplificado=False):
    """Estado del score, su motivo y (si no es simplificado) el desglose por criterio."""
    res = rubrica.resultado_guardado(l)
    r = an.get('rubrica') or {}
    if res["estado"] == rubrica.HISTORICO:
        st.html('<div class="l-nota">Este análisis usa la escala anterior (1–10), sin desglose por criterio. '
                'Puedes actualizarlo con la rúbrica actual desde «Más» o desde Perfil.</div>')
        return
    if not res["estado"]:   # Análisis sin score registrado: no hay desglose que mostrar
        return
    if r.get('motivo'):
        st.html(f'<div class="l-aviso">{escape(r["motivo"])}</div>')
    if simplificado:
        return
    seccion("Desglose del score")
    st.html(html_desglose(an))
    excluyentes = an.get('requisitos_excluyentes') or []
    if excluyentes:
        seccion("Requisitos excluyentes")
        st.html(html_lista(f"{e.get('requisito')} — {EXCLUYENTE_LABELS.get(e.get('estado'), e.get('estado'))}"
                           + (f" ({e['evidencia']})" if e.get('evidencia') else "") for e in excluyentes))
    if an.get('datos_faltantes'):
        seccion("Información faltante")
        st.html(html_lista(an['datos_faltantes']))
    advertencias = list(an.get('advertencias') or []) + list(r.get('advertencias') or [])
    if an.get('corpus_truncado'):
        advertencias.append("La ficha era muy extensa y la IA solo leyó una parte; puede faltar información.")
    if advertencias:
        st.html('<div class="l-nota"><b>Advertencias:</b> ' + " · ".join(escape(str(a)) for a in advertencias) + '</div>')
    if an.get('hechos_fuente') or an.get('inferencias'):
        st.html('<details class="l-tec l-tec-texto"><summary>Hechos de la ficha e inferencias de la IA</summary><div>'
                + ('<b>Hechos de la ficha</b>' + html_lista(an['hechos_fuente']) if an.get('hechos_fuente') else '')
                + ('<b>Inferencias de la IA</b>' + html_lista(an['inferencias']) if an.get('inferencias') else '')
                + '</div></details>')
    st.html('<div class="l-nota">El score mide la compatibilidad con tu perfil; no es la probabilidad de adjudicarte '
            'la licitación. Sus pesos y rangos son iniciales y aún no están validados.</div>')


def _detalle_analisis(base, l, an, simplificado=False, prefijo="lista"):
    """Contenido del desplegable: veredicto, score, puntos críticos, riesgos, pagos, fechas y evaluación."""
    res = rubrica.resultado_guardado(l)
    if an:
        st.html(f'<div class="l-veredicto"><b>Veredicto IA ·</b> {escape(an.get("veredicto") or "Sin veredicto")}</div>')
        _render_rubrica(l, an, simplificado)
        if not simplificado:
            c1, c2 = st.columns(2)
            with c1:
                seccion("Puntos críticos")
                st.html(html_lista(an['puntos_criticos'][:3]) if an['puntos_criticos'] else '<div class="l-nota">—</div>')
            with c2:
                seccion("Riesgos comerciales")
                st.html(html_lista(an['riesgos'][:3]) if an['riesgos'] else '<div class="l-nota">—</div>')
            if sugiere_descartar(res) and es_valor_util(l.get('motivo_archivo')):
                st.html(f'<div class="l-nota">Por qué la IA sugiere descartarla: {escape(l["motivo_archivo"])}</div>')
    elif l.get('analisis_ia_json'):
        st.warning("Este análisis no está disponible.")

    seccion("Pagos del organismo")
    _render_pago(l)
    _fechas_y_trazabilidad(l, con_analisis=bool(an))

    if an and not simplificado:
        seccion("Tu evaluación")
        _form_evaluacion(base, l, prefijo)


def _acciones(base, l):
    """Botones de estado y de re-análisis de una tarjeta."""
    id_ext = l['id_externo']
    if l['estado'] == 'analizado':
        if st.button("Favorita", icon=":material/star:", key=f"fav_{id_ext}", width="stretch"):
            base.cambiar_estado(id_ext, 'favorita'); st.rerun()
        if st.button("Archivar", icon=":material/archive:", key=f"arc_{id_ext}", width="stretch"):
            base.cambiar_estado(id_ext, 'archivada'); st.rerun()
    else:
        if st.button("Restaurar", icon=":material/undo:", key=f"re_{id_ext}", width="stretch",
                     help="Volver a Oportunidades"):
            base.cambiar_estado(id_ext, 'analizado'); st.rerun()
    _mas_acciones(base, l, f"ia_{id_ext}")


def _mas_acciones(base, l, clave_reanalizar):
    """Acciones secundarias (portal y re-análisis) agrupadas en un menú."""
    if not l.get('link') and not l.get('descripcion_pro'):
        return
    with st.popover("Más", icon=":material/more_horiz:", width="stretch"):
        if l.get('link'):
            st.link_button("Ver en Mercado Público", l['link'], icon=":material/open_in_new:", width="stretch")
        if l.get('descripcion_pro'):
            if st.button("Actualizar análisis", icon=":material/refresh:", key=clave_reanalizar, width="stretch",
                         help="Pide un análisis nuevo a la IA. Si algo falla, se mantiene el actual."):
                _reanalizar(base, l['id_externo'])


def _clave_tarjeta(prefijo, l):
    """Key del contenedor; incluye la urgencia para la franja de color (ver estilos)."""
    return f"lcard_u-{urgencia_cierre(l) or 'n'}_{prefijo}{l['id_externo']}"


def tarjeta(base, l, simplificado=False, version_actual=None):
    """Una licitación como tarjeta: cabecera HTML, acciones y desplegable con el análisis."""
    an = cargar_analisis_guardado(l.get('analisis_ia_json'))
    perfil_anterior = bool(version_actual) and analisis_con_perfil_anterior(l, version_actual)
    with st.container(border=True, key=_clave_tarjeta("", l)):
        c1, c2 = st.columns([5, 1.25])
        c1.html(html_tarjeta(l, an, perfil_anterior=perfil_anterior))
        with c2:
            _acciones(base, l)
        with st.expander("Análisis y evaluación" if not simplificado else "Ver análisis", icon=":material/insights:"):
            _detalle_analisis(base, l, an, simplificado)


def _filtros(lista, clave, ocultar_cerradas=True):
    """Fila única de filtros sobre la lista; devuelve (filtradas, orden)."""
    regiones = sorted({l['region'] for l in lista if es_valor_util(l.get('region'))})
    c1, c2, c3 = st.columns([2.2, 1.2, 1.7], vertical_alignment="bottom")
    texto = c1.text_input("Buscar", placeholder="Título u organismo", key=f"f_txt_{clave}", icon=":material/search:")
    score_min = c2.select_slider("Score mínimo", options=list(range(0, 101, 5)), value=0, key=f"f_score_{clave}",
                                 help="Escala 0–100. Con un mínimo mayor que 0 se ocultan las no elegibles, "
                                      "las de evaluación insuficiente y las de la escala anterior.")
    sel_regiones = c3.multiselect("Región", regiones, key=f"f_reg_{clave}", placeholder="Todas las regiones",
                                  format_func=region_corta)
    c4, c5 = st.columns([3, 1], vertical_alignment="center")
    # Radio con aspecto de "píldoras" (CSS en estilos: key "pill_*")
    orden = c4.radio("Ordenar por", ORDENES, key=f"pill_ord_{clave}", horizontal=True,
                     label_visibility="collapsed") or ORDENES[0]
    ocultar = c5.toggle("Ocultar cerradas", value=ocultar_cerradas, key=f"f_cer_{clave}")
    filtradas = filtrar_y_ordenar(lista, texto, score_min, sel_regiones, orden, ocultar)
    st.caption(f"{len(filtradas)} de {len(lista)} licitaciones")
    return filtradas, orden


def lista_tarjetas(base, lista, clave, simplificado=False, ocultar_cerradas=True,
                   vacio_titulo="Nada por aquí", vacio_texto="No hay licitaciones para mostrar."):
    """Lista filtrable de tarjetas."""
    if not lista:
        vacio(vacio_titulo, vacio_texto)
        return
    filtradas, orden = _filtros(lista, clave, ocultar_cerradas)
    if not filtradas:
        vacio("Sin resultados", "Ninguna licitación coincide con los filtros. Prueba ampliando la búsqueda.", "filter_alt_off")
        return
    version = version_perfil(base.obtener_perfil())
    if orden == "Más recientes":
        for etiqueta, grupo in agrupar_por_fecha(filtradas):
            seccion(etiqueta)
            for l in grupo:
                tarjeta(base, l, simplificado, version)
    else:
        for l in filtradas:
            tarjeta(base, l, simplificado, version)


# ===================================================================
# PÁGINAS
# ===================================================================

def pagina_oportunidades():
    base = db()
    cabecera(base, "Oportunidades", "Licitaciones que la IA evaluó según tu perfil de negocio.", "target")
    todas = base.obtener_licitaciones()
    m = metricas_resumen(todas)
    promedio = f"{m['score_promedio']}".replace(".", ",") if m["score_promedio"] is not None else "—"
    kpis = [("Oportunidades activas", m["activas"], "target", "acento", "Abiertas, incluidas favoritas"),
            ("Cierran esta semana", m["cierran_7"], "schedule", "medio" if m["cierran_7"] else "acento", "En los próximos 7 días"),
            ("Score promedio", promedio, "insights", "alto",
             f"De {m['n_definitivos']} con score definitivo (0–100)" if m["n_definitivos"] else "Sin scores definitivos aún"),
            ("En proceso", m["en_cola"], "pending_actions", "acento", "Esperando lectura o análisis")]
    for col, (etiqueta, valor, icono, tinte, pie) in zip(st.columns(4), kpis):
        col.html(html_kpi(etiqueta, valor, icono, tinte, pie))
    st.write("")
    lista_tarjetas(base, [l for l in todas if l['estado'] == 'analizado'], "analizadas",
                   vacio_titulo="Aún no hay oportunidades",
                   vacio_texto="Pulsa «Sincronizar ahora» para buscar y analizar las licitaciones publicadas hoy.")


def pagina_favoritas():
    base = db()
    cabecera(base, "Favoritas", "Las oportunidades que estás preparando, ordenadas por fecha de cierre.", "star")
    favs = filtrar_y_ordenar([l for l in base.obtener_licitaciones() if l['estado'] == 'favorita'], orden="Cierre más próximo")
    if not favs:
        vacio("Aún no tienes favoritas", "Marca como favoritas las oportunidades que quieras preparar.", "star")
        return

    version = version_perfil(base.obtener_perfil())
    for l in favs:
        an = cargar_analisis_guardado(l.get('analisis_ia_json'))
        with st.container(border=True, key=_clave_tarjeta("fav_", l)):
            c_head, c_acc = st.columns([5, 1.25])
            c_head.html(html_tarjeta(l, an, perfil_anterior=bool(version) and analisis_con_perfil_anterior(l, version)))
            with c_acc:
                if st.button("Quitar", icon=":material/star_half:", key=f"back_{l['id_externo']}", width="stretch",
                             help="Quitar de Favoritas"):
                    base.cambiar_estado(l['id_externo'], 'analizado'); st.rerun()
                _mas_acciones(base, l, f"iaf_{l['id_externo']}")

            c1, c2 = st.columns([1.9, 1], gap="large")
            with c1:
                if an:
                    st.html(f'<div class="l-veredicto"><b>Veredicto IA ·</b> {escape(an.get("veredicto") or "Sin veredicto")}</div>')
                    _render_rubrica(l, an)
                    a, b = st.columns(2)
                    with a:
                        seccion("Puntos clave")
                        st.html(html_lista(an['puntos_criticos']) if an['puntos_criticos'] else '<div class="l-nota">—</div>')
                    with b:
                        seccion("Riesgos")
                        st.html(html_lista(an['riesgos']) if an['riesgos'] else '<div class="l-nota">—</div>')
                else:
                    st.html('<div class="l-nota">Esta licitación aún no tiene análisis.</div>')
                seccion("Pagos del organismo")
                _render_pago(l)
                _fechas_y_trazabilidad(l, con_analisis=bool(an))
                if an:
                    with st.expander("Tu evaluación", icon=":material/rate_review:", expanded=evaluacion_desactualizada(l)):
                        _form_evaluacion(base, l, "fav")

            with c2:
                # Gestión operativa persistida en la BD
                seccion("Preparación")
                try:
                    checklist = json.loads(l.get('checklist_json') or '{}')
                except ValueError:
                    checklist = {}
                with st.form(f"notas_{l['id_externo']}", border=False):
                    valores = {clave: st.checkbox(etiqueta, value=bool(checklist.get(clave)), key=f"chk_{clave}_{l['id_externo']}")
                               for clave, etiqueta in CHECKLIST_ITEMS.items()}
                    notas = st.text_area("Notas internas", value=l.get('notas') or '', placeholder="Ej.: costos revisados con proveedor…",
                                         key=f"txt_{l['id_externo']}", height=110)
                    if st.form_submit_button("Guardar notas", icon=":material/check:", width="stretch"):
                        base.guardar_notas(l['id_externo'], notas, valores)
                        st.session_state['ultimo_mensaje'] = ("success", "Notas guardadas.")
                        st.rerun()


def pagina_archivo():
    base = db()
    cabecera(base, "Archivo", "Licitaciones que descartaste. Puedes restaurarlas cuando quieras.", "archive")
    lista_tarjetas(base, [l for l in base.obtener_licitaciones() if l['estado'] == 'archivada'], "archivadas",
                   simplificado=True, ocultar_cerradas=False,
                   vacio_titulo="El archivo está vacío", vacio_texto="Las licitaciones que archives aparecerán aquí.")


def pagina_cola():
    """Licitaciones aún no analizadas (pendientes, extraídas o con error): ninguna queda oculta."""
    base = db()
    cabecera(base, "En proceso",
             "Licitaciones que aún no terminan de analizarse. Se reintentan solas en las próximas sincronizaciones.",
             "pending_actions")
    lista = orden_cola([l for l in base.obtener_licitaciones() if l['estado'] in ESTADOS_COLA])
    if not lista:
        vacio("Todo al día", "No hay licitaciones esperando ni con problemas.", "task_alt")
        return
    st.caption("Ordenadas como se procesarán: primero las que cierran antes. "
               "Usa «Analizar ahora» para no esperar a la próxima sincronización.")
    estados = {
        'pendiente': ("Esperando lectura del portal", "hourglass_top", ""),
        'extraido': ("Esperando análisis de IA", "neurology", "medio"),
        'error': ("No se pudo completar", "error", "bajo"),
    }
    for l in lista:
        texto, icono, nivel = estados.get(l['estado'], ("En proceso", "help", ""))
        with st.container(border=True, key=f"lcard_cola_{l['id_externo']}"):
            c1, c2 = st.columns([5, 1.25], vertical_alignment="center")
            chips = [_chip(texto, icono, nivel), _chip(etiqueta_cierre(l), "schedule", urgencia_cierre(l))]
            if l['estado'] != 'error' and l.get('intentos'):
                chips.append(_chip(f"Intento {l['intentos']} de {config.MAX_INTENTOS}", "replay"))
            error = ""
            if l.get('ultimo_error'):
                error = (f'<div class="l-nota" style="margin-top:.55rem">{escape(mensaje_error_amigable(l["ultimo_error"]))}</div>'
                         + html_detalles_tecnicos([l["ultimo_error"]]))
            c1.html(f'<p class="l-titulo">{escape(titulo_de(l))}</p>'
                    f'<p class="l-org"><span class="l-id">{escape(l["id_externo"])}</span></p>'
                    f'<div class="l-chips">{"".join(chips)}</div>{error}')
            with c2:
                if st.button("Analizar ahora", icon=":material/bolt:", key=f"now_{l['id_externo']}", width="stretch",
                             type="primary" if l['estado'] != 'error' else "secondary",
                             help="La analiza en este momento, sin esperar a la próxima sincronización. Usa 1 análisis "
                                  "de IA; si la ficha aún no se leyó, primero abre el portal (puede tardar un minuto)."):
                    _analizar_ahora(base, l['id_externo'])
                if l['estado'] == 'error':
                    if st.button("Reintentar", icon=":material/replay:", key=f"retry_{l['id_externo']}", width="stretch",
                                 help="La devuelve a la cola para la próxima sincronización."):
                        base.reintentar(l['id_externo']); st.rerun()


def orden_cola(lista):
    """
    Orden de la página En proceso: el mismo de la cola (cierre más próximo, menos
    intentos, más antigua) y al final las que no se pudieron completar.
    """
    return sorted(lista, key=lambda l: (l['estado'] == 'error', l.get('fecha_cierre') is None,
                                        l.get('fecha_cierre') or "", l.get('intentos') or 0,
                                        l.get('fecha_creacion') or "", l['id_externo']))


def mensaje_analisis_a_pedido(resultado, motivo, licit=None):
    """Traducir el resultado de `main.analizar_ahora` a (nivel, mensaje) para el usuario."""
    if resultado == "analizada":
        res = rubrica.resultado_guardado(licit or {})
        return "success", f"Análisis listo: {rubrica.texto_resultado(res)}. Ya está en Oportunidades."
    if resultado == "fallida":
        return "error", f"No se pudo completar el análisis. {mensaje_error_amigable(motivo)} Se reintentará en la próxima sincronización."
    if resultado == "no_disponible":
        return "info", "Esta licitación ya no está en proceso."
    clave = {"cuota": "cuota", "sin_navegador": "chrome", "en_curso": "sincronizacion en curso",
             "sin_configurar": "gemini_api_key", "cerrada": "cerro antes"}.get(resultado, "")
    return "warning" if resultado == "cerrada" else "error", mensaje_error_amigable(clave or motivo)


def _analizar_ahora(base, id_externo):
    """Ejecutar el análisis a pedido de una licitación de la cola y mostrar el resultado."""
    from main import analizar_ahora
    with st.spinner("Analizando la licitación…"):
        try:
            resultado, motivo = analizar_ahora(base, id_externo)
        except Exception:
            log.exception(f"Error inesperado en el análisis a pedido de {id_externo}")
            resultado, motivo = "fallida", "error inesperado"
    st.session_state['ultimo_mensaje'] = mensaje_analisis_a_pedido(resultado, motivo, base.obtener_licitacion(id_externo))
    st.rerun()


def pagina_panorama():
    from web import panorama
    base = db()
    cabecera(base, "Panorama", "Cómo funciona tu radar: qué encuentra, qué cierra pronto y qué tan acertada es la IA.",
             "monitoring")
    panorama.render(base)
    st.write("")
    _exportar(base)


def _exportar(base):
    """Descarga de los datos en formatos independientes del esquema SQLite."""
    with st.container(border=True, key="lcard_exportar"):
        seccion("Descargar datos")
        st.caption("Tus oportunidades con su análisis y tus evaluaciones. Las notas internas no se incluyen.")
        exportables = [l for l in base.obtener_licitaciones() if l.get('estado') in ('analizado', 'favorita', 'archivada')]
        incluir_ficha = st.checkbox("Incluir el texto completo de cada ficha (solo en JSON; el archivo será más pesado)", key="exp_ficha")
        sello = datetime.now().strftime("%Y%m%d-%H%M")
        c1, c2, _ = st.columns([1, 1, 2])
        c1.download_button("Excel (CSV)", a_csv(exportables), file_name=f"licitai-{sello}.csv", icon=":material/table_view:",
                           mime="text/csv", on_click="ignore", width="stretch", disabled=not exportables)
        c2.download_button("JSON", a_json(exportables, incluir_ficha), file_name=f"licitai-{sello}.json", icon=":material/data_object:",
                           mime="application/json", on_click="ignore", width="stretch", disabled=not exportables)
        st.caption(f"{len(exportables)} licitaciones con análisis.")


def pagina_perfil():
    """Formulario del perfil de negocio."""
    base = db()
    cabecera(base, "Perfil de negocio", "Qué buscar en Mercado Público y cómo debe evaluar la IA cada oportunidad.", "tune")
    perfil = base.obtener_perfil() or {}
    with st.container(border=True, key="lcard_perfil"):
        with st.form("perfil_form", border=False):
            c1, c2 = st.columns(2)
            with c1:
                keywords_pos = st.text_area("Palabras clave de interés", perfil.get('keywords_pos') or '', height=120,
                                            placeholder="Ej.: reactivos, microscopio, laboratorio clínico",
                                            help="Sepáralas con comas. Basta con que el título de la licitación contenga una. "
                                                 "No importan mayúsculas ni tildes.")
            with c2:
                keywords_neg = st.text_area("Palabras a excluir", perfil.get('keywords_neg') or '', height=120,
                                            placeholder="Ej.: aseo, guardias, uniformes",
                                            help="Sepáralas con comas. Si el título contiene alguna, la licitación se descarta.")
            bio = st.text_area("Describe tu empresa", perfil.get('bio_estrategica') or '', height=160,
                               placeholder="Qué vendes, a quién, en qué te especializas y qué tipo de contratos te interesan.",
                               help="La IA usa esta descripción para evaluar qué tan conveniente es cada licitación para ti.")
            if st.form_submit_button("Guardar cambios", icon=":material/check:", type="primary"):
                # regiones: reservado, sin uso en el filtrado
                base.guardar_perfil(keywords_pos, keywords_neg, perfil.get('regiones'), bio)
                cambio = version_perfil(base.obtener_perfil()) != version_perfil(perfil)
                st.session_state['ultimo_mensaje'] = ("success", "Perfil actualizado." + (
                    " Los análisis que ya tienes no cambian: más abajo puedes actualizarlos." if cambio else ""))
                st.rerun()

    _impacto_perfil(base, base.obtener_perfil())


def _impacto_perfil(base, perfil):
    """Qué datos quedaron desalineados con el perfil actual y cómo corregirlos (siempre a pedido)."""
    version = version_perfil(perfil)
    if not version:
        return
    todas = base.obtener_licitaciones()
    por_perfil = afectados_por_perfil(todas, version)
    por_rubrica = con_rubrica_anterior(todas)
    ids_perfil = {l['id_externo'] for l in por_perfil}
    afectados = por_perfil + [l for l in por_rubrica if l['id_externo'] not in ids_perfil]
    fuera = cola_fuera_de_perfil(todas, perfil)

    with st.container(border=True, key="lcard_perfil_impacto"):
        seccion("Análisis y perfil actual")
        if not afectados and not fuera:
            st.html('<div class="l-dato">Todos tus análisis están al día con este perfil y con la rúbrica del score.</div>')
            return
        st.caption("Cambiar el perfil o la rúbrica no modifica los análisis existentes. Si quieres, puedes actualizarlos aquí; "
                   "el análisis anterior queda guardado en el historial.")

        if afectados:
            if por_perfil:
                st.markdown(f"**{len(por_perfil)}** {'oportunidad se analizó' if len(por_perfil) == 1 else 'oportunidades se analizaron'} "
                            "con una versión anterior de tu perfil, así que su score podría no reflejar lo que buscas hoy.")
            if por_rubrica:
                st.markdown(f"**{len(por_rubrica)}** {'oportunidad tiene' if len(por_rubrica) == 1 else 'oportunidades tienen'} "
                            "un score con la rúbrica anterior (escala 1–10), que no se compara con el actual (0–100).")
            confirmar = st.checkbox(f"Entiendo que esto usará hasta {len(afectados)} análisis de IA", key="conf_reanalisis")
            if st.button(f"Actualizar {len(afectados)} análisis", icon=":material/refresh:", disabled=not confirmar,
                         key="btn_reanalizar_lote"):
                from main import reanalizar_lote
                barra = st.progress(0.0, text="Actualizando análisis…")
                r = reanalizar_lote(base, [l['id_externo'] for l in afectados],
                                    al_avanzar=lambda hechas, total: barra.progress(hechas / total, text=f"{hechas} de {total}"))
                texto = f"Se actualizaron {r['reanalizadas']} de {r['total']} análisis."
                if r["fallidas"]:
                    texto += f" {len(r['fallidas'])} no se pudieron actualizar y mantienen su análisis anterior."
                if r["detenido_por"]:
                    texto += " " + mensaje_error_amigable(r["detenido_por"])
                nivel = "success" if r["reanalizadas"] == r["total"] else "warning" if r["reanalizadas"] else "error"
                st.session_state['ultimo_mensaje'] = (nivel, texto)
                st.rerun()

        if fuera:
            st.markdown(f"**{len(fuera)}** {'licitación en proceso ya no coincide' if len(fuera) == 1 else 'licitaciones en proceso ya no coinciden'} "
                        "con tus palabras clave y se analizarían igual.")
            if st.button("Descartarlas", icon=":material/playlist_remove:", key="btn_quitar_cola",
                         help="Dejan de procesarse. Podrás reintentarlas desde En proceso."):
                for l in fuera:
                    base.marcar_error(l['id_externo'], "Ya no coincide con las keywords del perfil")
                st.session_state['ultimo_mensaje'] = ("success", f"{len(fuera)} licitaciones descartadas del proceso.")
                st.rerun()
