# -*- coding: utf-8 -*-
"""
Módulo: Panorama (visualizaciones)
---------------------------------
Pestaña de análisis agregado del dashboard. Cada gráfico tiene:
1. Una función pura `datos_*` que prepara las filas (probada sin Streamlit).
2. Un constructor Altair `grafico_*` que solo dibuja.
3. Una vista de tabla equivalente y el tamaño de la muestra (n) visible.

Colores: paleta de referencia de la guía de visualización, validada con su
script (una serie = azul slot 1; magnitud = rampa secuencial azul).
"""

from datetime import datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st

from core.parsing import cargar_analisis_guardado, dias_para_cierre, es_valor_util, parsear_fecha_hora

ESTADOS_ACTIVOS = ("analizado", "favorita")
ESTADOS_CON_ANALISIS = ("analizado", "favorita", "archivada")
MIN_EVALUACIONES_CALIBRACION = 10
TRAMOS_SCORE = (("1–4", 1, 4), ("5–6", 5, 6), ("7–8", 7, 8), ("9–10", 9, 10))
PERIODOS = {"Últimos 7 días": 7, "Últimos 30 días": 30, "Últimos 90 días": 90, "Todo": None}

# Tokens de los gráficos, alineados con web/estilos.py (tema "premium oscuro").
# Validados con el script de la guía de visualización contra la superficie #0f1012:
# serie índigo con contraste >= 3:1 y rampa índigo de un solo tono (--ordinal).
TEMAS = {
    "dark": {"serie": "#7c82f2", "rampa": ["#3f44a8", "#5e6ad2", "#8b92ee", "#bcc0fa"],
             "superficie": "#0f1012", "texto": "#f7f8f8", "texto2": "#b4b8bf", "muted": "#7d828b",
             "grid": "rgba(255,255,255,0.06)", "eje": "rgba(255,255,255,0.12)"},
    # Paleta clara de referencia (sin uso en la UI actual; se conserva para un tema claro futuro)
    "light": {"serie": "#2a78d6", "rampa": ["#86b6ef", "#5598e7", "#256abf", "#104281"],
              "superficie": "#fcfcfb", "texto": "#0b0b0b", "texto2": "#52514e", "muted": "#898781",
              "grid": "#e1e0d9", "eje": "#c3c2b7"},
}


# ===================================================================
# PREPARACIÓN DE DATOS (funciones puras)
# ===================================================================

def _fecha_registro(licit):
    """Fecha (date) en que la licitación entró a la BD."""
    f = parsear_fecha_hora((licit.get("fecha_creacion") or "")[:19])
    return f.date() if f else None


def _titulo_corto(licit, largo=60):
    titulo = licit.get("titulo") if es_valor_util(licit.get("titulo")) else f"Licitación {licit['id_externo']}"
    return titulo if len(titulo) <= largo else titulo[:largo - 1] + "…"


def en_periodo(licitaciones, dias, ahora=None):
    """Licitaciones registradas en los últimos `dias` días (None = todas)."""
    if dias is None:
        return list(licitaciones)
    desde = (ahora or datetime.now()).date() - timedelta(days=dias - 1)
    return [l for l in licitaciones if (_fecha_registro(l) or desde) >= desde]


def datos_embudo(licitaciones, ejecuciones, dias=None, ahora=None):
    """
    Etapas del embudo en el periodo, o None si no hay ejecuciones registradas.

    - Listado: suma, por fecha consultada, del mayor total del listado (varias
      ejecuciones del mismo día no se cuentan dos veces).
    - Relevantes / Analizadas / Favoritas: licitaciones registradas desde la
      primera ejecución registrada, para que las etapas sean comparables.
    """
    ahora = ahora or datetime.now()
    desde = ahora.date() - timedelta(days=dias - 1) if dias else None
    por_fecha = {}
    for e in ejecuciones:
        fecha = e.get("fecha_consulta") or (e.get("inicio") or "")[:10]
        if not fecha or (desde and fecha < desde.isoformat()):
            continue
        por_fecha[fecha] = max(por_fecha.get(fecha, 0), e.get("total_listado") or 0)
    if not por_fecha:
        return None

    primera = min(por_fecha)
    base = [l for l in licitaciones if (_fecha_registro(l) and _fecha_registro(l).isoformat() >= primera)]
    if desde:
        base = [l for l in base if _fecha_registro(l) >= desde]
    analizadas = [l for l in base if l.get("analisis_ia_json")]
    return [
        {"etapa": "Publicadas en el portal", "orden": 1, "cantidad": sum(por_fecha.values())},
        {"etapa": "Coinciden con tu perfil", "orden": 2, "cantidad": len(base)},
        {"etapa": "Analizadas por la IA", "orden": 3, "cantidad": len(analizadas)},
        {"etapa": "Favoritas", "orden": 4, "cantidad": sum(1 for l in base if l.get("estado") == "favorita")},
    ]


