# -*- coding: utf-8 -*-
"""
Módulo: Estilos (estilos)
------------------------
Hoja de estilos de la interfaz, dirección "editorial clara": lienzo color papel,
tarjetas casi blancas con bordes finos, tinta grafito (nunca negro puro), un
único acento azul tinta para lo interactivo y una serif editorial (Newsreader)
para títulos, cifras y scores. Movimiento sobrio y desactivable (prefers-reduced-motion).

Los colores base (fondo, texto, primario, fuentes) vienen de .streamlit/config.toml;
aquí se definen superficies, insignias, chips, animaciones y el retoque de los controles.

Los selectores `data-testid` dependen de la versión de Streamlit fijada en
requirements.txt: revisar este archivo si se actualiza Streamlit.
"""

# Estados (alto/medio/bajo): las marcas usan la paleta de estado fija de la guía
# de visualización; el texto, un tono oscuro de la misma familia con contraste
# >= 4.5:1 sobre su fondo. Siempre acompañados de número o texto (nunca solo color).
TOKENS = {
    "fondo": "#f6f4ef",
    "superficie": "#ffffff",
    "superficie_2": "#fbfaf7",
    "superficie_hover": "#fdfcfa",
    "borde": "#e7e3da",
    "borde_fuerte": "#d6d0c3",
    "texto": "#1a1917",
    "texto2": "#45433e",
    "muted": "#6f6c64",
    "tenue": "#8f8b81",
    "acento": "#2a5bd7",
    "acento_claro": "#1f47a8",
    "acento_suave": "rgba(42,91,215,.08)",
    "alto": "#0ca30c", "alto_tx": "#17672f", "alto_bg": "#e7f4ea",
    "medio": "#fab219", "medio_tx": "#7a4f00", "medio_bg": "#fbf1dc",
    "bajo": "#d03b3b", "bajo_tx": "#a32626", "bajo_bg": "#fbe8e6",
    "chip": "#f3f1ec",
    "sombra": "0 1px 2px rgba(26,25,23,.04), 0 6px 20px -12px rgba(26,25,23,.18)",
    "sombra_alta": "0 2px 4px rgba(26,25,23,.05), 0 16px 36px -18px rgba(26,25,23,.28)",
    "serif": "'Newsreader', Georgia, 'Times New Roman', serif",
    "curva": "cubic-bezier(.2,.7,.2,1)",
}


