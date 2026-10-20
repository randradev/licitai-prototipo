# -*- coding: utf-8 -*-
"""
Módulo: Interfaz de Usuario (LicitAIWeb)
---------------------------------------
Implementa el dashboard interactivo utilizando Streamlit.
Este módulo actúa como la capa de presentación, permitiendo al usuario:
1. Configurar su perfil de negocio y criterios de búsqueda.
2. Visualizar, filtrar, gestionar y evaluar licitaciones analizadas por la IA.
3. Orquestar manualmente la sincronización con Mercado Público.
4. Ver el panorama agregado y exportar los datos.
"""

import os
import sys

# Permitir `streamlit run web/app.py` desde cualquier directorio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
from datetime import datetime

import streamlit as st
from core import config
from core.database_mgr import DatabaseManager
from core.exportar import a_csv, a_json
from core.parsing import (cargar_analisis_guardado, dias_para_cierre, es_valor_util, fecha_iso, formatear_fecha,
                          normalizar_keywords, normalizar_texto, parsear_fecha_hora)
from web import panorama

# Configuración global de la página y metadatos del navegador
st.set_page_config(
    page_title="LicitAI - Dashboard",
    page_icon="🤖",
    layout="wide"
)

config.configurar_logging()
log = logging.getLogger("licitai.web")

# Ítems del checklist de gestión (clave persistida -> etiqueta)
CHECKLIST_ITEMS = {"bases_leidas": "Bases leídas", "anexos_preparados": "Anexos preparados"}

# Evaluación humana del análisis (clave persistida -> etiqueta)
EVAL_SCORE_LABELS = {"acertado": "Acertado", "muy_alto": "Muy alto", "muy_bajo": "Muy bajo"}
POSTULARIA_LABELS = {"si": "Sí", "tal_vez": "Tal vez", "no": "No"}

ORDENES = ("Cierre más próximo", "Mayor score", "Más recientes")


# ===================================================================
# HELPERS DE PRESENTACIÓN (puros, sin Streamlit)
# ===================================================================

def score_de(licit):
    """Devolver el score como entero, o None si no existe o no es válido."""
    try:
        return int(licit.get('score_ia'))
    except (TypeError, ValueError):
        return None


def color_score(score):
    """Indicador visual según los umbrales únicos de core/config.py."""
    if score is None:
        return "⚪"
    return "🟢" if score >= config.UMBRAL_ALTO else "🟡" if score >= config.UMBRAL_MEDIO else "🔴"


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
        return "cierre sin informar"
    if dias < 0:
        return "cerrada"
    if dias == 0:
        return "⏰ cierra hoy"
    if dias == 1:
        return "⏰ cierra mañana"
    return f"{'⏰ ' if dias <= 7 else ''}cierra en {dias} días"


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
        "en_cola": sum(1 for l in licitaciones if l.get('estado') in ('pendiente', 'extraido', 'error')),
    }


