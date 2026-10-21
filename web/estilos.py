# -*- coding: utf-8 -*-
"""
Módulo: Estilos (estilos)
------------------------
Hoja de estilos de la interfaz, dirección "premium oscuro": fondo casi negro,
superficies apenas elevadas con bordes sutiles, acento índigo y brillos suaves.

Los colores base (fondo, texto, primario, fuente) vienen de .streamlit/config.toml;
aquí se definen superficies, insignias, chips y el retoque de los controles.

Los selectores `data-testid` dependen de la versión de Streamlit fijada en
requirements.txt: revisar este archivo si se actualiza Streamlit.
"""

# Estados (alto/medio/bajo): marcas con la paleta de estado de la guía de
# visualización; el texto usa un tono más claro de la misma familia para
# legibilidad. Siempre acompañados de número o texto (nunca solo color).
TOKENS = {
    "fondo": "#08090a",
    "superficie": "#0f1012",
    "superficie_2": "#141517",
    "superficie_hover": "#16171a",
    "borde": "rgba(255,255,255,.07)",
    "borde_fuerte": "rgba(255,255,255,.13)",
    "texto": "#f7f8f8",
    "texto2": "#b4b8bf",
    "muted": "#7d828b",
    "tenue": "#5b5f67",
    "acento": "#5e6ad2",
    "acento_claro": "#8b92ee",
    "acento_suave": "rgba(94,106,210,.14)",
    "alto": "#0ca30c", "alto_tx": "#4cc38a", "alto_bg": "rgba(12,163,12,.13)",
    "medio": "#fab219", "medio_tx": "#f2b84b", "medio_bg": "rgba(250,178,25,.12)",
    "bajo": "#d03b3b", "bajo_tx": "#ef6461", "bajo_bg": "rgba(208,59,59,.15)",
    "chip": "rgba(255,255,255,.05)",
}


