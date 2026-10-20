# -*- coding: utf-8 -*-
"""
Módulo: Interfaz de Usuario (LicitAIWeb)
---------------------------------------
Implementa el dashboard interactivo utilizando Streamlit.
Este módulo actúa como la capa de presentación, permitiendo al usuario:
1. Configurar su perfil de negocio y criterios de búsqueda.
2. Visualizar y gestionar licitaciones analizadas por la IA.
3. Orquestar manualmente la sincronización con Mercado Público.
"""

import os
import sys

# Permitir `streamlit run web/app.py` desde cualquier directorio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import streamlit as st
from core import config
from core.database_mgr import DatabaseManager
from core.parsing import cargar_analisis_guardado, es_valor_util, formatear_fecha, normalizar_keywords

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


def agrupar_por_fecha(lista):
    """
    Agrupar por fecha de publicación (ISO) en orden cronológico descendente;
    las licitaciones sin fecha válida quedan en un grupo final.

    Returns:
        list: [(etiqueta, [licitaciones]), ...]
    """
    grupos, sin_fecha = {}, []
    for l in lista:
        fecha = formatear_fecha(l.get('fecha_publicacion'))
        if fecha:
            grupos.setdefault(l['fecha_publicacion'][:10], []).append(l)
        else:
            sin_fecha.append(l)
    resultado = [(f"Publicadas el {formatear_fecha(k)}", grupos[k]) for k in sorted(grupos, reverse=True)]
    if sin_fecha:
        resultado.append(("Fecha de publicación no disponible", sin_fecha))
    return resultado


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

    def render_sidebar(self):
        """
        Renderizar la barra lateral con controles de sistema y perfil de negocio.
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

        st.sidebar.markdown("---")

        # --- SECCIÓN: PERFIL DE NEGOCIO ---
        # Recuperar configuración actual para pre-poblar el formulario
        perfil = self.db.obtener_perfil() or {}
        st.sidebar.subheader("🏢 Perfil de Negocio")
        if not normalizar_keywords(perfil.get('keywords_pos')):
            st.sidebar.warning("Configura al menos una keyword positiva: sin ellas la sincronización no se ejecuta.")
        with st.sidebar.form("perfil_form"):
            keywords_pos = st.text_area("Keywords Positivas", perfil.get('keywords_pos') or '',
                                        help="Separadas por comas. Se buscan en el título sin distinguir mayúsculas ni tildes.")
            keywords_neg = st.text_area("Keywords Negativas", perfil.get('keywords_neg') or '',
                                        help="Separadas por comas. Si el título contiene alguna, la licitación se descarta.")
            bio = st.text_area("Bio Estratégica (Contexto IA)", perfil.get('bio_estrategica') or '', height=150)

            if st.form_submit_button("Guardar Cambios"):
                # Actualizar el modelo de datos con la nueva configuración (regiones: reservado, sin uso)
                self.db.guardar_perfil(keywords_pos, keywords_neg, perfil.get('regiones'), bio)
                st.session_state['ultimo_mensaje'] = ("success", "✅ Perfil actualizado")
                st.rerun()

    def dibujar_lista_licitaciones(self, lista, simplificado=False):
        """
        Renderizar la lista de licitaciones agrupadas cronológicamente.

        Args:
            lista (list): Colección de licitaciones a visualizar.
            simplificado (bool): Si es True, omite detalles extensos de IA (útil para archivos).
        """
        if not lista:
            st.info("No hay licitaciones para mostrar.")
            return

        # Renderizar grupos en orden cronológico descendente (más recientes primero)
        for etiqueta, grupo in agrupar_por_fecha(lista):
            st.markdown(f"#### 📅 {etiqueta}")

            for l in grupo:
                score = score_de(l)
                an = cargar_analisis_guardado(l.get('analisis_ia_json'))
                titulo_display_text = titulo_de(l, an)

                # Truncar título para mantener la UI limpia
                titulo_header = (titulo_display_text[:85] + '...') if len(titulo_display_text) > 85 else titulo_display_text

                with st.expander(f"{color_score(score)} {texto_score(score)} - {titulo_header}"):
                    c1, c2 = st.columns([2.5, 1])
                    with c1:
                        st.write(f"**🏢 {organismo_de(l)}**")

                        self._render_pago_badge(l)
                        cierre = formatear_fecha(l.get('fecha_cierre'), con_hora=True) or "No disponible"
                        region = f" | **Región:** {l['region']}" if es_valor_util(l.get('region')) else ""
                        st.caption(f"🕒 **Cierre:** {cierre} | **ID:** {l['id_externo']}{region}")

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
            st.divider()

    def dibujar_favoritas_detallado(self, lista):
        """
        Renderizar la vista extendida para licitaciones marcadas como favoritas.
        Ordena por puntaje estratégico de IA.
        """
        lista_ordenada = sorted(lista, key=lambda x: score_de(x) or 0, reverse=True)

        for l in lista_ordenada:
            score = score_de(l)
            an = cargar_analisis_guardado(l.get('analisis_ia_json'))
            titulo = titulo_de(l, an)

            with st.container(border=True):
                c_head1, c_head2 = st.columns([3, 1])
                with c_head1:
                    st.subheader(f"🌟 {titulo}")
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

    def run(self):
        """
        Punto de entrada principal para renderizar la aplicación.
        """
        self.render_sidebar()
        st.title("🤖 LicitAI: Radar Inteligente")
        st.caption("Prototipo. Scores, veredictos e interpretaciones son generados por IA y deben verificarse en el portal.")
        self._mostrar_mensaje_pendiente()

        cola = self.db.obtener_licitaciones(estado=('pendiente', 'extraido', 'error'))

        # Organización de la vista por pestañas de estado
        tab1, tab2, tab3, tab4 = st.tabs(["🎯 Analizadas", "🌟 Favoritas", "📁 Archivadas", f"⏳ Pendientes / Errores ({len(cola)})"])

        with tab1:
            licitaciones = self.db.obtener_licitaciones(estado='analizado')
            if not licitaciones:
                st.info("No hay licitaciones analizadas.")
            else:
                self.dibujar_lista_licitaciones(licitaciones)

        with tab2:
            favs = self.db.obtener_licitaciones(estado='favorita')
            if not favs:
                st.info("No tienes favoritas seleccionadas aún.")
            else:
                self.dibujar_favoritas_detallado(favs)

        with tab3:
            archived = self.db.obtener_licitaciones(estado='archivada')
            if not archived:
                st.info("El historial de archivadas está vacío.")
            else:
                self.dibujar_lista_licitaciones(archived, simplificado=True)

        with tab4:
            self.dibujar_cola(cola)

# --- INVOCACIÓN DEL PUNTO DE ENTRADA ---
if __name__ == "__main__":
    app = LicitAIWeb()
    app.run()
