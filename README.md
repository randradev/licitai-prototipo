# 🤖 LicitAI: Radar de Licitaciones (prototipo)

LicitAI es un **prototipo** que ayuda a revisar oportunidades de **Mercado Público** (Chile). Descubre las licitaciones del día con la API oficial, las filtra por palabras clave, extrae el texto de cada ficha con Selenium y le pide a **Google Gemini** una evaluación de idoneidad según el perfil de tu empresa. Los resultados se revisan en un dashboard Streamlit.

> Es un proyecto de portafolio, no un producto de producción. Los scores, veredictos e interpretaciones los genera un modelo de IA y deben verificarse en el portal.

---

## ✅ Qué hace
* **Descubrimiento:** consulta la API de Mercado Público (licitaciones de la fecha indicada, por defecto hoy).
* **Filtrado:** conserva las licitaciones *Publicadas* y aún abiertas cuyo título contiene alguna palabra clave de interés y ninguna palabra a excluir (sin distinguir mayúsculas ni tildes).
* **Cola recuperable:** registra todas las licitaciones relevantes y procesa hasta `LICITAI_MAX_PROCESAR` por ejecución. Las restantes y las que fallan se retoman en las siguientes sincronizaciones (hasta `LICITAI_MAX_INTENTOS` intentos). Las que no pudieron completarse quedan visibles en la página **En proceso**, con un botón **Reintentar**.
* **Datos de la fuente:** el título, el organismo, la fecha de publicación, la región y el **número de reclamos por pagos atrasados** se toman literalmente del texto de la ficha. Si un dato no aparece se muestra "No disponible"; nunca se inventa.
* **Análisis IA:** Gemini (con `temperature=0`) devuelve un JSON con un score del 1 al 10, un veredicto, puntos críticos y riesgos. La respuesta se valida antes de guardarse. Si un nuevo análisis falla, se conserva el anterior.
* **Trazabilidad:** cada análisis guarda el modelo, la versión del prompt (`PROMPT_VERSION` en `core/ai_analyst.py`), la versión del perfil y su fecha. En la interfaz se ve como «Analizado el …», con los detalles técnicos en un desplegable.
* **Tu evaluación:** en cada análisis puedes indicar si el score fue acertado y si postularías. Esas respuestas forman un conjunto de datos con criterio humano para medir la calidad del score.
* **Perfil versionado:** al cambiar las palabras clave o la descripción de la empresa, los análisis existentes no cambian. Se marcan como «Analizada con un perfil anterior» y desde **Perfil** puedes actualizarlos a pedido (con confirmación, porque cada uno usa un análisis de IA) o descartar de la cola las licitaciones que ya no coinciden.
* **Exportación:** Excel (CSV) o JSON (con la ficha completa opcional), separando los datos de la fuente, el análisis de IA y tu evaluación. Las notas internas no se exportan.

### Páginas
| Página | Contenido |
|---|---|
| **Oportunidades** | Indicadores, búsqueda y filtros (score mínimo, región, orden, ocultar cerradas) y tarjetas con el score, los días al cierre, la región y los reclamos de pago. Cada tarjeta despliega el análisis y tu evaluación. |
| **Favoritas** | Detalle ampliado y preparación: checklist («Bases leídas», «Anexos preparados») y notas internas. |
| **Archivo** | Licitaciones descartadas, con opción de restaurarlas. |
| **En proceso** | Licitaciones que aún no terminan de analizarse y las que no pudieron completarse. |
| **Panorama** | «De lo publicado a tus oportunidades» (embudo), «Próximos cierres» (días restantes por licitación), score vs. reclamos de pago, distribución de scores y «¿Qué tan acertada es la IA?» (se dibuja desde 10 evaluaciones), además de la descarga de datos. |
| **Perfil** | Palabras clave de interés, palabras a excluir, descripción de la empresa y alineación de los análisis con el perfil actual. |

## ⚠️ Qué no hace / limitaciones
* Solo consulta **una fecha por ejecución**: si no se ejecuta un día, ese listado no se revisa (puedes usar `python main.py --fecha DDMMAAAA`).
* El filtro mira **solo el título** del listado. La región se muestra después de la extracción, pero no se usa para filtrar (el listado de la API no la trae).
* No lee las bases en PDF; analiza solo el texto visible de la ficha (truncado a `LICITAI_IA_MAX_CHARS`).
* El score todavía **no tiene una rúbrica explícita** (qué significa cada valor del 1 al 10) y su precisión **aún no está medida**. Ver «Estado y próximos pasos».
* Depende de la estructura actual del portal (selectores de Selenium) y del SDK `google-generativeai`, que Google ya no mantiene (genera un `FutureWarning`).
* La sincronización corre dentro de la petición de Streamlit y puede tardar varios minutos. Lo que hagas en la página mientras tanto se aplica al terminar. Solo puede haber una sincronización activa por base de datos: un archivo `<bd>.lock` evita que dos pestañas del navegador, o la UI y una tarea programada, procesen lo mismo a la vez.
* Interfaz con tema oscuro único, pensada para escritorio.
* Single-tenant (un único perfil). No se ha verificado su despliegue en Streamlit Cloud ni en otros servicios.

---

## 🛠️ Stack
* Python **3.11+**, Streamlit, SQLite3, Altair, Selenium (Chrome, modo headless por defecto), Google Gemini (`google-generativeai`, modelo configurable con `GEMINI_MODEL`).

