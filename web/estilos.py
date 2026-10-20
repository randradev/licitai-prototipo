# -*- coding: utf-8 -*-
"""
Módulo: Estilos (estilos)
------------------------
CSS de la interfaz. Los colores base (fondo, texto, primario) vienen del tema
de Streamlit (.streamlit/config.toml); aquí solo se definen las superficies de
tarjeta, insignias y chips, con un juego de tokens por tema.

Los selectores `data-testid` dependen de la versión de Streamlit fijada en
requirements.txt: revisar este archivo si se actualiza Streamlit.
"""

# Tokens por tema. Estados (alto/medio/bajo) = paleta de estado de la guía de
# visualización, siempre acompañados del número o texto (nunca solo color).
TOKENS = {
    "light": {
        "superficie": "#fcfcfb", "plano": "#f6f6f3", "borde": "#e1e0d9", "texto": "#1a1a19",
        "texto2": "#52514e", "muted": "#898781", "chip": "#efeee9", "primario": "#2a78d6",
        "primario_suave": "rgba(42,120,214,.10)",
        "alto_bg": "rgba(12,163,12,.12)", "alto_tx": "#006300",
        "medio_bg": "rgba(250,178,25,.20)", "medio_tx": "#7a5200",
        "bajo_bg": "rgba(208,59,59,.12)", "bajo_tx": "#a12a2a",
        "sombra": "0 1px 2px rgba(11,11,11,.04), 0 1px 1px rgba(11,11,11,.03)",
    },
    "dark": {
        "superficie": "#1a1a19", "plano": "#0f0f0e", "borde": "#2c2c2a", "texto": "#f0efec",
        "texto2": "#c3c2b7", "muted": "#898781", "chip": "#262624", "primario": "#3987e5",
        "primario_suave": "rgba(57,135,229,.16)",
        "alto_bg": "rgba(12,163,12,.18)", "alto_tx": "#4cc94c",
        "medio_bg": "rgba(250,178,25,.16)", "medio_tx": "#fab219",
        "bajo_bg": "rgba(208,59,59,.20)", "bajo_tx": "#ef8a8a",
        "sombra": "none",
    },
}


def css(tema="light"):
    """Hoja de estilos completa para el tema indicado ('light' | 'dark')."""
    t = TOKENS.get(tema, TOKENS["light"])
    variables = ";".join(f"--l-{k.replace('_', '-')}: {v}" for k, v in t.items())
    return f"""
<style>
:root {{ {variables}; }}

/* --- Lienzo: ancho máximo centrado y menos aire superior --- */
.block-container {{ max-width: 1200px; padding-top: 4.2rem; padding-bottom: 4rem; }}
[data-testid="stDecoration"], footer {{ display: none !important; }}

/* --- Superficies: tarjetas y métricas sobre el plano de la página ---
   Las tarjetas son st.container(border=True) con key "lcard_*" (Streamlit la expone como clase st-key-*) */
[class*="st-key-lcard"] {{ background: var(--l-superficie); box-shadow: var(--l-sombra); }}
[data-testid="stMetric"] {{ background: var(--l-superficie); box-shadow: var(--l-sombra); }}
[data-testid="stMetricLabel"] p {{ color: var(--l-texto2); font-size: .82rem; font-weight: 500; }}
[data-testid="stMetricValue"] {{ font-weight: 650; }}
[data-testid="stExpander"] details {{ background: transparent; }}
[data-testid="stExpander"] summary p {{ font-weight: 500; color: var(--l-texto2); }}

/* --- Cabecera de página --- */
.l-cabecera h1 {{ font-size: 1.75rem; margin: 0; padding: 0; line-height: 1.2; }}
.l-cabecera p {{ color: var(--l-texto2); margin: .25rem 0 0 0; font-size: .92rem; }}
.l-seccion {{ font-size: .78rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
             color: var(--l-muted); margin: .2rem 0 .4rem 0; }}

/* --- Tarjeta de licitación --- */
.l-tarjeta {{ display: flex; gap: 1rem; align-items: flex-start; }}
.l-score {{ flex: 0 0 auto; width: 3.4rem; height: 3.4rem; border-radius: .7rem; display: flex;
           flex-direction: column; align-items: center; justify-content: center; line-height: 1; }}
.l-score b {{ font-size: 1.35rem; font-weight: 700; }}
.l-score span {{ font-size: .62rem; font-weight: 600; letter-spacing: .04em; margin-top: .2rem; text-transform: uppercase; }}
.l-alto {{ background: var(--l-alto-bg); color: var(--l-alto-tx); }}
.l-medio {{ background: var(--l-medio-bg); color: var(--l-medio-tx); }}
.l-bajo {{ background: var(--l-bajo-bg); color: var(--l-bajo-tx); }}
.l-nulo {{ background: var(--l-chip); color: var(--l-muted); }}
.l-cuerpo {{ min-width: 0; flex: 1; }}
.l-titulo {{ font-size: 1.02rem; font-weight: 600; color: var(--l-texto); line-height: 1.35; margin: 0; }}
.l-org {{ font-size: .88rem; color: var(--l-texto2); margin: .15rem 0 .55rem 0; }}
.l-chips {{ display: flex; flex-wrap: wrap; gap: .4rem; }}
.l-chip {{ display: inline-flex; align-items: center; gap: .3rem; font-size: .78rem; font-weight: 500;
          padding: .18rem .55rem; border-radius: 999px; background: var(--l-chip); color: var(--l-texto2); }}
.l-chip.l-alto {{ background: var(--l-alto-bg); color: var(--l-alto-tx); font-weight: 600; }}
.l-chip.l-medio {{ background: var(--l-medio-bg); color: var(--l-medio-tx); font-weight: 600; }}
.l-chip.l-bajo {{ background: var(--l-bajo-bg); color: var(--l-bajo-tx); font-weight: 600; }}
.l-chip .l-ico {{ font-family: 'Material Symbols Rounded'; font-size: 15px; line-height: 1; font-weight: 400;
                 font-feature-settings: 'liga'; -webkit-font-feature-settings: 'liga'; }}
.l-id {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .74rem; color: var(--l-muted); }}

/* --- Bloques del detalle --- */
.l-veredicto {{ background: var(--l-primario-suave); border-radius: .6rem; padding: .75rem .9rem;
               color: var(--l-texto); font-size: .93rem; line-height: 1.45; }}
.l-veredicto b {{ color: var(--l-primario); font-weight: 600; }}
.l-lista {{ margin: .2rem 0 0 0; padding-left: 1.1rem; color: var(--l-texto2); font-size: .88rem; line-height: 1.45; }}
.l-lista li {{ margin-bottom: .3rem; }}
.l-nota {{ font-size: .8rem; color: var(--l-muted); line-height: 1.4; }}
.l-dato {{ font-size: .88rem; color: var(--l-texto2); line-height: 1.5; }}
.l-dato b {{ color: var(--l-texto); font-weight: 600; }}
.l-pago {{ border-left: 3px solid var(--l-primario); padding: .35rem .7rem; font-size: .86rem;
          color: var(--l-texto2); background: var(--l-primario-suave); border-radius: 0 .4rem .4rem 0; }}
</style>
"""
