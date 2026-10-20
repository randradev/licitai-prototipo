# -*- coding: utf-8 -*-
"""
Módulo: Vistas (vistas)
----------------------
Capa de presentación del dashboard. Contiene:
1. Helpers puros (sin Streamlit) para formatear, filtrar y resumir licitaciones.
2. Constructores de HTML para tarjetas e insignias (todo texto externo se escapa).
3. Las funciones que dibujan cada página (las invoca web/paginas/*.py).

Los widgets interactivos (botones, formularios) son de Streamlit; el HTML solo
se usa para presentar información.
"""

import json
import logging
from datetime import datetime
from html import escape

import streamlit as st
from core import config
from core.database_mgr import DatabaseManager
from core.exportar import a_csv, a_json
from core.parsing import (cargar_analisis_guardado, dias_para_cierre, es_valor_util, fecha_iso, formatear_fecha,
                          normalizar_keywords, normalizar_texto, parsear_fecha_hora)

log = logging.getLogger("licitai.web")

# Ítems del checklist de gestión (clave persistida -> etiqueta)
CHECKLIST_ITEMS = {"bases_leidas": "Bases leídas", "anexos_preparados": "Anexos preparados"}

# Evaluación humana del análisis (clave persistida -> etiqueta)
EVAL_SCORE_LABELS = {"acertado": "Acertado", "muy_alto": "Muy alto", "muy_bajo": "Muy bajo"}
POSTULARIA_LABELS = {"si": "Sí", "tal_vez": "Tal vez", "no": "No"}

ORDENES = ("Cierre más próximo", "Mayor score", "Más recientes")
ESTADOS_COLA = ("pendiente", "extraido", "error")


# ===================================================================
# HELPERS DE PRESENTACIÓN (puros, sin Streamlit)
# ===================================================================

def score_de(licit):
    """Devolver el score como entero, o None si no existe o no es válido."""
    try:
        return int(licit.get('score_ia'))
    except (TypeError, ValueError):
        return None


def nivel_score(score):
    """Nivel según los umbrales únicos de core/config.py: 'alto' | 'medio' | 'bajo' | 'nulo'."""
    if score is None:
        return "nulo"
    return "alto" if score >= config.UMBRAL_ALTO else "medio" if score >= config.UMBRAL_MEDIO else "bajo"


def texto_score(score):
    return f"{score}/{config.SCORE_MAX}" if score is not None else "Sin score"


def titulo_de(licit, analisis=None):
    """Resolver el título a mostrar: dato de la fuente, luego IA, luego el ID."""
    if es_valor_util(licit.get('titulo')) and licit.get('titulo') != f"Licitación {licit['id_externo']}":
        return licit['titulo']
    if analisis and es_valor_util(analisis.get('titulo_recuperado')):
        return analisis['titulo_recuperado']
    return f"Licitación {licit['id_externo']}"