## 🏗️ Estructura
| Archivo | Responsabilidad |
|---|---|
| `main.py` | Orquestador del pipeline (CLI y UI) y re-análisis en lote. Devuelve un resumen de lo ocurrido. |
| `core/scraper.py` | API de Mercado Público, filtro y extracción con Selenium. |
| `core/ai_analyst.py` | Prompt, llamada a Gemini y validación de la respuesta. |
| `core/database_mgr.py` | Persistencia SQLite, ciclo de vida de estados, evaluaciones, ejecuciones y migración de esquema. |
| `core/parsing.py` | Funciones puras: palabras clave, fechas, metadatos de la ficha, validación del JSON y versión del perfil. |
| `core/config.py` | Variables de entorno, constantes (umbrales del score, límites) y logging. |
| `core/migrar_datos.py` | Corrección única de los datos guardados por versiones anteriores. |
| `core/exportar.py` | Exportación a JSON y CSV independiente del esquema SQLite. |
| `web/app.py` | Punto de entrada del dashboard: tema, estilos y navegación superior. |
| `web/paginas/*.py` | Una página por archivo (Oportunidades, Favoritas, Archivo, En proceso, Panorama, Perfil). |
| `web/vistas.py` | Contenido de cada página: tarjetas, filtros, formularios, mensajes para el usuario y helpers de presentación. |
| `web/estilos.py` | CSS de la estética «premium oscuro»: tarjetas, KPIs, anillo de score, chips y retoques de los controles. |
| `web/panorama.py` | Visualizaciones: preparación de datos y gráficos Altair (paleta validada sobre el fondo oscuro). |
| `web/static/fonts/` | Tipografía Inter incluida en el proyecto (licencia OFL): la interfaz no depende de internet. |
| `.streamlit/config.toml` | Tema oscuro de Streamlit: fuente, colores, bordes y radios. |

**Estados de una licitación:** `pendiente` (registrada) → `extraido` (texto de la ficha guardado) → `analizado` → `favorita` / `archivada`. `error`: agotó los reintentos, cerró antes de procesarse o se descartó porque ya no coincide con el perfil.

---

## 🔧 Instalación

Requisitos: Python 3.11 o superior y Google Chrome instalado. El driver se descarga automáticamente la primera vez, así que hace falta conexión a internet.

```bash
git clone https://github.com/randradev/licitai-prototipo.git
cd licitai-prototipo
python -m venv venv
# Windows
venv\Scripts\activate
# Linux / macOS
source venv/bin/activate
pip install -r requirements.txt
```

### Variables de entorno
Copia `.env.example` como `.env` en la raíz y completa:

| Variable | Obligatoria | Descripción |
|---|---|---|
| `MP_TICKET` | Sí | Ticket de la API de Mercado Público. |
| `GEMINI_API_KEY` | Sí | API key de Google AI Studio. |
| `DATABASE_PATH` | No | Ruta de la BD (por defecto `data/mp_database.db`, relativa a la raíz). |
| `GEMINI_MODEL` | No | Modelo de Gemini (por defecto `gemini-3-flash-preview`). |
| `LICITAI_LOG_FILE` | No | Si se define (p. ej. `data/licitai.log`), además de la consola se escribe un log con fecha y nivel. Recomendado para tareas programadas. |
| `LICITAI_MAX_PROCESAR`, `LICITAI_MAX_INTENTOS`, `LICITAI_HEADLESS`, … | No | Ver `.env.example`. |

La base de datos se crea automáticamente al primer arranque.

## ▶️ Ejecución
**Dashboard** (desde la raíz del proyecto):
```bash
python -m streamlit run web/app.py
```
En Windows también puedes usar `run_app.bat`.

1. En la página **Perfil**, completa tus palabras clave de interés (separadas por comas), las palabras a excluir y la descripción de tu empresa, y guarda.
2. Pulsa **Sincronizar ahora** (arriba a la derecha). Al terminar verás cuántas licitaciones nuevas se analizaron y cuántas quedaron en espera.
3. Revisa las tarjetas en **Oportunidades**, marca favoritas y evalúa los análisis desde «Análisis y evaluación».

**Línea de comandos** (útil para tareas programadas):
```bash
python main.py                    # Fecha de hoy
python main.py --fecha 30092026   # Otra fecha (DDMMAAAA)
python main.py --max 2            # Límite de procesamiento de esta ejecución
```

### Actualizar una base de datos creada con versiones anteriores
Las versiones previas guardaban la *fecha de procesamiento* como fecha de publicación. Este script recalcula los datos desde el texto de las fichas ya guardado (sin scraping ni IA):
```bash
python -m core.migrar_datos            # Simulación: muestra los cambios, no modifica nada
python -m core.migrar_datos --aplicar  # Crea data/mp_database.backup-<fecha>.db y aplica
```
Las columnas nuevas del esquema se agregan solas al arrancar (solo `ADD COLUMN`; no se borran datos).

## 🧪 Pruebas
```bash
pip install -r requirements-dev.txt
python -m pytest
```
Las pruebas son deterministas: usan bases temporales y simulan la API, Selenium y Gemini, así que no consumen cuota ni tocan tu base de datos. La verificación contra los servicios reales se hace manualmente con `python main.py --max 1`.

---

## 🗺️ Estado y próximos pasos
* **Recopilación de datos en curso:** el prototipo se ejecuta a diario para acumular análisis reales y evaluaciones humanas. Las cifras de calidad del score se publicarán solo cuando la muestra lo permita, indicando siempre su tamaño.
* **Rúbrica del score (pendiente):** definir qué significa cada valor de idoneidad del 1 al 10 e incorporarlo al prompt (con una nueva `PROMPT_VERSION`).
* **Versión 2:** está prevista una evolución Full Stack (API, tareas asíncronas, frontend web y análisis de bases PDF). El stack aún no está decidido.

---

## 👤 Autor
randradev — desarrollado con enfoque en Ingeniería de Software y Automatización.