def datos_calendario(licitaciones, ahora=None):
    """Oportunidades activas aún abiertas, ordenadas por cierre."""
    ahora = ahora or datetime.now()
    filas = []
    for l in licitaciones:
        cierre = parsear_fecha_hora(l.get("fecha_cierre"))
        if l.get("estado") not in ESTADOS_ACTIVOS or not cierre or cierre < ahora:
            continue
        inicio = parsear_fecha_hora(l.get("fecha_publicacion")) or parsear_fecha_hora((l.get("fecha_creacion") or "")[:19]) or ahora
        filas.append({
            "id_externo": l["id_externo"], "titulo": _titulo_corto(l, 55), "organismo": l.get("organismo") or "—",
            "inicio": inicio, "cierre": cierre, "score": l.get("score_ia"),
            "dias": dias_para_cierre(l.get("fecha_cierre"), ahora),
            "favorita": l.get("estado") == "favorita",
        })
    return sorted(filas, key=lambda f: f["cierre"])


def datos_riesgo(licitaciones):
    """Licitaciones con score y con reclamos de pago extraídos de la ficha."""
    return [{
        "id_externo": l["id_externo"], "titulo": _titulo_corto(l, 70), "organismo": l.get("organismo") or "—",
        "reclamos": l["reclamos_pago_n"], "score": l["score_ia"],
    } for l in licitaciones
        if l.get("estado") in ESTADOS_CON_ANALISIS and l.get("score_ia") is not None and l.get("reclamos_pago_n") is not None]


def datos_histograma(licitaciones):
    """Cantidad de licitaciones por score (1 a 10, incluidos los ceros)."""
    conteo = {s: 0 for s in range(1, 11)}
    for l in licitaciones:
        s = l.get("score_ia")
        if l.get("estado") in ESTADOS_CON_ANALISIS and isinstance(s, int) and s in conteo:
            conteo[s] += 1
    return [{"score": s, "cantidad": n} for s, n in conteo.items()]


def datos_calibracion(licitaciones):
    """
    Evaluaciones humanas agrupadas por tramo de score.

    Returns:
        dict: total evaluadas, filas por tramo (n, sí, tal vez, no, % sí) y
              resumen de la evaluación del score (acertado / muy alto / muy bajo).
    """
    evaluadas = [l for l in licitaciones if l.get("eval_postularia") and l.get("score_ia") is not None]
    filas = []
    for etiqueta, desde, hasta in TRAMOS_SCORE:
        grupo = [l for l in evaluadas if desde <= l["score_ia"] <= hasta]
        n = len(grupo)
        cuenta = {op: sum(1 for l in grupo if l["eval_postularia"] == op) for op in ("si", "tal_vez", "no")}
        filas.append({"tramo": etiqueta, "n": n, "si": cuenta["si"], "tal_vez": cuenta["tal_vez"], "no": cuenta["no"],
                      "pct_si": round(100 * cuenta["si"] / n) if n else None})
    con_eval_score = [l for l in licitaciones if l.get("eval_score")]
    resumen = {op: sum(1 for l in con_eval_score if l["eval_score"] == op) for op in ("acertado", "muy_alto", "muy_bajo")}
    return {"total": len(evaluadas), "tramos": filas, "eval_score": resumen, "total_eval_score": len(con_eval_score)}


# ===================================================================
# GRÁFICOS (Altair)
# ===================================================================