def css():
    """Hoja de estilos completa."""
    variables = ";".join(f"--l-{k.replace('_', '-')}: {v}" for k, v in TOKENS.items())
    return f"""
<style>
:root {{ {variables}; }}

/* ===================== Lienzo ===================== */
.stApp {{
  background:
    radial-gradient(1200px 520px at 50% -180px, rgba(94,106,210,.16), transparent 70%),
    var(--l-fondo);
}}
.block-container {{ max-width: 1180px; padding-top: 4.4rem; padding-bottom: 3rem; }}
[data-testid="stDecoration"], footer {{ display: none !important; }}
[data-testid="stHeader"] {{
  background: rgba(8,9,10,.72); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  border-bottom: 1px solid var(--l-borde);
}}
::selection {{ background: rgba(94,106,210,.45); }}

/* ===================== Navegación superior ===================== */
[data-testid="stTopNavLink"] {{ border-radius: .5rem; transition: background .15s ease; }}
[data-testid="stTopNavLink"] span {{ color: var(--l-muted); font-weight: 500; font-size: .9rem; }}
[data-testid="stTopNavLink"]:hover {{ background: rgba(255,255,255,.04); }}
[data-testid="stTopNavLink"]:hover span {{ color: var(--l-texto); }}
[data-testid="stTopNavLink"][aria-current="page"], [data-testid="stTopNavLink"].active {{ background: rgba(255,255,255,.06); }}
[data-testid="stTopNavLink"][aria-current="page"] span {{ color: var(--l-texto); }}

/* ===================== Tipografía ===================== */
h1, h2, h3, h4, h5 {{ letter-spacing: -.015em; }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{ color: var(--l-muted); }}
[data-testid="stWidgetLabel"] p {{ color: var(--l-texto2); font-size: .82rem; font-weight: 500; }}

/* ===================== Superficies (tarjetas: st.container key "lcard_*") ===================== */
[class*="st-key-lcard"] {{
  background: linear-gradient(180deg, rgba(255,255,255,.025), rgba(255,255,255,.01));
  border-color: var(--l-borde) !important; border-radius: .875rem !important;
  box-shadow: 0 1px 0 rgba(255,255,255,.04) inset, 0 12px 32px -18px rgba(0,0,0,.8);
  transition: border-color .15s ease, background .15s ease;
}}
[class*="st-key-lcard"]:hover {{ border-color: var(--l-borde-fuerte) !important; }}
/* Franja de urgencia del cierre (key "lcard_u-bajo_*" / "lcard_u-medio_*") */
[class*="st-key-lcard_u-bajo"] {{ box-shadow: inset 3px 0 0 var(--l-bajo), 0 12px 32px -18px rgba(0,0,0,.8); }}
[class*="st-key-lcard_u-medio"] {{ box-shadow: inset 3px 0 0 var(--l-medio), 0 12px 32px -18px rgba(0,0,0,.8); }}

/* ===================== Controles ===================== */
[data-testid="stBaseButton-secondary"], [data-testid="stBaseLinkButton-secondary"],
[data-testid="stBaseButton-secondaryFormSubmit"], [data-testid="stPopoverButton"] {{
  background: rgba(255,255,255,.035) !important; border: 1px solid var(--l-borde-fuerte) !important;
  color: var(--l-texto) !important; font-weight: 500; transition: background .15s ease, border-color .15s ease;
}}
[data-testid="stBaseButton-secondary"]:hover, [data-testid="stBaseLinkButton-secondary"]:hover,
[data-testid="stBaseButton-secondaryFormSubmit"]:hover, [data-testid="stPopoverButton"]:hover {{
  background: rgba(255,255,255,.07) !important; border-color: rgba(255,255,255,.2) !important;
}}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{
  background: linear-gradient(180deg, #6b76e0, #5560c8) !important; border: 1px solid rgba(255,255,255,.14) !important;
  box-shadow: 0 0 0 1px rgba(94,106,210,.35), 0 8px 24px -8px rgba(94,106,210,.75); font-weight: 600;
}}
[data-testid="stBaseButton-primary"]:hover {{ filter: brightness(1.08); }}
[data-testid="stBaseButton-secondary"]:disabled {{ opacity: .45; }}
[data-testid="stExpander"] details {{ background: rgba(255,255,255,.015); border-color: var(--l-borde) !important; border-radius: .625rem; }}
[data-testid="stExpander"] summary p {{ font-weight: 500; color: var(--l-texto2); font-size: .9rem; }}
[data-testid="stExpander"] summary:hover p {{ color: var(--l-texto); }}
[data-testid="stAlert"] {{ border-radius: .625rem; }}

/* Radio horizontal con aspecto de control segmentado ("píldoras"): st.radio con key "pill_*" */
[class*="st-key-pill_"] [role="radiogroup"] {{ gap: 0 !important; display: inline-flex; flex-wrap: wrap;
  background: rgba(255,255,255,.03); border: 1px solid var(--l-borde); border-radius: .6rem; padding: 3px; }}
[class*="st-key-pill_"] [role="radiogroup"] label {{ margin: 0 !important; padding: .32rem .8rem; border-radius: .45rem;
  cursor: pointer; transition: background .15s ease; }}
[class*="st-key-pill_"] [role="radiogroup"] label > div:first-child {{ display: none; }}
[class*="st-key-pill_"] [role="radiogroup"] label p {{ font-size: .84rem; font-weight: 500; color: var(--l-muted); }}
[class*="st-key-pill_"] [role="radiogroup"] label:hover p {{ color: var(--l-texto); }}
[class*="st-key-pill_"] [role="radiogroup"] label:has(input:checked) {{ background: rgba(255,255,255,.08);
  box-shadow: 0 1px 0 rgba(255,255,255,.06) inset; }}
[class*="st-key-pill_"] [role="radiogroup"] label:has(input:checked) p {{ color: var(--l-texto); }}

/* ===================== Cabecera de página ===================== */
.l-cabecera {{ display: flex; gap: .9rem; align-items: center; }}
.l-cabecera .l-ico-pag {{ width: 2.6rem; height: 2.6rem; border-radius: .7rem; display: flex; align-items: center;
  justify-content: center; background: var(--l-acento-suave); border: 1px solid rgba(139,146,238,.25); flex: 0 0 auto; }}
.l-cabecera .l-ico-pag span {{ font-family: 'Material Symbols Rounded'; font-size: 22px; color: var(--l-acento-claro); }}
.l-cabecera h1 {{ font-size: 1.6rem; font-weight: 650; margin: 0; padding: 0; line-height: 1.15; color: var(--l-texto); }}
.l-cabecera p {{ color: var(--l-muted); margin: .2rem 0 0 0; font-size: .9rem; }}
.l-sync {{ text-align: right; font-size: .78rem; color: var(--l-muted); margin-bottom: .35rem; }}
.l-sync b {{ color: var(--l-texto2); font-weight: 500; }}
.l-seccion {{ font-size: .72rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
             color: var(--l-tenue); margin: .3rem 0 .45rem 0; }}

/* ===================== KPIs ===================== */
.l-kpi {{ background: linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,.012));
  border: 1px solid var(--l-borde); border-radius: .875rem; padding: .95rem 1.05rem; height: 100%; }}
.l-kpi-top {{ display: flex; align-items: center; justify-content: space-between; }}
.l-kpi-label {{ font-size: .8rem; color: var(--l-muted); font-weight: 500; }}
.l-kpi-ico {{ font-family: 'Material Symbols Rounded'; font-size: 18px; width: 1.9rem; height: 1.9rem; border-radius: .55rem;
  display: flex; align-items: center; justify-content: center; }}
.l-kpi-valor {{ font-size: 1.85rem; font-weight: 650; color: var(--l-texto); letter-spacing: -.02em; margin-top: .35rem; line-height: 1.1; }}
.l-kpi-pie {{ font-size: .76rem; color: var(--l-tenue); margin-top: .2rem; }}
.l-tinte-acento {{ background: var(--l-acento-suave); color: var(--l-acento-claro); }}
.l-tinte-alto {{ background: var(--l-alto-bg); color: var(--l-alto-tx); }}
.l-tinte-medio {{ background: var(--l-medio-bg); color: var(--l-medio-tx); }}
.l-tinte-bajo {{ background: var(--l-bajo-bg); color: var(--l-bajo-tx); }}

/* ===================== Tarjeta de licitación ===================== */
.l-tarjeta {{ display: flex; gap: 1rem; align-items: flex-start; }}
.l-anillo {{ position: relative; width: 3.5rem; height: 3.5rem; flex: 0 0 auto; border-radius: 50%;
  background: conic-gradient(var(--c) var(--p), rgba(255,255,255,.08) 0); }}
.l-anillo::before {{ content: ''; position: absolute; inset: 4px; border-radius: 50%; background: var(--l-superficie); }}
.l-anillo .l-anillo-txt {{ position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center;
  justify-content: center; line-height: 1; }}
.l-anillo b {{ font-size: 1.05rem; font-weight: 700; color: var(--l-texto); }}
.l-anillo small {{ font-size: .56rem; color: var(--l-tenue); font-weight: 600; letter-spacing: .06em; margin-top: .15rem; }}
.l-cuerpo {{ min-width: 0; flex: 1; }}
.l-titulo {{ font-size: 1rem; font-weight: 600; color: var(--l-texto); line-height: 1.38; margin: 0; letter-spacing: -.005em; }}
.l-org {{ font-size: .86rem; color: var(--l-texto2); margin: .2rem 0 .6rem 0; }}
.l-chips {{ display: flex; flex-wrap: wrap; gap: .4rem; }}
.l-chip {{ display: inline-flex; align-items: center; gap: .32rem; font-size: .76rem; font-weight: 500;
  padding: .2rem .55rem; border-radius: 999px; background: var(--l-chip); color: var(--l-texto2);
  border: 1px solid var(--l-borde); }}
.l-chip.l-alto {{ background: var(--l-alto-bg); color: var(--l-alto-tx); border-color: transparent; font-weight: 600; }}
.l-chip.l-medio {{ background: var(--l-medio-bg); color: var(--l-medio-tx); border-color: transparent; font-weight: 600; }}
.l-chip.l-bajo {{ background: var(--l-bajo-bg); color: var(--l-bajo-tx); border-color: transparent; font-weight: 600; }}
.l-chip .l-ico {{ font-family: 'Material Symbols Rounded'; font-size: 15px; line-height: 1; font-weight: 400; }}
.l-id {{ font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace; font-size: .72rem; color: var(--l-tenue); }}

/* ===================== Detalle ===================== */
.l-veredicto {{ background: linear-gradient(135deg, rgba(94,106,210,.16), rgba(94,106,210,.05));
  border: 1px solid rgba(139,146,238,.22); border-radius: .7rem; padding: .8rem .95rem;
  color: var(--l-texto); font-size: .92rem; line-height: 1.5; }}
.l-veredicto b {{ color: var(--l-acento-claro); font-weight: 600; }}
.l-lista {{ margin: .1rem 0 0 0; padding-left: 1.05rem; color: var(--l-texto2); font-size: .87rem; line-height: 1.5; }}
.l-lista li {{ margin-bottom: .35rem; }}
.l-lista li::marker {{ color: var(--l-tenue); }}
.l-nota {{ font-size: .8rem; color: var(--l-muted); line-height: 1.45; }}
.l-dato {{ font-size: .86rem; color: var(--l-texto2); line-height: 1.5; }}
.l-aviso {{ border: 1px solid var(--l-borde); border-left: 3px solid var(--l-medio-tx); background: var(--l-medio-bg);
  border-radius: .55rem; padding: .5rem .75rem; font-size: .86rem; color: var(--l-texto); line-height: 1.45; margin-top: .45rem; }}
.l-crit {{ width: 100%; border-collapse: collapse; font-size: .84rem; color: var(--l-texto2); }}
.l-crit th {{ text-align: left; font-weight: 600; color: var(--l-muted); font-size: .74rem; padding: .3rem .4rem;
  border-bottom: 1px solid var(--l-borde); }}
.l-crit td {{ padding: .45rem .4rem; border-bottom: 1px solid var(--l-borde); vertical-align: top; line-height: 1.4; }}
.l-crit td b {{ color: var(--l-texto); font-weight: 600; }}
.l-crit .l-crit-nota {{ white-space: nowrap; font-weight: 700; color: var(--l-texto); }}
details.l-tec.l-tec-texto div {{ font-family: inherit; font-size: .84rem; color: var(--l-texto2); }}
.l-dato b {{ color: var(--l-texto); font-weight: 600; }}
.l-pago {{ border: 1px solid var(--l-borde); background: rgba(255,255,255,.025); padding: .5rem .75rem;
  font-size: .86rem; color: var(--l-texto2); border-radius: .55rem; display: flex; gap: .5rem; align-items: center; }}
.l-pago .l-ico {{ font-family: 'Material Symbols Rounded'; font-size: 17px; color: var(--l-acento-claro); }}
details.l-tec {{ font-size: .76rem; color: var(--l-tenue); margin-top: .35rem; }}
details.l-tec summary {{ cursor: pointer; color: var(--l-muted); list-style: none; }}
details.l-tec summary::-webkit-details-marker {{ display: none; }}
details.l-tec summary::before {{ content: '›'; display: inline-block; margin-right: .35rem; transition: transform .15s; }}
details.l-tec[open] summary::before {{ transform: rotate(90deg); }}
details.l-tec div {{ margin-top: .3rem; font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace; line-height: 1.6; }}

/* ===================== Estados vacíos y pie ===================== */
.l-vacio {{ border: 1px dashed var(--l-borde-fuerte); border-radius: .875rem; padding: 2.2rem 1rem; text-align: center; }}
.l-vacio .l-ico {{ font-family: 'Material Symbols Rounded'; font-size: 28px; color: var(--l-acento-claro);
  background: var(--l-acento-suave); width: 3rem; height: 3rem; border-radius: .8rem; display: inline-flex;
  align-items: center; justify-content: center; }}
.l-vacio h4 {{ margin: .8rem 0 .25rem 0; font-size: 1rem; font-weight: 600; color: var(--l-texto); }}
.l-vacio p {{ margin: 0; color: var(--l-muted); font-size: .87rem; }}
.l-pie {{ margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--l-borde); font-size: .76rem;
  color: var(--l-tenue); display: flex; justify-content: space-between; flex-wrap: wrap; gap: .5rem; }}
</style>
"""