def organismo_de(licit):
    return licit['organismo'] if es_valor_util(licit.get('organismo')) else "Organismo no detectado"


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
        fuente = f"{n} reclamos por incumplir plazo de pago (últimos 12 meses) — fuente: ficha de Mercado Público"
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
    """Describir con qué modelo, prompt y cuándo se generó el análisis vigente."""
    if not licit.get('analisis_fecha'):
        return "Análisis sin registro de modelo ni versión (anterior a la trazabilidad)."
    return (f"Análisis del {formatear_fecha(licit['analisis_fecha'], con_hora=True)} · "
            f"modelo {licit.get('analisis_modelo') or '?'} · prompt {licit.get('analisis_prompt_version') or '?'}")


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
    - score_min: excluye las que no alcanzan el score (las sin score se excluyen si hay mínimo > 1).
    - regiones: si se indica, solo esas regiones.
    - orden: 'Cierre más próximo' (sin fecha al final), 'Mayor score' o 'Más recientes'.
    """
    busqueda = normalizar_texto(texto)
    resultado = []
    for l in lista:
        if busqueda and busqueda not in normalizar_texto(f"{l.get('titulo') or ''} {l.get('organismo') or ''}"):
            continue
        s = score_de(l)
        if score_min and score_min > 1 and (s is None or s < score_min):
            continue
        if regiones and l.get('region') not in regiones:
            continue
        if ocultar_cerradas and (dias_para_cierre(l.get('fecha_cierre'), ahora) or 0) < 0:
            continue
        resultado.append(l)

    if orden == "Mayor score":
        return sorted(resultado, key=lambda l: -(score_de(l) or 0))
    if orden == "Cierre más próximo":
        def clave_cierre(l):
            cierre = parsear_fecha_hora(l.get('fecha_cierre'))
            return (cierre is None, cierre or datetime.max, -(score_de(l) or 0))
        return sorted(resultado, key=clave_cierre)
    return sorted(resultado, key=lambda l: fecha_iso(l.get('fecha_publicacion')) or "", reverse=True)


def metricas_resumen(licitaciones, ahora=None):
    """Indicadores de la cabecera."""
    activas = [l for l in licitaciones if l.get('estado') in ('analizado', 'favorita')
               and (dias_para_cierre(l.get('fecha_cierre'), ahora) or 0) >= 0]
    scores = [score_de(l) for l in activas if score_de(l) is not None]
    return {
        "activas": len(activas),
        "cierran_7": sum(1 for l in activas if (d := dias_para_cierre(l.get('fecha_cierre'), ahora)) is not None and d <= 7),
        "score_promedio": round(sum(scores) / len(scores), 1) if scores else None,
        "en_cola": sum(1 for l in licitaciones if l.get('estado') in ESTADOS_COLA),
    }


# ===================================================================
# HTML (presentación; todo texto externo se escapa)
# ===================================================================

def _chip(texto, icono=None, nivel=""):
    ico = f'<span class="l-ico">{icono}</span>' if icono else ""
    return f'<span class="l-chip {"l-" + nivel if nivel else ""}">{ico}{escape(str(texto))}</span>'


def html_tarjeta(licit, analisis=None, ahora=None):
    """Cabecera de tarjeta: insignia de score, título, organismo y chips de contexto."""
    score = score_de(licit)
    nivel = nivel_score(score)
    insignia = (f'<div class="l-score l-{nivel}"><b>{score if score is not None else "–"}</b>'
                f'<span>{"score" if score is not None else "s/score"}</span></div>')
    chips = [_chip(etiqueta_cierre(licit, ahora), "schedule", urgencia_cierre(licit, ahora))]
    if es_valor_util(licit.get('region')):
        chips.append(_chip(region_corta(licit['region']), "location_on"))
    if licit.get('reclamos_pago_n') is not None:
        chips.append(_chip(f"{licit['reclamos_pago_n']} reclamos de pago", "payments"))
    return (f'<div class="l-tarjeta">{insignia}<div class="l-cuerpo">'
            f'<p class="l-titulo">{escape(titulo_de(licit, analisis))}</p>'
            f'<p class="l-org">{escape(organismo_de(licit))} · <span class="l-id">{escape(licit["id_externo"])}</span></p>'
            f'<div class="l-chips">{"".join(chips)}</div></div></div>')


def html_lista(items):
    return '<ul class="l-lista">' + "".join(f"<li>{escape(str(i))}</li>" for i in items) + "</ul>"


def html_cabecera(titulo, subtitulo=""):
    sub = f"<p>{escape(subtitulo)}</p>" if subtitulo else ""
    return f'<div class="l-cabecera"><h1>{escape(titulo)}</h1>{sub}</div>'


# ===================================================================
# COMPONENTES COMPARTIDOS
# ===================================================================

def db():
    """Gestor de BD (uno por ejecución del script)."""
    return DatabaseManager()


def seccion(texto):
    st.html(f'<div class="l-seccion">{escape(texto)}</div>')


def mostrar_mensaje_pendiente():
    """Mostrar (una vez) el resultado de la última acción, sobreviviendo al rerun."""
    mensaje = st.session_state.pop('ultimo_mensaje', None)
    if mensaje:
        nivel, texto = mensaje
        iconos = {"success": ":material/check_circle:", "error": ":material/error:",
                  "warning": ":material/warning:", "info": ":material/info:"}
        getattr(st, nivel, st.info)(texto, icon=iconos.get(nivel))


def cabecera(base, titulo, subtitulo):
    """Cabecera común: título de la página a la izquierda; sincronización a la derecha."""
    c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
    c1.html(html_cabecera(titulo, subtitulo))
    with c2:
        ejecuciones = base.obtener_ejecuciones()
        if ejecuciones:
            u = ejecuciones[0]
            st.caption(f"Última sincronización: {formatear_fecha(u['inicio'], con_hora=True)} · "
                       f"{u['analizadas']} analizadas de {u['total_listado']} en el listado")
        if st.button("Sincronizar ahora", icon=":material/sync:", type="primary", width="stretch", key="btn_sync",
                     help=f"Consulta las licitaciones publicadas hoy y procesa hasta {config.MAX_PROCESAR} de la cola. "
                          "Puede tardar varios minutos."):
            with st.status("Sincronizando con Mercado Público…", expanded=False) as status:
                try:
                    # Importación diferida para evitar dependencias circulares
                    from main import ejecutar_pipeline, describir_resumen
                    resumen = ejecutar_pipeline(db=base)
                    nivel, mensaje = describir_resumen(resumen)
                    status.update(label="Sincronización finalizada", state="error" if nivel == "error" else "complete")
                except Exception as e:
                    log.exception("Error inesperado en la sincronización")
                    nivel, mensaje = "error", f"Error inesperado en el proceso: {type(e).__name__}: {e}"
                    status.update(label="Error en la sincronización", state="error")
            st.session_state['ultimo_mensaje'] = (nivel, mensaje)
            st.rerun()

    perfil = base.obtener_perfil() or {}
    if not normalizar_keywords(perfil.get('keywords_pos')):
        st.warning("Configura al menos una keyword positiva en **Perfil**: sin ellas la sincronización no se ejecuta.",
                   icon=":material/tune:")
    mostrar_mensaje_pendiente()


def _render_pago(licit):
    """Reclamos de pago con su procedencia: fuente, interpretación IA o sin datos."""
    fuente, ia = info_pago(licit)
    if fuente:
        st.html(f'<div class="l-pago">{escape(fuente)}</div>')
    if ia:
        st.html(f'<div class="l-nota">Interpretación IA (no verificada): {escape(ia)}</div>')
    if not fuente and not ia:
        st.html('<div class="l-nota">Reclamos de pago: sin datos verificados</div>')


def _reanalizar(base, id_externo):
    """Ejecutar un nuevo análisis real con Gemini; si falla se conserva el anterior."""
    from core.ai_analyst import AIAnalyst, AnalisisFallido, CuotaAgotada
    with st.spinner("Consultando a la IA..."):
        try:
            analisis = AIAnalyst(base).analizar_licitacion(id_externo)
        except (ValueError, AnalisisFallido, CuotaAgotada) as e:
            st.session_state['ultimo_mensaje'] = ("error", f"No se pudo re-analizar {id_externo}; se conserva el análisis anterior. Detalle: {e}")
        else:
            st.session_state['ultimo_mensaje'] = ("success", f"{id_externo} re-analizada: {texto_score(analisis['score_ia'])}")
    st.rerun()


def _form_evaluacion(base, l, prefijo):
    """
    Formulario de evaluación humana del análisis vigente. Las respuestas
    alimentan el gráfico de calibración y el dataset de la V2.
    """
    id_ext = l['id_externo']
    if evaluacion_desactualizada(l):
        st.warning("Tu evaluación corresponde a un análisis anterior: revísala.", icon=":material/history:")
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
        comentario = st.text_input("Comentario (opcional)", value=l.get('eval_comentario') or "", key=f"evc_{prefijo}_{id_ext}")
        if st.form_submit_button("Guardar evaluación", icon=":material/save:", key=f"evb_{prefijo}_{id_ext}"):
            if not eval_score or not postularia:
                st.warning("Responde ambas preguntas para guardar.")
            else:
                base.guardar_evaluacion(id_ext, eval_score, postularia, comentario)
                st.session_state['ultimo_mensaje'] = ("success", f"Evaluación de {id_ext} guardada.")
                st.rerun()


def _detalle_analisis(base, l, an, simplificado=False, prefijo="lista"):
    """Contenido del desplegable: veredicto, puntos críticos, riesgos, pagos, trazabilidad y evaluación."""
    score = score_de(l)
    if an:
        st.html(f'<div class="l-veredicto"><b>Veredicto IA ·</b> {escape(an.get("veredicto") or "Sin veredicto")}</div>')
        if not simplificado:
            c1, c2 = st.columns(2)
            with c1:
                seccion("Puntos críticos")
                st.html(html_lista(an['puntos_criticos'][:3]) if an['puntos_criticos'] else '<div class="l-nota">—</div>')
            with c2:
                seccion("Riesgos")
                st.html(html_lista(an['riesgos'][:3]) if an['riesgos'] else '<div class="l-nota">—</div>')
            if score is not None and score < config.UMBRAL_DESCARTE and es_valor_util(l.get('motivo_archivo')):
                st.html(f'<div class="l-nota">Motivo de descarte sugerido por la IA: {escape(l["motivo_archivo"])}</div>')
    elif l.get('analisis_ia_json'):
        st.warning("El análisis guardado no se pudo leer.")

    seccion("Pagos del organismo")
    _render_pago(l)
    cierre = formatear_fecha(l.get('fecha_cierre'), con_hora=True) or "No disponible"
    publicacion = formatear_fecha(l.get('fecha_publicacion')) or "No disponible"
    st.html(f'<div class="l-dato"><b>Publicación:</b> {publicacion} &nbsp;·&nbsp; <b>Cierre:</b> {cierre}</div>')
    if an:
        st.html(f'<div class="l-nota">{escape(texto_trazabilidad(l))}</div>')

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
                     help="Devolver a Oportunidades"):
            base.cambiar_estado(id_ext, 'analizado'); st.rerun()
    _mas_acciones(base, l, f"ia_{id_ext}")


def _mas_acciones(base, l, clave_reanalizar):
    """Acciones secundarias (portal y re-análisis) agrupadas en un menú."""
    if not l.get('link') and not l.get('descripcion_pro'):
        return
    with st.popover("Más", icon=":material/more_horiz:", width="stretch"):
        if l.get('link'):
            st.link_button("Ver en el portal", l['link'], icon=":material/open_in_new:", width="stretch")
        if l.get('descripcion_pro'):
            if st.button("Re-analizar con IA", icon=":material/refresh:", key=clave_reanalizar, width="stretch",
                         help="Pedir un nuevo análisis a Gemini (si falla se conserva el actual)"):
                _reanalizar(base, l['id_externo'])


def tarjeta(base, l, simplificado=False):
    """Una licitación como tarjeta: cabecera HTML, acciones y desplegable con el análisis."""
    an = cargar_analisis_guardado(l.get('analisis_ia_json'))
    with st.container(border=True, key=f"lcard_{l['id_externo']}"):
        c1, c2 = st.columns([5, 1.25])
        c1.html(html_tarjeta(l, an))
        with c2:
            _acciones(base, l)
        with st.expander("Análisis y evaluación" if not simplificado else "Análisis", icon=":material/insights:"):
            _detalle_analisis(base, l, an, simplificado)


def _filtros(lista, clave, ocultar_cerradas=True):
    """Fila única de filtros sobre la lista; devuelve (filtradas, orden)."""
    regiones = sorted({l['region'] for l in lista if es_valor_util(l.get('region'))})
    c1, c2, c3, c4, c5 = st.columns([2, 1.2, 1.7, 1.9, 1.1], vertical_alignment="bottom")
    texto = c1.text_input("Buscar", placeholder="Título u organismo", key=f"f_txt_{clave}", icon=":material/search:")
    score_min = c2.select_slider("Score mínimo", options=list(range(1, 11)), value=1, key=f"f_score_{clave}")
    sel_regiones = c3.multiselect("Región", regiones, key=f"f_reg_{clave}", placeholder="Todas")
    orden = c4.selectbox("Ordenar por", ORDENES, key=f"f_ord_{clave}")
    ocultar = c5.checkbox("Ocultar cerradas", value=ocultar_cerradas, key=f"f_cer_{clave}")
    filtradas = filtrar_y_ordenar(lista, texto, score_min, sel_regiones, orden, ocultar)
    st.caption(f"{len(filtradas)} de {len(lista)} licitaciones")
    return filtradas, orden


def lista_tarjetas(base, lista, clave, simplificado=False, ocultar_cerradas=True, vacio="No hay licitaciones para mostrar."):
    """Lista filtrable de tarjetas."""
    if not lista:
        st.info(vacio, icon=":material/inbox:")
        return
    filtradas, orden = _filtros(lista, clave, ocultar_cerradas)
    if not filtradas:
        st.info("Ninguna licitación coincide con los filtros.", icon=":material/filter_alt_off:")
        return
    if orden == "Más recientes":
        for etiqueta, grupo in agrupar_por_fecha(filtradas):
            seccion(etiqueta)
            for l in grupo:
                tarjeta(base, l, simplificado)
    else:
        for l in filtradas:
            tarjeta(base, l, simplificado)


# ===================================================================
# PÁGINAS
# ===================================================================

def pagina_oportunidades():
    base = db()
    cabecera(base, "Oportunidades", "Licitaciones analizadas por la IA según tu perfil de negocio.")
    todas = base.obtener_licitaciones()
    m = metricas_resumen(todas)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Oportunidades activas", m["activas"], help="Analizadas y favoritas aún abiertas.", border=True)
    c2.metric("Cierran en ≤ 7 días", m["cierran_7"], border=True)
    c3.metric("Score promedio", f"{m['score_promedio']}".replace(".", ",") if m["score_promedio"] is not None else "—",
              help="Promedio de las oportunidades activas.", border=True)
    c4.metric("Pendientes / errores", m["en_cola"], border=True)
    st.write("")
    lista_tarjetas(base, [l for l in todas if l['estado'] == 'analizado'], "analizadas",
                   vacio="No hay licitaciones analizadas. Pulsa «Sincronizar ahora» para buscar las de hoy.")


def pagina_favoritas():
    base = db()
    cabecera(base, "Favoritas", "Las oportunidades que estás preparando, ordenadas por cierre.")
    favs = filtrar_y_ordenar([l for l in base.obtener_licitaciones() if l['estado'] == 'favorita'], orden="Cierre más próximo")
    if not favs:
        st.info("Aún no tienes favoritas. Márcalas desde Oportunidades.", icon=":material/star:")
        return

    for l in favs:
        an = cargar_analisis_guardado(l.get('analisis_ia_json'))
        with st.container(border=True, key=f"lcard_fav_{l['id_externo']}"):
            c_head, c_acc = st.columns([5, 1.25])
            c_head.html(html_tarjeta(l, an))
            with c_acc:
                if st.button("Quitar", icon=":material/star_half:", key=f"back_{l['id_externo']}", width="stretch",
                             help="Quitar de Favoritas"):
                    base.cambiar_estado(l['id_externo'], 'analizado'); st.rerun()
                _mas_acciones(base, l, f"iaf_{l['id_externo']}")

            c1, c2 = st.columns([1.9, 1], gap="large")
            with c1:
                if an:
                    st.html(f'<div class="l-veredicto"><b>Veredicto IA ·</b> {escape(an.get("veredicto") or "Sin veredicto")}</div>')
                    a, b = st.columns(2)
                    with a:
                        seccion("Puntos clave")
                        st.html(html_lista(an['puntos_criticos']) if an['puntos_criticos'] else '<div class="l-nota">—</div>')
                    with b:
                        seccion("Riesgos")
                        st.html(html_lista(an['riesgos']) if an['riesgos'] else '<div class="l-nota">—</div>')
                else:
                    st.caption("Sin análisis disponible.")
                seccion("Pagos del organismo")
                _render_pago(l)
                cierre = formatear_fecha(l.get('fecha_cierre'), con_hora=True) or "No disponible"
                publicacion = formatear_fecha(l.get('fecha_publicacion')) or "No disponible"
                st.html(f'<div class="l-dato"><b>Publicación:</b> {publicacion} &nbsp;·&nbsp; <b>Cierre:</b> {cierre}</div>')
                if an:
                    st.html(f'<div class="l-nota">{escape(texto_trazabilidad(l))}</div>')
                    with st.expander("Tu evaluación", icon=":material/rate_review:", expanded=evaluacion_desactualizada(l)):
                        _form_evaluacion(base, l, "fav")

            with c2:
                # Gestión operativa persistida en la BD
                seccion("Gestión")
                try:
                    checklist = json.loads(l.get('checklist_json') or '{}')
                except ValueError:
                    checklist = {}
                with st.form(f"notas_{l['id_externo']}", border=False):
                    valores = {clave: st.checkbox(etiqueta, value=bool(checklist.get(clave)), key=f"chk_{clave}_{l['id_externo']}")
                               for clave, etiqueta in CHECKLIST_ITEMS.items()}
                    notas = st.text_area("Notas internas:", value=l.get('notas') or '', placeholder="Ej: Costos revisados...",
                                         key=f"txt_{l['id_externo']}", height=110)
                    if st.form_submit_button("Guardar notas", icon=":material/save:", width="stretch"):
                        base.guardar_notas(l['id_externo'], notas, valores)
                        st.session_state['ultimo_mensaje'] = ("success", f"Notas de {l['id_externo']} guardadas.")
                        st.rerun()


def pagina_archivo():
    base = db()
    cabecera(base, "Archivo", "Licitaciones descartadas. Puedes restaurarlas en cualquier momento.")
    lista_tarjetas(base, [l for l in base.obtener_licitaciones() if l['estado'] == 'archivada'], "archivadas",
                   simplificado=True, ocultar_cerradas=False, vacio="El archivo está vacío.")


def pagina_cola():
    """Licitaciones aún no analizadas (pendientes, extraídas o con error): ninguna queda oculta."""
    base = db()
    cabecera(base, "Cola de procesamiento",
             f"Pendientes y extraídas se procesan solas en las próximas sincronizaciones (hasta {config.MAX_INTENTOS} intentos). "
             "Las que quedan en error requieren «Reintentar».")
    lista = [l for l in base.obtener_licitaciones() if l['estado'] in ESTADOS_COLA]
    if not lista:
        st.info("No hay licitaciones pendientes ni con errores.", icon=":material/task_alt:")
        return
    estados = {
        'pendiente': ("Pendiente de extracción", "hourglass_top", ""),
        'extraido': ("Pendiente de análisis IA", "description", "medio"),
        'error': ("Error: requiere reintento", "error", "bajo"),
    }
    for l in lista:
        texto, icono, nivel = estados.get(l['estado'], (l['estado'], "help", ""))
        with st.container(border=True, key=f"lcard_cola_{l['id_externo']}"):
            c1, c2 = st.columns([5, 1.25], vertical_alignment="center")
            chips = [_chip(texto, icono, nivel), _chip(f"{l.get('intentos') or 0} intentos", "replay"),
                     _chip(etiqueta_cierre(l), "schedule")]
            error = f'<div class="l-nota" style="margin-top:.5rem">Último error: {escape(l["ultimo_error"])}</div>' if l.get('ultimo_error') else ""
            c1.html(f'<p class="l-titulo">{escape(titulo_de(l))}</p>'
                    f'<p class="l-org"><span class="l-id">{escape(l["id_externo"])}</span></p>'
                    f'<div class="l-chips">{"".join(chips)}</div>{error}')
            with c2:
                if l['estado'] == 'error':
                    if st.button("Reintentar", icon=":material/replay:", key=f"retry_{l['id_externo']}", width="stretch"):
                        base.reintentar(l['id_externo']); st.rerun()


def pagina_panorama():
    from web import panorama
    base = db()
    cabecera(base, "Panorama", "Cómo se comporta el radar: filtrado, cierres, riesgo de pago y calidad del score.")
    panorama.render(base)
    st.write("")
    _exportar(base)


def _exportar(base):
    """Descarga de los datos en formatos independientes del esquema SQLite."""
    with st.container(border=True, key="lcard_exportar"):
        seccion("Exportar datos")
        st.caption("Incluye datos de la fuente, análisis de IA (con su trazabilidad) y tus evaluaciones. "
                   "No incluye notas internas ni checklist.")
        exportables = [l for l in base.obtener_licitaciones() if l.get('estado') in ('analizado', 'favorita', 'archivada')]
        incluir_ficha = st.checkbox("Incluir el texto completo de cada ficha (solo JSON; aumenta mucho el tamaño)", key="exp_ficha")
        sello = datetime.now().strftime("%Y%m%d-%H%M")
        c1, c2, _ = st.columns([1, 1, 2])
        c1.download_button("JSON", a_json(exportables, incluir_ficha), file_name=f"licitai-{sello}.json", icon=":material/download:",
                           mime="application/json", on_click="ignore", width="stretch", disabled=not exportables)
        c2.download_button("CSV", a_csv(exportables), file_name=f"licitai-{sello}.csv", icon=":material/download:",
                           mime="text/csv", on_click="ignore", width="stretch", disabled=not exportables)
        st.caption(f"{len(exportables)} licitaciones con análisis.")


def pagina_perfil():
    """Formulario del perfil de negocio."""
    base = db()
    cabecera(base, "Perfil de negocio", "Define qué buscar en el portal y el contexto que recibe la IA.")
    perfil = base.obtener_perfil() or {}
    with st.container(border=True, key="lcard_perfil"):
        with st.form("perfil_form", border=False):
            c1, c2 = st.columns(2)
            with c1:
                keywords_pos = st.text_area("Keywords Positivas", perfil.get('keywords_pos') or '', height=120,
                                            help="Separadas por comas. Basta con que el título contenga una. "
                                                 "No distingue mayúsculas ni tildes.")
            with c2:
                keywords_neg = st.text_area("Keywords Negativas", perfil.get('keywords_neg') or '', height=120,
                                            help="Separadas por comas. Si el título contiene alguna, la licitación se descarta.")
            bio = st.text_area("Bio Estratégica (Contexto IA)", perfil.get('bio_estrategica') or '', height=160,
                               help="Qué vende tu empresa y qué oportunidades te interesan. Se entrega a la IA en cada análisis.")
            if st.form_submit_button("Guardar Cambios", icon=":material/save:", type="primary"):
                # regiones: reservado, sin uso en el filtrado
                base.guardar_perfil(keywords_pos, keywords_neg, perfil.get('regiones'), bio)
                st.session_state['ultimo_mensaje'] = ("success", "Perfil actualizado")
                st.rerun()