def _config(chart, t):
    """Chrome recesivo: grilla y ejes en hairline, texto en tintas de texto."""
    return (chart.configure(background="transparent")   # El fondo lo pone la tarjeta
            .configure_view(stroke=None)
            .configure_axis(gridColor=t["grid"], domainColor=t["eje"], tickColor=t["eje"],
                            labelColor=t["muted"], titleColor=t["texto2"], labelFontSize=12, titleFontSize=12,
                            titleFontWeight="normal")
            .configure_legend(labelColor=t["texto2"], titleColor=t["texto2"]))


def grafico_embudo(filas, t):
    df = pd.DataFrame(filas)
    total = df["cantidad"].iloc[0] or 1
    df["pct"] = (100 * df["cantidad"] / total).map(lambda p: f"{p:.1f} %".replace(".", ","))
    df["etiqueta"] = df.apply(lambda r: f"{r['cantidad']:,}".replace(",", ".") + (f"  ({r['pct']})" if r["orden"] > 1 else ""), axis=1)
    base = alt.Chart(df).encode(
        y=alt.Y("etapa:N", sort=alt.SortField("orden"), title=None, axis=alt.Axis(labelColor=t["texto2"], labelLimit=200)),
        x=alt.X("cantidad:Q", title=None, axis=alt.Axis(grid=False, labels=False, ticks=False, domain=False)),
        tooltip=[alt.Tooltip("etapa:N", title="Etapa"), alt.Tooltip("cantidad:Q", title="Cantidad", format=",d"),
                 alt.Tooltip("pct:N", title="% de lo publicado")],
    )
    barras = base.mark_bar(color=t["serie"], cornerRadiusEnd=4, height=18)
    textos = base.mark_text(align="left", dx=6, color=t["texto2"], fontSize=12).encode(text="etiqueta:N")
    return _config((barras + textos).properties(height=4 * 38), t)


def grafico_calendario(filas, t, ahora=None):
    ahora = ahora or datetime.now()
    # Ventana enfocada en lo que importa (hasta el cierre): una semana atrás como contexto
    desde = ahora - timedelta(days=7)
    df = pd.DataFrame(filas)
    df["inicio_visible"] = df["inicio"].map(lambda f: max(f, desde))
    hoy = pd.DataFrame({"hoy": [ahora]})
    orden = list(df["titulo"])
    dominio = [desde, max(df["cierre"]) + timedelta(days=2)]
    barras = alt.Chart(df).mark_bar(height=12, cornerRadius=4).encode(
        y=alt.Y("titulo:N", sort=orden, title=None, axis=alt.Axis(labelLimit=320, labelColor=t["texto2"])),
        x=alt.X("inicio_visible:T", title=None, axis=alt.Axis(format="%d %b"), scale=alt.Scale(domain=dominio)),
        x2="cierre:T",
        color=alt.Color("score:Q", title="Score", scale=alt.Scale(domain=[1, 10], range=t["rampa"]),
                        legend=alt.Legend(orient="top", gradientLength=160)),
        tooltip=[alt.Tooltip("titulo:N", title="Licitación"), alt.Tooltip("organismo:N", title="Organismo"),
                 alt.Tooltip("score:Q", title="Score"), alt.Tooltip("inicio:T", title="Publicación", format="%d/%m/%Y"),
                 alt.Tooltip("cierre:T", title="Cierre", format="%d/%m/%Y %H:%M"),
                 alt.Tooltip("dias:Q", title="Días para el cierre")],
    )
    regla = alt.Chart(hoy).mark_rule(color=t["muted"], strokeWidth=1).encode(x="hoy:T")
    etiqueta_hoy = alt.Chart(hoy).mark_text(text="hoy", dy=-6, color=t["muted"], fontSize=11, baseline="bottom", align="left", dx=3).encode(
        x="hoy:T", y=alt.value(0))
    return _config((barras + regla + etiqueta_hoy).properties(height=max(120, 30 * len(df) + 40)), t)


