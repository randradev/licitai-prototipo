# -*- coding: utf-8 -*-
"""
Módulo: Interfaz de Usuario (punto de entrada)
---------------------------------------------
Dashboard Streamlit de LicitAI con navegación superior. Este archivo solo
configura la página, los estilos y la navegación; cada sección vive en
web/paginas/*.py y su contenido en web/vistas.py.

Ejecutar desde la raíz del proyecto:
    python -m streamlit run web/app.py
"""

import os
import sys

# Permitir `streamlit run web/app.py` desde cualquier directorio
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import streamlit as st
from core import config
from web.estilos import css

# Configuración global de la página y metadatos del navegador
st.set_page_config(page_title="LicitAI", page_icon=":material/radar:", layout="wide")
config.configurar_logging()

# Estilos (tema único "editorial claro"; ver .streamlit/config.toml)
st.html(css())
st.logo(os.path.join(RAIZ, "web", "assets", "logo-light.svg"), size="large")

PAGINAS = os.path.join(RAIZ, "web", "paginas")
navegacion = st.navigation([
    st.Page(os.path.join(PAGINAS, "oportunidades.py"), title="Oportunidades", icon=":material/target:", default=True),
    st.Page(os.path.join(PAGINAS, "favoritas.py"), title="Favoritas", icon=":material/star:"),
    st.Page(os.path.join(PAGINAS, "archivo.py"), title="Archivo", icon=":material/archive:"),
    st.Page(os.path.join(PAGINAS, "cola.py"), title="En proceso", icon=":material/pending_actions:"),
    st.Page(os.path.join(PAGINAS, "panorama.py"), title="Panorama", icon=":material/monitoring:"),
    st.Page(os.path.join(PAGINAS, "perfil.py"), title="Perfil", icon=":material/tune:"),
], position="top")
navegacion.run()

st.html('<div class="l-pie"><span>LicitAI · prototipo</span>'
        '<span>Los análisis son generados por IA y pueden contener errores. Verifica siempre en Mercado Público.</span></div>')