class LicitAIWeb:
    """
    Clase principal para la gestión y renderizado de la interfaz web.

    Encapsula la lógica de visualización y los componentes de interacción
    con el usuario final.
    """

    def __init__(self):
        """
        Inicializar la conexión con la persistencia de datos.
        """
        self.db = DatabaseManager()

    def _render_pago_badge(self, licit):
        """
        Mostrar los reclamos de pago del organismo indicando su procedencia:
        dato de la fuente, interpretación de la IA o ausencia de datos.
        """
        fuente, ia = info_pago(licit)
        if fuente:
            st.info(f"💳 {fuente}")
        if ia:
            st.caption(f"🤖 Interpretación IA (no verificada): {ia}")
        if not fuente and not ia:
            st.caption("💳 Reclamos de pago: Sin datos verificados")

    def _mostrar_mensaje_pendiente(self):
        """Mostrar (una vez) el resultado de la última acción, sobreviviendo al rerun."""
        mensaje = st.session_state.pop('ultimo_mensaje', None)
        if mensaje:
            nivel, texto = mensaje
            getattr(st, nivel, st.info)(texto)

    def _reanalizar(self, id_externo):
        """Ejecutar un nuevo análisis real con Gemini; si falla se conserva el anterior."""
        from core.ai_analyst import AIAnalyst, AnalisisFallido, CuotaAgotada
        with st.spinner("Consultando a la IA..."):
            try:
                analisis = AIAnalyst(self.db).analizar_licitacion(id_externo)
            except (ValueError, AnalisisFallido, CuotaAgotada) as e:
                st.session_state['ultimo_mensaje'] = ("error", f"No se pudo re-analizar {id_externo}; se conserva el análisis anterior. Detalle: {e}")
            else:
                st.session_state['ultimo_mensaje'] = ("success", f"{id_externo} re-analizada: {texto_score(analisis['score_ia'])}")
        st.rerun()

    def _form_evaluacion(self, l, prefijo):
        """
        Formulario de evaluación humana del análisis vigente. Las respuestas
        alimentan el gráfico de calibración y el dataset de la V2.
        """
        id_ext = l['id_externo']
        if evaluacion_desactualizada(l):
            st.warning("Tu evaluación corresponde a un análisis anterior: revísala.")
        with st.form(f"eval_{prefijo}_{id_ext}"):
            opciones_score = list(EVAL_SCORE_LABELS)
            opciones_post = list(POSTULARIA_LABELS)
            eval_score = st.radio("¿El score de la IA es acertado?", opciones_score, format_func=EVAL_SCORE_LABELS.get,
                                  index=opciones_score.index(l['eval_score']) if l.get('eval_score') in opciones_score else None,
                                  horizontal=True, key=f"evs_{prefijo}_{id_ext}")
            postularia = st.radio("¿Postularías?", opciones_post, format_func=POSTULARIA_LABELS.get,
                                  index=opciones_post.index(l['eval_postularia']) if l.get('eval_postularia') in opciones_post else None,
                                  horizontal=True, key=f"evp_{prefijo}_{id_ext}")
            comentario = st.text_input("Comentario (opcional)", value=l.get('eval_comentario') or "", key=f"evc_{prefijo}_{id_ext}")
            if st.form_submit_button("💾 Guardar evaluación", key=f"evb_{prefijo}_{id_ext}"):
                if not eval_score or not postularia:
                    st.warning("Responde ambas preguntas para guardar.")
                else:
                    self.db.guardar_evaluacion(id_ext, eval_score, postularia, comentario)
                    st.session_state['ultimo_mensaje'] = ("success", f"Evaluación de {id_ext} guardada.")
                    st.rerun()

    def render_sidebar(self):
        """
        Renderizar la barra lateral con la sincronización y su estado.
        """
        st.sidebar.title("⚙️ Panel de Control")

        # --- SECCIÓN: SINCRONIZACIÓN ---
        st.sidebar.subheader("🔄 Sincronización")
        st.sidebar.caption(
            f"Consulta las licitaciones publicadas hoy y procesa hasta {config.MAX_PROCESAR} "
            "de la cola (incluidas pendientes anteriores). Puede tardar varios minutos; "
            "lo que hagas en la página mientras tanto se aplica al terminar."
        )
        if st.sidebar.button("🚀 Buscar y Analizar Hoy", width="stretch"):
            with st.sidebar.status("Ejecutando proceso...", expanded=True) as status:
                try:
                    # Importación diferida para evitar dependencias circulares
                    from main import ejecutar_pipeline, describir_resumen
                    resumen = ejecutar_pipeline(db=self.db)
                    nivel, mensaje = describir_resumen(resumen)
                    status.update(label="Proceso finalizado", state="error" if nivel == "error" else "complete")
                except Exception as e:
                    log.exception("Error inesperado en la sincronización")
                    nivel, mensaje = "error", f"Error inesperado en el proceso: {type(e).__name__}: {e}"
                    status.update(label="Error en el proceso", state="error")
            st.session_state['ultimo_mensaje'] = (nivel, mensaje)
            st.rerun()

        ejecuciones = self.db.obtener_ejecuciones()
        if ejecuciones:
            ultima = ejecuciones[0]
            st.sidebar.caption(f"Última sincronización: {formatear_fecha(ultima['inicio'], con_hora=True)} — "
                               f"{ultima['analizadas']} analizadas de {ultima['total_listado']} en el listado.")

        perfil = self.db.obtener_perfil() or {}
        if not normalizar_keywords(perfil.get('keywords_pos')):
            st.sidebar.warning("Configura al menos una keyword positiva en la pestaña ⚙️ Perfil: sin ellas la sincronización no se ejecuta.")

    def render_metricas(self, todas):
        """Fila de indicadores de la cabecera."""
        m = metricas_resumen(todas)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Oportunidades activas", m["activas"], help="Analizadas y favoritas aún abiertas.", border=True)
        c2.metric("Cierran en ≤ 7 días", m["cierran_7"], border=True)
        c3.metric("Score promedio (activas)", f"{m['score_promedio']}".replace(".", ",") if m["score_promedio"] is not None else "—", border=True)
        c4.metric("Pendientes / errores", m["en_cola"], border=True)

    def render_perfil(self):
        """Formulario del perfil de negocio (pestaña propia: se edita con poca frecuencia)."""
        perfil = self.db.obtener_perfil() or {}
        st.caption("Las keywords se buscan en el título del listado sin distinguir mayúsculas ni tildes. "
                   "La bio se entrega a la IA como contexto del negocio.")
        with st.form("perfil_form"):
            c1, c2 = st.columns(2)
            with c1:
                keywords_pos = st.text_area("Keywords Positivas", perfil.get('keywords_pos') or '', height=120,
                                            help="Separadas por comas. Basta con que el título contenga una.")
            with c2:
                keywords_neg = st.text_area("Keywords Negativas", perfil.get('keywords_neg') or '', height=120,
                                            help="Separadas por comas. Si el título contiene alguna, la licitación se descarta.")
            bio = st.text_area("Bio Estratégica (Contexto IA)", perfil.get('bio_estrategica') or '', height=160)

            if st.form_submit_button("Guardar Cambios"):
                # Actualizar el modelo de datos con la nueva configuración (regiones: reservado, sin uso)
                self.db.guardar_perfil(keywords_pos, keywords_neg, perfil.get('regiones'), bio)
                st.session_state['ultimo_mensaje'] = ("success", "✅ Perfil actualizado")
                st.rerun()

    def _filtros(self, lista, clave, ocultar_cerradas=True):
        """Fila única de filtros sobre la lista; devuelve (filtradas, orden)."""
        regiones = sorted({l['region'] for l in lista if es_valor_util(l.get('region'))})
        c1, c2, c3, c4, c5 = st.columns([2, 1.2, 1.7, 1.9, 1.1], vertical_alignment="bottom")
        texto = c1.text_input("Buscar", placeholder="Título u organismo", key=f"f_txt_{clave}")
        score_min = c2.select_slider("Score mínimo", options=list(range(1, 11)), value=1, key=f"f_score_{clave}")
        sel_regiones = c3.multiselect("Región", regiones, key=f"f_reg_{clave}", placeholder="Todas")
        orden = c4.selectbox("Ordenar por", ORDENES, key=f"f_ord_{clave}")
        ocultar = c5.checkbox("Ocultar cerradas", value=ocultar_cerradas, key=f"f_cer_{clave}")
        filtradas = filtrar_y_ordenar(lista, texto, score_min, sel_regiones, orden, ocultar)
        if len(filtradas) != len(lista):
            st.caption(f"Mostrando {len(filtradas)} de {len(lista)}.")
        return filtradas, orden

    def _dibujar_item(self, l, simplificado):
        """Una licitación como fila expandible."""
        score = score_de(l)
        an = cargar_analisis_guardado(l.get('analisis_ia_json'))
        titulo_display_text = titulo_de(l, an)

        # Truncar título para mantener la UI limpia
        titulo_header = (titulo_display_text[:80] + '...') if len(titulo_display_text) > 80 else titulo_display_text

        with st.expander(f"{color_score(score)} {texto_score(score)} · {titulo_header} · {etiqueta_cierre(l)}"):
            c1, c2 = st.columns([2.5, 1])
            with c1:
                st.write(f"**🏢 {organismo_de(l)}**")

                self._render_pago_badge(l)
                cierre = formatear_fecha(l.get('fecha_cierre'), con_hora=True) or "No disponible"
                publicacion = formatear_fecha(l.get('fecha_publicacion')) or "No disponible"
                region = f" | **Región:** {l['region']}" if es_valor_util(l.get('region')) else ""
                st.caption(f"🕒 **Cierre:** {cierre} ({etiqueta_cierre(l)}) | **Publicación:** {publicacion} | **ID:** {l['id_externo']}{region}")

                # Mostrar el análisis semántico si existe
                if an:
                    st.info(f"**🧠 Veredicto (IA):** {an.get('veredicto') or 'Sin veredicto'}")
                    if not simplificado:
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.markdown("**✅ Puntos críticos:**")
                            for p in an['puntos_criticos'][:3]: st.caption(f"• {p}")
                        with col_b:
                            st.markdown("**⚠️ Riesgos:**")
                            for r in an['riesgos'][:3]: st.caption(f"• {r}")
                        if score is not None and score < config.UMBRAL_DESCARTE and es_valor_util(l.get('motivo_archivo')):
                            st.caption(f"📂 Motivo de descarte sugerido por la IA: {l['motivo_archivo']}")
                    st.caption(f"🔎 {texto_trazabilidad(l)}")
                elif l.get('analisis_ia_json'):
                    st.warning("El análisis guardado no se pudo leer.")

                if l.get('link'):
                    st.link_button("🌐 Ver en Mercado Público", l['link'])

            with c2:
                st.metric("Match IA", texto_score(score))
                # Controles de estado de la licitación
                if l['estado'] == 'analizado':
                    if st.button("⭐ Favorita", key=f"fav_{l['id_externo']}", width="stretch"):
                        self.db.cambiar_estado(l['id_externo'], 'favorita'); st.rerun()
                    if st.button("📁 Archivar", key=f"arc_{l['id_externo']}", width="stretch"):
                        self.db.cambiar_estado(l['id_externo'], 'archivada'); st.rerun()
                else:
                    if st.button("↩️ Restaurar a Analizadas", key=f"re_{l['id_externo']}", width="stretch"):
                        self.db.cambiar_estado(l['id_externo'], 'analizado'); st.rerun()
                if l.get('descripcion_pro'):
                    if st.button("🧠 Re-analizar con IA", key=f"ia_{l['id_externo']}", width="stretch"):
                        self._reanalizar(l['id_externo'])

            if an and not simplificado:
                st.markdown("**📝 Tu evaluación**")
                self._form_evaluacion(l, "lista")

    def dibujar_lista_licitaciones(self, lista, simplificado=False, clave="lista", ocultar_cerradas=True):
        """
        Renderizar la lista de licitaciones con filtros.

        Args:
            lista (list): Colección de licitaciones a visualizar.
            simplificado (bool): Si es True, omite detalles extensos de IA (útil para archivos).
            clave (str): Prefijo de los widgets de filtro (uno por pestaña).
        """
        if not lista:
            st.info("No hay licitaciones para mostrar.")
            return

        filtradas, orden = self._filtros(lista, clave, ocultar_cerradas)
        if not filtradas:
            st.info("Ninguna licitación coincide con los filtros.")
            return

        if orden == "Más recientes":
            # Agrupación cronológica por fecha de publicación (más recientes primero)
            for etiqueta, grupo in agrupar_por_fecha(filtradas):
                st.markdown(f"#### 📅 {etiqueta}")
                for l in grupo:
                    self._dibujar_item(l, simplificado)
                st.divider()
        else:
            for l in filtradas:
                self._dibujar_item(l, simplificado)

    def dibujar_favoritas_detallado(self, lista):
        """
        Renderizar la vista extendida para licitaciones marcadas como favoritas.
        Ordena por cierre más próximo y luego por score.
        """
        lista_ordenada = filtrar_y_ordenar(lista, orden="Cierre más próximo")

        for l in lista_ordenada:
            score = score_de(l)
            an = cargar_analisis_guardado(l.get('analisis_ia_json'))
            titulo = titulo_de(l, an)

            with st.container(border=True):
                c_head1, c_head2 = st.columns([3, 1])
                with c_head1:
                    st.markdown(f"#### 🌟 {titulo}")
                    st.caption(f"{organismo_de(l)} · {etiqueta_cierre(l)}")
                with c_head2:
                    st.metric("Puntaje Estratégico", texto_score(score))

                c1, c2, c3 = st.columns([1.2, 1.8, 1])

                with c1:
                    st.markdown("##### 📋 Ficha Técnica")
                    st.write(f"**Organismo:**\n{organismo_de(l)}")
                    self._render_pago_badge(l)
                    st.write(f"**Publicación:** {formatear_fecha(l.get('fecha_publicacion')) or 'No disponible'}")
                    st.write(f"**Cierre:** {formatear_fecha(l.get('fecha_cierre'), con_hora=True) or 'No disponible'}")
                    if l.get('link'):
                        st.link_button("🚀 Abrir en Portal", l['link'], width="stretch")
                    if st.button("⬅️ Quitar de Favoritas", key=f"back_{l['id_externo']}", width="stretch"):
                        self.db.cambiar_estado(l['id_externo'], 'analizado'); st.rerun()
                    if l.get('descripcion_pro'):
                        if st.button("🧠 Re-analizar con IA", key=f"iaf_{l['id_externo']}", width="stretch"):
                            self._reanalizar(l['id_externo'])

                with c2:
                    st.markdown("##### 🧠 Análisis de la IA")
                    if an:
                        st.success(f"**Veredicto:** {an.get('veredicto') or 'Sin veredicto'}")
                        st.markdown("**Puntos Clave:**")
                        for p in an['puntos_criticos']: st.write(f"🔹 {p}")
                        with st.expander("Ver Riesgos Detectados"):
                            for r in an['riesgos']: st.write(f"🔸 {r}")
                        st.caption(f"🔎 {texto_trazabilidad(l)}")
                        with st.expander("📝 Tu evaluación", expanded=evaluacion_desactualizada(l)):
                            self._form_evaluacion(l, "fav")
                    else:
                        st.caption("Sin análisis disponible.")

                with c3:
                    # Gestión operativa persistida en la BD
                    st.markdown("##### 📝 Gestión")
                    try:
                        checklist = json.loads(l.get('checklist_json') or '{}')
                    except ValueError:
                        checklist = {}
                    with st.form(f"notas_{l['id_externo']}"):
                        valores = {clave: st.checkbox(etiqueta, value=bool(checklist.get(clave)), key=f"chk_{clave}_{l['id_externo']}")
                                   for clave, etiqueta in CHECKLIST_ITEMS.items()}
                        notas = st.text_area("Notas internas:", value=l.get('notas') or '', placeholder="Ej: Costos revisados...", key=f"txt_{l['id_externo']}")
                        if st.form_submit_button("💾 Guardar notas", width="stretch"):
                            self.db.guardar_notas(l['id_externo'], notas, valores)
                            st.session_state['ultimo_mensaje'] = ("success", f"Notas de {l['id_externo']} guardadas.")
                            st.rerun()

    def dibujar_cola(self, lista):
        """
        Mostrar las licitaciones aún no analizadas (pendientes, extraídas o con error)
        para que ningún registro quede oculto.
        """
        if not lista:
            st.info("No hay licitaciones pendientes ni con errores.")
            return
        descripcion_estado = {
            'pendiente': "⏳ Pendiente de extracción",
            'extraido': "📄 Extraída, pendiente de análisis IA",
            'error': "❌ Error (sin reintentos automáticos)",
        }
        st.caption(f"Las pendientes y extraídas se procesan automáticamente en las próximas sincronizaciones "
                   f"(hasta {config.MAX_INTENTOS} intentos). Las que están en error requieren 'Reintentar'.")
        for l in lista:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.write(f"**{titulo_de(l)}** — `{l['id_externo']}`")
                    cierre = formatear_fecha(l.get('fecha_cierre'), con_hora=True) or "No disponible"
                    st.caption(f"{descripcion_estado.get(l['estado'], l['estado'])} | Intentos: {l.get('intentos') or 0} | Cierre: {cierre}")
                    if l.get('ultimo_error'):
                        st.caption(f"Último error: {l['ultimo_error']}")
                with c2:
                    if l['estado'] == 'error':
                        if st.button("🔁 Reintentar", key=f"retry_{l['id_externo']}", width="stretch"):
                            self.db.reintentar(l['id_externo']); st.rerun()

    def render_exportar(self, todas):
        """Descarga de los datos en formatos independientes del esquema SQLite."""
        st.markdown("#### ⬇️ Exportar datos")
        st.caption("Incluye datos de la fuente, análisis de IA (con su trazabilidad) y tus evaluaciones. "
                   "No incluye notas internas ni checklist.")
        exportables = [l for l in todas if l.get('estado') in ('analizado', 'favorita', 'archivada')]
        incluir_ficha = st.checkbox("Incluir el texto completo de cada ficha (solo JSON; aumenta mucho el tamaño)", key="exp_ficha")
        sello = datetime.now().strftime("%Y%m%d-%H%M")
        c1, c2 = st.columns(2)
        c1.download_button("Descargar JSON", a_json(exportables, incluir_ficha), file_name=f"licitai-{sello}.json",
                           mime="application/json", on_click="ignore", width="stretch", disabled=not exportables)
        c2.download_button("Descargar CSV", a_csv(exportables), file_name=f"licitai-{sello}.csv",
                           mime="text/csv", on_click="ignore", width="stretch", disabled=not exportables)
        st.caption(f"{len(exportables)} licitaciones con análisis.")

    def run(self):
        """
        Punto de entrada principal para renderizar la aplicación.
        """
        self.render_sidebar()
        st.title("🤖 LicitAI: Radar Inteligente")
        st.caption("Prototipo. Scores, veredictos e interpretaciones son generados por IA y deben verificarse en el portal.")
        self._mostrar_mensaje_pendiente()

        todas = self.db.obtener_licitaciones()
        self.render_metricas(todas)
        cola = [l for l in todas if l['estado'] in ('pendiente', 'extraido', 'error')]

        # Organización de la vista por pestañas de estado
        tabs = st.tabs(["🎯 Analizadas", "🌟 Favoritas", "📁 Archivadas", f"⏳ Pendientes / Errores ({len(cola)})",
                        "📊 Panorama", "⚙️ Perfil"])

        with tabs[0]:
            licitaciones = [l for l in todas if l['estado'] == 'analizado']
            if not licitaciones:
                st.info("No hay licitaciones analizadas.")
            else:
                self.dibujar_lista_licitaciones(licitaciones, clave="analizadas")

        with tabs[1]:
            favs = [l for l in todas if l['estado'] == 'favorita']
            if not favs:
                st.info("No tienes favoritas seleccionadas aún.")
            else:
                self.dibujar_favoritas_detallado(favs)

        with tabs[2]:
            archived = [l for l in todas if l['estado'] == 'archivada']
            if not archived:
                st.info("El historial de archivadas está vacío.")
            else:
                self.dibujar_lista_licitaciones(archived, simplificado=True, clave="archivadas", ocultar_cerradas=False)

        with tabs[3]:
            self.dibujar_cola(cola)

        with tabs[4]:
            panorama.render(self.db)
            st.divider()
            self.render_exportar(todas)

        with tabs[5]:
            self.render_perfil()

# --- INVOCACIÓN DEL PUNTO DE ENTRADA ---
if __name__ == "__main__":
    app = LicitAIWeb()
    app.run()