def grafico_riesgo(filas, t):
    df = pd.DataFrame(filas)
    tooltip = [alt.Tooltip("titulo:N", title="Licitación"), alt.Tooltip("organismo:N", title="Organismo"),
               alt.Tooltip("score:Q", title="Score"), alt.Tooltip("reclamos:Q", title="Reclamos por pagos atrasados")]
    enc = dict(
        x=alt.X("reclamos:Q", title="Reclamos por pagos atrasados (últimos 12 meses)", scale=alt.Scale(zero=True)),
        y=alt.Y("score:Q", title="Score", scale=alt.Scale(domain=[0, 10]), axis=alt.Axis(values=list(range(0, 11, 2)))),
    )
    puntos = alt.Chart(df).mark_circle(size=90, color=t["serie"], opacity=0.85, stroke=t["superficie"], strokeWidth=2).encode(**enc)
    # Área de acierto mayor que la marca (≥24px) para el tooltip
    objetivo = alt.Chart(df).mark_circle(size=700, opacity=0).encode(**enc, tooltip=tooltip)
    return _config((puntos + objetivo).properties(height=320), t)


def grafico_histograma(filas, t):
    df = pd.DataFrame(filas)
    return _config(alt.Chart(df).mark_bar(color=t["serie"], cornerRadiusTopLeft=4, cornerRadiusTopRight=4, width=22).encode(
        x=alt.X("score:O", title="Score", axis=alt.Axis(labelAngle=0)),
        y=alt.Y("cantidad:Q", title="Licitaciones", axis=alt.Axis(tickMinStep=1, format="d")),
        tooltip=[alt.Tooltip("score:O", title="Score"), alt.Tooltip("cantidad:Q", title="Licitaciones")],
    ).properties(height=220), t)


def grafico_calibracion(filas, t):
    df = pd.DataFrame(filas)
    df["etiqueta"] = df.apply(lambda r: f"{int(r['pct_si'])} % · {int(r['n'])} eval." if r["n"] else "sin datos", axis=1)
    df["y_etiqueta"] = df["pct_si"].fillna(0)
    tramos = [t_[0] for t_ in TRAMOS_SCORE]
    base = alt.Chart(df).encode(
        # Todos los tramos en el eje, aunque alguno no tenga evaluaciones
        x=alt.X("tramo:O", title="Score de la IA", sort=tramos, scale=alt.Scale(domain=tramos), axis=alt.Axis(labelAngle=0)),
        y=alt.Y("pct_si:Q", title="% en que postularías", scale=alt.Scale(domain=[0, 100])),
        tooltip=[alt.Tooltip("tramo:O", title="Score"), alt.Tooltip("n:Q", title="Evaluadas"),
                 alt.Tooltip("si:Q", title="Sí"), alt.Tooltip("tal_vez:Q", title="Tal vez"), alt.Tooltip("no:Q", title="No")],
    )
    barras = base.mark_bar(color=t["serie"], cornerRadiusTopLeft=4, cornerRadiusTopRight=4, width=36)
    textos = base.mark_text(dy=-8, color=t["texto2"], fontSize=12).encode(y="y_etiqueta:Q", text="etiqueta:N")
    return _config((barras + textos).properties(height=240), t)


# ===================================================================
# RENDER
# ===================================================================

def _tema():
    """Tokens de los gráficos (la UI usa un único tema oscuro)."""
    return TEMAS["dark"]


def _tabla(df, columnas):
    with st.expander("Ver datos"):
        st.dataframe(pd.DataFrame(df).rename(columns=columnas)[list(columnas.values())], hide_index=True, width="stretch")


def _titulo(texto, subtitulo=None):
    st.markdown(f"##### {texto}")
    if subtitulo:
        st.caption(subtitulo)