def css():
    """Hoja de estilos completa."""
    variables = ";".join(f"--l-{k.replace('_', '-')}: {v}" for k, v in TOKENS.items())
    return f"""
<style>
:root {{ {variables}; }}

/* El anillo del score anima su avance (--p) al cargar: requiere registrar la propiedad.
   "<" va escapado (\\3C = <, \\3E = >): st.html sanea el HTML y lo tomaría como etiqueta. */
@property --p {{ syntax: '\\3C percentage\\3E'; inherits: false; initial-value: 0%; }}

/* ===================== Movimiento ===================== */
@keyframes l-entra {{ from {{ opacity: 0; transform: translateY(8px); }} to {{ opacity: 1; transform: none; }} }}
@keyframes l-aparece {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
@keyframes l-llena {{ from {{ --p: 0%; }} }}
@keyframes l-subraya {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}

/* ===================== Lienzo ===================== */
.stApp {{ background: var(--l-fondo); }}
.block-container {{ max-width: 1180px; padding-top: 4.6rem; padding-bottom: 3rem; }}
[data-testid="stDecoration"], footer {{ display: none !important; }}
[data-testid="stHeader"] {{
  background: rgba(246,244,239,.82); backdrop-filter: saturate(1.4) blur(14px); -webkit-backdrop-filter: saturate(1.4) blur(14px);
  border-bottom: 1px solid var(--l-borde);
}}
::selection {{ background: rgba(42,91,215,.18); }}
a {{ text-underline-offset: .18em; }}

/* ===================== Navegación superior ===================== */
[data-testid="stTopNavLink"] {{ border-radius: .45rem; position: relative; transition: background .2s var(--l-curva); }}
[data-testid="stTopNavLink"] span {{ color: var(--l-muted); font-weight: 500; font-size: .9rem; transition: color .2s var(--l-curva); }}
[data-testid="stTopNavLink"]:hover {{ background: rgba(26,25,23,.04); }}
[data-testid="stTopNavLink"]:hover span {{ color: var(--l-texto); }}
[data-testid="stTopNavLink"][aria-current="page"], [data-testid="stTopNavLink"].active {{ background: transparent !important; }}
[data-testid="stTopNavLink"][aria-current="page"] span, [data-testid="stTopNavLink"].active span {{ color: var(--l-texto); font-weight: 600; }}
[data-testid="stTopNavLink"][aria-current="page"]::after, [data-testid="stTopNavLink"].active::after {{
  content: ''; position: absolute; left: .7rem; right: .7rem; bottom: -1px; height: 2px; border-radius: 2px;
  background: var(--l-acento); transform-origin: left; animation: l-subraya .35s var(--l-curva) both;
}}

/* ===================== Tipografía ===================== */
h1, h2, h3, h4, h5 {{ font-family: var(--l-serif) !important; letter-spacing: -.01em; color: var(--l-texto); }}
[data-testid="stMarkdownContainer"] h5 {{ font-size: 1.22rem; font-weight: 600; margin-bottom: .1rem; }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{ color: var(--l-muted); }}
[data-testid="stWidgetLabel"] p {{ color: var(--l-texto2); font-size: .8rem; font-weight: 500; letter-spacing: .01em; }}

/* ===================== Superficies (tarjetas: st.container key "lcard_*") ===================== */
[class*="st-key-lcard"] {{
  background: var(--l-superficie);
  border-color: var(--l-borde) !important; border-radius: .875rem !important;
  box-shadow: var(--l-sombra);
  transition: border-color .25s var(--l-curva), box-shadow .25s var(--l-curva), transform .25s var(--l-curva);
  animation: l-entra .5s var(--l-curva) both;
}}
[class*="st-key-lcard"]:hover {{ border-color: var(--l-borde-fuerte) !important; box-shadow: var(--l-sombra-alta); transform: translateY(-1px); }}
/* Franja de urgencia del cierre (key "lcard_u-bajo_*" / "lcard_u-medio_*") */
[class*="st-key-lcard_u-bajo"] {{ box-shadow: inset 3px 0 0 var(--l-bajo), var(--l-sombra); }}
[class*="st-key-lcard_u-bajo"]:hover {{ box-shadow: inset 3px 0 0 var(--l-bajo), var(--l-sombra-alta); }}
[class*="st-key-lcard_u-medio"] {{ box-shadow: inset 3px 0 0 var(--l-medio), var(--l-sombra); }}
[class*="st-key-lcard_u-medio"]:hover {{ box-shadow: inset 3px 0 0 var(--l-medio), var(--l-sombra-alta); }}

/* ===================== Controles ===================== */
[data-testid="stBaseButton-secondary"], [data-testid="stBaseLinkButton-secondary"],
[data-testid="stBaseButton-secondaryFormSubmit"], [data-testid="stPopoverButton"] {{
  background: var(--l-superficie) !important; border: 1px solid var(--l-borde-fuerte) !important;
  color: var(--l-texto) !important; font-weight: 500; box-shadow: 0 1px 1px rgba(26,25,23,.04);
  transition: background .2s var(--l-curva), border-color .2s var(--l-curva), transform .15s var(--l-curva);
}}
[data-testid="stBaseButton-secondary"]:hover, [data-testid="stBaseLinkButton-secondary"]:hover,
[data-testid="stBaseButton-secondaryFormSubmit"]:hover, [data-testid="stPopoverButton"]:hover {{
  background: var(--l-superficie-2) !important; border-color: var(--l-tenue) !important;
}}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{
  background: var(--l-acento) !important; border: 1px solid var(--l-acento) !important; color: #fff !important;
  box-shadow: 0 1px 2px rgba(31,71,168,.25), 0 6px 16px -8px rgba(42,91,215,.55); font-weight: 600;
  transition: background .2s var(--l-curva), box-shadow .2s var(--l-curva), transform .15s var(--l-curva);
}}
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {{
  background: var(--l-acento-claro) !important; border-color: var(--l-acento-claro) !important;
  box-shadow: 0 2px 4px rgba(31,71,168,.25), 0 10px 22px -10px rgba(42,91,215,.6);
}}
[data-testid^="stBaseButton"]:active {{ transform: translateY(1px); }}
[data-testid="stBaseButton-secondary"]:disabled, [data-testid="stBaseButton-primary"]:disabled {{ opacity: .45; box-shadow: none; }}
[data-testid="stExpander"] details {{ background: var(--l-superficie-2); border-color: var(--l-borde) !important; border-radius: .625rem; }}
[data-testid="stExpander"] summary p {{ font-weight: 500; color: var(--l-texto2); font-size: .9rem; }}
[data-testid="stExpander"] summary:hover p {{ color: var(--l-acento-claro); }}
[data-testid="stExpanderDetails"] {{ animation: l-aparece .3s var(--l-curva) both; }}
[data-testid="stAlert"] {{ border-radius: .625rem; animation: l-entra .4s var(--l-curva) both; }}

/* Radio horizontal con aspecto de control segmentado ("píldoras"): st.radio con key "pill_*" */
[class*="st-key-pill_"] [role="radiogroup"] {{ gap: 0 !important; display: inline-flex; flex-wrap: wrap;
  background: #efece5; border: 1px solid var(--l-borde); border-radius: .6rem; padding: 3px; }}
[class*="st-key-pill_"] [role="radiogroup"] label {{ margin: 0 !important; padding: .32rem .85rem; border-radius: .45rem;
  cursor: pointer; transition: background .2s var(--l-curva), box-shadow .2s var(--l-curva); }}
[class*="st-key-pill_"] [role="radiogroup"] label > div:first-child {{ display: none; }}
[class*="st-key-pill_"] [role="radiogroup"] label p {{ font-size: .84rem; font-weight: 500; color: var(--l-muted); }}
[class*="st-key-pill_"] [role="radiogroup"] label:hover p {{ color: var(--l-texto); }}
[class*="st-key-pill_"] [role="radiogroup"] label:has(input:checked) {{ background: var(--l-superficie);
  box-shadow: 0 1px 2px rgba(26,25,23,.08), 0 0 0 1px var(--l-borde); }}
[class*="st-key-pill_"] [role="radiogroup"] label:has(input:checked) p {{ color: var(--l-texto); font-weight: 600; }}

/* ===================== Cabecera de página ===================== */
.l-cabecera {{ display: flex; gap: .95rem; align-items: center; animation: l-entra .5s var(--l-curva) both; }}
.l-cabecera .l-ico-pag {{ width: 2.7rem; height: 2.7rem; border-radius: 50%; display: flex; align-items: center;
  justify-content: center; background: var(--l-superficie); border: 1px solid var(--l-borde-fuerte); flex: 0 0 auto;
  box-shadow: var(--l-sombra); }}
.l-cabecera .l-ico-pag span {{ font-family: 'Material Symbols Rounded'; font-size: 21px; color: var(--l-acento); }}
.l-cabecera h1 {{ font-family: var(--l-serif) !important; font-size: 2.15rem; font-weight: 500; margin: 0; padding: 0;
  line-height: 1.05; color: var(--l-texto); letter-spacing: -.02em; }}
.l-cabecera p {{ color: var(--l-muted); margin: .3rem 0 0 0; font-size: .92rem; }}
.l-sync {{ text-align: right; font-size: .78rem; color: var(--l-muted); margin-bottom: .35rem; }}
.l-sync b {{ color: var(--l-texto2); font-weight: 600; }}
.l-seccion {{ font-size: .7rem; font-weight: 600; letter-spacing: .12em; text-transform: uppercase;
             color: var(--l-muted); margin: .5rem 0 .5rem 0; display: flex; align-items: center; gap: .6rem; }}
.l-seccion::after {{ content: ''; flex: 1; height: 1px; background: var(--l-borde); }}

/* ===================== KPIs ===================== */
.l-kpi {{ background: var(--l-superficie); border: 1px solid var(--l-borde); border-radius: .875rem;
  padding: 1rem 1.1rem 1.05rem; height: 100%; box-shadow: var(--l-sombra);
  animation: l-entra .55s var(--l-curva) both; transition: box-shadow .25s var(--l-curva), transform .25s var(--l-curva); }}
.l-kpi:hover {{ box-shadow: var(--l-sombra-alta); transform: translateY(-1px); }}
[data-testid="stColumn"]:nth-child(2) .l-kpi {{ animation-delay: .06s; }}
[data-testid="stColumn"]:nth-child(3) .l-kpi {{ animation-delay: .12s; }}
[data-testid="stColumn"]:nth-child(4) .l-kpi {{ animation-delay: .18s; }}
.l-kpi-top {{ display: flex; align-items: center; justify-content: space-between; }}
.l-kpi-label {{ font-size: .7rem; color: var(--l-muted); font-weight: 600; letter-spacing: .1em; text-transform: uppercase; }}
.l-kpi-ico {{ font-family: 'Material Symbols Rounded'; font-size: 17px; width: 1.85rem; height: 1.85rem; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; }}
.l-kpi-valor {{ font-family: var(--l-serif); font-size: 2.45rem; font-weight: 500; color: var(--l-texto);
  letter-spacing: -.02em; margin-top: .3rem; line-height: 1; font-variant-numeric: lining-nums tabular-nums; }}
.l-kpi-pie {{ font-size: .76rem; color: var(--l-muted); margin-top: .45rem; padding-top: .45rem; border-top: 1px solid var(--l-borde); }}
.l-tinte-acento {{ background: var(--l-acento-suave); color: var(--l-acento); }}
.l-tinte-alto {{ background: var(--l-alto-bg); color: var(--l-alto-tx); }}
.l-tinte-medio {{ background: var(--l-medio-bg); color: var(--l-medio-tx); }}
.l-tinte-bajo {{ background: var(--l-bajo-bg); color: var(--l-bajo-tx); }}

/* ===================== Tarjeta de licitación ===================== */
.l-tarjeta {{ display: flex; gap: 1.05rem; align-items: flex-start; }}
.l-anillo {{ position: relative; width: 3.6rem; height: 3.6rem; flex: 0 0 auto; border-radius: 50%;
  background: conic-gradient(var(--c) var(--p), #ece8df 0); animation: l-llena 1.1s var(--l-curva) .15s both; }}
.l-anillo::before {{ content: ''; position: absolute; inset: 4px; border-radius: 50%; background: var(--l-superficie); }}
.l-anillo .l-anillo-txt {{ position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center;
  justify-content: center; line-height: 1; }}
.l-anillo b {{ font-family: var(--l-serif); font-size: 1.3rem; font-weight: 600; color: var(--l-texto);
  font-variant-numeric: lining-nums tabular-nums; }}
.l-anillo small {{ font-size: .52rem; color: var(--l-muted); font-weight: 600; letter-spacing: .07em; margin-top: .12rem; }}
.l-cuerpo {{ min-width: 0; flex: 1; }}
.l-titulo {{ font-family: var(--l-serif); font-size: 1.16rem; font-weight: 600; color: var(--l-texto); line-height: 1.3;
  margin: 0; letter-spacing: -.005em; }}
.l-org {{ font-size: .85rem; color: var(--l-muted); margin: .25rem 0 .65rem 0; }}
.l-chips {{ display: flex; flex-wrap: wrap; gap: .4rem; }}
.l-chip {{ display: inline-flex; align-items: center; gap: .32rem; font-size: .75rem; font-weight: 500;
  padding: .2rem .6rem; border-radius: 999px; background: var(--l-chip); color: var(--l-texto2);
  border: 1px solid var(--l-borde); transition: border-color .2s var(--l-curva); }}
.l-chip.l-alto {{ background: var(--l-alto-bg); color: var(--l-alto-tx); border-color: transparent; font-weight: 600; }}
.l-chip.l-medio {{ background: var(--l-medio-bg); color: var(--l-medio-tx); border-color: transparent; font-weight: 600; }}
.l-chip.l-bajo {{ background: var(--l-bajo-bg); color: var(--l-bajo-tx); border-color: transparent; font-weight: 600; }}
.l-chip .l-ico {{ font-family: 'Material Symbols Rounded'; font-size: 15px; line-height: 1; font-weight: 400; }}
.l-id {{ font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace; font-size: .72rem; color: var(--l-tenue); }}

/* ===================== Detalle ===================== */
.l-veredicto {{ background: var(--l-superficie-2); border: 1px solid var(--l-borde); border-left: 3px solid var(--l-acento);
  border-radius: .25rem .7rem .7rem .25rem; padding: .85rem 1rem;
  color: var(--l-texto); font-family: var(--l-serif); font-size: 1.04rem; line-height: 1.5; }}
.l-veredicto b {{ font-family: 'Inter', sans-serif; color: var(--l-acento); font-weight: 600; font-size: .7rem;
  letter-spacing: .1em; text-transform: uppercase; margin-right: .2rem; }}
.l-lista {{ margin: .1rem 0 0 0; padding-left: 1.05rem; color: var(--l-texto2); font-size: .87rem; line-height: 1.55; }}
.l-lista li {{ margin-bottom: .35rem; }}
.l-lista li::marker {{ color: var(--l-acento); }}
.l-nota {{ font-size: .8rem; color: var(--l-muted); line-height: 1.45; }}
.l-dato {{ font-size: .86rem; color: var(--l-texto2); line-height: 1.5; }}
.l-dato b {{ color: var(--l-texto); font-weight: 600; }}
.l-aviso {{ border: 1px solid #f0dfb8; border-left: 3px solid var(--l-medio); background: var(--l-medio-bg);
  border-radius: .25rem .55rem .55rem .25rem; padding: .55rem .8rem; font-size: .86rem; color: var(--l-texto); line-height: 1.45;
  margin-top: .5rem; }}
.l-crit {{ width: 100%; border-collapse: collapse; font-size: .84rem; color: var(--l-texto2); }}
.l-crit th {{ text-align: left; font-weight: 600; color: var(--l-muted); font-size: .68rem; letter-spacing: .1em;
  text-transform: uppercase; padding: .35rem .45rem; border-bottom: 1px solid var(--l-borde-fuerte); }}
.l-crit td {{ padding: .55rem .45rem; border-bottom: 1px solid var(--l-borde); vertical-align: top; line-height: 1.4; }}
.l-crit tr:last-child td {{ border-bottom: 0; }}
.l-crit tbody tr {{ transition: background .2s var(--l-curva); }}
.l-crit tbody tr:hover {{ background: var(--l-superficie-2); }}
.l-crit td b {{ color: var(--l-texto); font-weight: 600; }}
.l-crit .l-crit-nota {{ white-space: nowrap; font-family: var(--l-serif); font-size: 1.05rem; font-weight: 600; color: var(--l-texto); }}
.l-pago {{ border: 1px solid var(--l-borde); background: var(--l-superficie-2); padding: .55rem .8rem;
  font-size: .86rem; color: var(--l-texto2); border-radius: .55rem; display: flex; gap: .5rem; align-items: center; }}
.l-pago .l-ico {{ font-family: 'Material Symbols Rounded'; font-size: 17px; color: var(--l-acento); }}
details.l-tec {{ font-size: .76rem; color: var(--l-tenue); margin-top: .35rem; }}
details.l-tec summary {{ cursor: pointer; color: var(--l-muted); list-style: none; transition: color .2s var(--l-curva); }}
details.l-tec summary:hover {{ color: var(--l-acento-claro); }}
details.l-tec summary::-webkit-details-marker {{ display: none; }}
details.l-tec summary::before {{ content: '›'; display: inline-block; margin-right: .35rem; transition: transform .2s var(--l-curva); }}
details.l-tec[open] summary::before {{ transform: rotate(90deg); }}
details.l-tec div {{ margin-top: .3rem; font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace; line-height: 1.6;
  animation: l-aparece .25s var(--l-curva) both; }}
details.l-tec.l-tec-texto div {{ font-family: inherit; font-size: .84rem; color: var(--l-texto2); }}

/* ===================== Estados vacíos y pie ===================== */
.l-vacio {{ border: 1px dashed var(--l-borde-fuerte); background: rgba(255,255,255,.55); border-radius: .875rem;
  padding: 2.4rem 1rem; text-align: center; animation: l-entra .5s var(--l-curva) both; }}
.l-vacio .l-ico {{ font-family: 'Material Symbols Rounded'; font-size: 26px; color: var(--l-acento);
  background: var(--l-superficie); border: 1px solid var(--l-borde); width: 3rem; height: 3rem; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center; box-shadow: var(--l-sombra); }}
.l-vacio h4 {{ margin: .85rem 0 .25rem 0; font-size: 1.25rem; font-weight: 500; color: var(--l-texto); }}
.l-vacio p {{ margin: 0; color: var(--l-muted); font-size: .87rem; }}
.l-pie {{ margin-top: 2.8rem; padding-top: 1rem; border-top: 1px solid var(--l-borde-fuerte); font-size: .76rem;
  color: var(--l-muted); display: flex; justify-content: space-between; flex-wrap: wrap; gap: .5rem; }}
.l-pie span:first-child {{ font-family: var(--l-serif); font-size: .9rem; color: var(--l-texto2); }}

/* ===================== Gráficos ===================== */
[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"] {{ animation: l-aparece .6s var(--l-curva) .1s both; }}

/* Sin movimiento si el sistema lo pide */
@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{ animation: none !important; transition: none !important; }}
  [class*="st-key-lcard"]:hover, .l-kpi:hover {{ transform: none; }}
}}
</style>
"""
