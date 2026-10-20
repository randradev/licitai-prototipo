# 🤖 LicitAI: Radar de Licitaciones (prototipo)

LicitAI es un **prototipo** que ayuda a revisar oportunidades de **Mercado Público** (Chile). Descubre las licitaciones del día con la API oficial, las filtra por palabras clave, extrae el texto de cada ficha con Selenium y le pide a **Google Gemini** una evaluación de idoneidad según el perfil de tu empresa. Los resultados se revisan en un dashboard Streamlit.

> Es un proyecto de portafolio, no un producto de producción. Los scores, veredictos e interpretaciones los genera un modelo de IA y deben verificarse en el portal.

---

## ✅ Qué hace
* **Descubrimiento:** consulta la API de Mercado Público (licitaciones de la fecha indicada, por defecto hoy).
* **Filtrado:** conserva las licitaciones *Publicadas* y aún abiertas cuyo título contiene alguna keyword positiva y ninguna negativa (sin distinguir mayúsculas ni tildes).
* **Cola recuperable:** registra todas las licitaciones relevantes y procesa hasta `LICITAI_MAX_PROCESAR` por ejecución. Las restantes y las que fallan se retoman en las siguientes ejecuciones (hasta `LICITAI_MAX_INTENTOS` intentos). Después pasan a *error*, visibles en la pestaña **Pendientes / Errores**, con un botón **Reintentar**.
* **Datos de la fuente:** el título, el organismo, la fecha de publicación, la región y el **número de reclamos por pago fuera de plazo** se toman literalmente del texto de la ficha. Si un dato no aparece se muestra "No disponible"; nunca se inventa.
* **Análisis IA:** Gemini devuelve un JSON con un score del 1 al 10, un veredicto, puntos críticos y riesgos. La respuesta se valida antes de guardarse. Si un re-análisis falla, se conserva el análisis anterior.
* **Gestión:** favoritas, archivadas, re-análisis manual con IA y notas y checklist por favorita guardados en SQLite. Búsqueda y filtros por score, región y cierre, con el tiempo restante para el cierre siempre visible.
* **Trazabilidad:** cada análisis guarda el modelo, la versión del prompt (`PROMPT_VERSION` en `core/ai_analyst.py`) y su fecha, para comparar análisis hechos con configuraciones distintas.
* **Tu evaluación:** en cada análisis puedes indicar si el score fue acertado y si postularías. Esas respuestas forman un set de datos con criterio humano para medir la calidad del score.
* **📊 Panorama:** embudo de filtrado (listado → relevantes → analizadas → favoritas, a partir del registro de cada sincronización), calendario de cierres, oportunidad vs. reclamos de pago, distribución de scores y calibración del score contra tus evaluaciones (se dibuja desde 10 evaluaciones). Cada gráfico muestra su tamaño de muestra y tiene una vista de tabla.
* **Exportación:** JSON (con la ficha completa opcional) o CSV, separando los datos de la fuente, el análisis de IA y tu evaluación. Las notas internas no se exportan.

## ⚠️ Qué no hace / limitaciones
* Solo consulta **una fecha por ejecución**: si no se ejecuta un día, ese listado no se revisa (puedes usar `python main.py --fecha DDMMAAAA`).
* El filtro mira **solo el título** del listado. El campo de regiones del perfil no se usa: el listado de la API no trae región. La región se muestra después de la extracción.
* No lee las bases en PDF; analiza solo el texto visible de la ficha (truncado a `LICITAI_IA_MAX_CHARS`).
* Depende de la estructura actual del portal (selectores de Selenium) y del SDK `google-generativeai`, que Google ya no mantiene (genera un `FutureWarning`).
* La sincronización corre dentro de la petición de Streamlit y puede tardar varios minutos. Lo que hagas en la página mientras tanto se aplica al terminar. Solo puede haber una sincronización activa por base de datos: un archivo `<bd>.lock` evita que dos pestañas, o la UI y una tarea programada, procesen lo mismo a la vez.
* Aunque Gemini se usa con `temperature=0`, el score de una misma ficha puede variar ligeramente entre ejecuciones.
* Single-tenant (un único perfil). No se ha verificado su despliegue en Streamlit Cloud ni en otros servicios.

---

## 🛠️ Stack
* Python **3.11+**, Streamlit, SQLite3, Selenium (Chrome, modo headless por defecto), Google Gemini (`google-generativeai`, modelo configurable con `GEMINI_MODEL`).

## 🏗️ Estructura
| Archivo | Responsabilidad |
|---|---|
| `main.py` | Orquestador del pipeline (CLI y UI). Devuelve un resumen de lo ocurrido. |
| `core/scraper.py` | API de Mercado Público, filtro y extracción con Selenium. |
| `core/ai_analyst.py` | Prompt, llamada a Gemini y validación de la respuesta. |
| `core/database_mgr.py` | Persistencia SQLite, ciclo de vida de estados y migración de esquema. |
| `core/parsing.py` | Funciones puras: keywords, fechas, metadatos de la ficha y validación del JSON. |
| `core/config.py` | Variables de entorno y constantes (umbrales del score, límites). |
| `core/migrar_datos.py` | Corrección única de los datos guardados por versiones anteriores. |
| `core/exportar.py` | Exportación a JSON y CSV independiente del esquema SQLite. |
| `web/app.py` | Punto de entrada del dashboard: tema, estilos y navegación superior. |
| `web/paginas/*.py` | Una sección por archivo (Oportunidades, Favoritas, Archivo, Cola, Panorama, Perfil). |
| `web/vistas.py` | Contenido de cada sección: tarjetas, filtros, formularios y helpers de presentación. |
| `web/estilos.py` | CSS de tarjetas, insignias y chips, con colores para tema claro y oscuro. |
| `web/panorama.py` | Visualizaciones: preparación de datos y gráficos Altair. |
| `.streamlit/config.toml` | Tema de Streamlit: tipografía Inter, colores y bordes. Si no hay internet, se usa la fuente del sistema. |

**Estados de una licitación:** `pendiente` (registrada) → `extraido` (texto de la ficha guardado) → `analizado` → `favorita` / `archivada`. `error`: agotó los reintentos o cerró antes de procesarse.

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

1. Completa el **Perfil de Negocio** en la barra lateral (keywords positivas separadas por comas, keywords negativas y bio) y guarda.
2. Pulsa **🚀 Buscar y Analizar Hoy**. Al terminar se muestra un resumen con las licitaciones analizadas, las fallidas y las que siguen en cola.

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

## 👤 Autor
randradev — desarrollado con enfoque en Ingeniería de Software y Automatización.