def _vacio(texto):
    st.html(f'<div class="l-nota" style="padding:.6rem 0">{texto}</div>')


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def render(db, ahora=None):
    """Dibujar la página Panorama: cada gráfico en su tarjeta."""
    t = _tema()
    todas = db.obtener_licitaciones()
    ejecuciones = db.obtener_ejecuciones()

    # Filtro único que acota todo lo que mira hacia atrás (el calendario mira hacia adelante)
    # Radio con aspecto de "píldoras" (CSS en web/estilos.py: key "pill_*")
    etiqueta_periodo = st.radio("Periodo", list(PERIODOS), index=1, key="pill_periodo", horizontal=True,
                                label_visibility="collapsed") or "Últimos 30 días"
    dias = PERIODOS[etiqueta_periodo]
    periodo = en_periodo(todas, dias, ahora)

    # --- Embudo ---
    with st.container(border=True, key="lcard_pan_1"):
        _titulo("De lo publicado a tus oportunidades",
                "Cuántas licitaciones pasan cada etapa: publicadas, coinciden con tu perfil, analizadas y favoritas.")
        embudo = datos_embudo(todas, ejecuciones, dias, ahora)
        if not embudo:
            _vacio("Aún no hay sincronizaciones en este periodo. Este gráfico se completa a partir de la próxima.")
        else:
            st.altair_chart(grafico_embudo(embudo, t), width="stretch")
            _tabla(embudo, {"etapa": "Etapa", "cantidad": "Licitaciones"})

    # --- Calendario ---
    with st.container(border=True, key="lcard_pan_2"):
        cal = datos_calendario(todas, ahora)
        _titulo("Próximos cierres",
                f"Tus oportunidades abiertas hasta su fecha de cierre ({_plural(len(cal), 'licitación', 'licitaciones')}). "
                "El color indica el score.")
        if not cal:
            _vacio("No tienes oportunidades abiertas en este momento.")
        else:
            st.altair_chart(grafico_calendario(cal, t, ahora), width="stretch")
            _tabla(cal, {"titulo": "Licitación", "organismo": "Organismo", "score": "Score", "dias": "Días al cierre", "id_externo": "Código"})

    c1, c2 = st.columns([3, 2])
    # --- Oportunidad vs. riesgo ---
    with c1, st.container(border=True, height="stretch", key="lcard_pan_3"):
        riesgo = datos_riesgo(periodo)
        _titulo("Score vs. reclamos de pago",
                f"Cada punto es una licitación ({len(riesgo)}). Considera que los organismos que compran mucho "
                "suelen acumular más reclamos.")
        if not riesgo:
            _vacio("Sin licitaciones con información de pagos en este periodo.")
        else:
            st.altair_chart(grafico_riesgo(riesgo, t), width="stretch")
            _tabla(riesgo, {"titulo": "Licitación", "organismo": "Organismo", "score": "Score", "reclamos": "Reclamos de pago"})

    # --- Distribución de scores ---
    with c2, st.container(border=True, height="stretch", key="lcard_pan_4"):
        hist = datos_histograma(periodo)
        n_hist = sum(f["cantidad"] for f in hist)
        _titulo("Distribución de scores", f"Cuántas licitaciones obtuvieron cada score ({n_hist} en total).")
        if not n_hist:
            _vacio("Sin análisis en este periodo.")
        else:
            st.altair_chart(grafico_histograma(hist, t), width="stretch")
            _tabla(hist, {"score": "Score", "cantidad": "Licitaciones"})

    # --- Calibración ---
    with st.container(border=True, key="lcard_pan_5"):
        cal_data = datos_calibracion(periodo)
        _titulo("¿Qué tan acertada es la IA?", "Se calcula con tus evaluaciones de cada análisis.")
        if cal_data["total_eval_score"]:
            from web.vistas import html_kpi
            r, n = cal_data["eval_score"], cal_data["total_eval_score"]
            pie = f"Según {_plural(n, 'evaluación', 'evaluaciones')}"
            kpis = [("Score acertado", r['acertado'], "check_circle", "alto"),
                    ("Score muy alto", r['muy_alto'], "arrow_upward", "medio"),
                    ("Score muy bajo", r['muy_bajo'], "arrow_downward", "bajo")]
            for col, (etiqueta, valor, icono, tinte) in zip(st.columns(3), kpis):
                col.html(html_kpi(etiqueta, f"{round(100 * valor / n)} %", icono, tinte, pie))
            st.write("")
        if cal_data["total"] < MIN_EVALUACIONES_CALIBRACION:
            st.info(f"Evalúa al menos {MIN_EVALUACIONES_CALIBRACION} análisis para ver cómo se relaciona el score con tus decisiones "
                    f"(llevas {cal_data['total']}). Puedes hacerlo desde «Análisis y evaluación» en cada licitación.",
                    icon=":material/rate_review:")
        else:
            st.caption("Porcentaje de licitaciones a las que postularías, según su score. "
                       "Si la IA acierta, debería subir a medida que sube el score.")
            st.altair_chart(grafico_calibracion(cal_data["tramos"], t), width="stretch")
            _tabla(cal_data["tramos"], {"tramo": "Score", "n": "Evaluadas", "si": "Sí", "tal_vez": "Tal vez", "no": "No", "pct_si": "% sí"})
