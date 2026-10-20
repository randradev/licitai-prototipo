# LicitAI Prototype --- Plan de estabilización para demo y portafolio

## 1. Contexto

LicitAI es un prototipo que descubre licitaciones de Mercado Público,
extrae información, utiliza Gemini para evaluar su relevancia según un
perfil empresarial y presenta los resultados en una interfaz Streamlit.

El objetivo de esta tarea es **estabilizar la versión actual de `main`
para que sea fiable, coherente y presentable como prototipo en un
portafolio profesional**.

Esta tarea NO consiste en desarrollar LicitAI V2 ni en migrar la
arquitectura. La V2 se planificará por separado, probablemente en un
repositorio nuevo.

## 2. Objetivo principal

Dejar el prototipo actual en un estado en que pueda:

-   Instalarse y ejecutarse siguiendo instrucciones claras.
-   Descubrir y procesar licitaciones sin perder registros ni dejar
    estados inconsistentes.
-   Generar y guardar análisis de IA con datos validados.
-   Mostrar resultados coherentes en el dashboard.
-   Gestionar errores recuperables sin bloquear toda la aplicación.
-   Servir como base para recopilar una muestra de análisis reales que
    más adelante se utilizará en una demo pública de solo lectura.
-   Documentar con honestidad sus capacidades, limitaciones y
    requisitos.

**Importante:** por ahora la aplicación debe seguir pudiendo recopilar y
analizar licitaciones. No desactives el scraping, Gemini ni las
funciones de análisis en esta fase. La conversión a una demo pública de
solo lectura y la preparación de datos precargados quedan explícitamente
para una tarea posterior.

## 3. Forma de trabajo requerida

### Fase 1 --- Auditoría completa antes de modificar código

Inspecciona el repositorio actual de punta a punta. No te limites a los
problemas enumerados en este documento.

Revisa, como mínimo:

-   `main.py` y el flujo completo de orquestación.
-   Todos los módulos de `core/`.
-   `web/app.py` y cada vista, botón, filtro y formulario.
-   Esquema SQLite, inicialización, migraciones o cambios de esquema y
    operaciones de lectura/escritura.
-   Scraping, llamadas HTTP, Selenium, extracción y normalización de
    datos.
-   Integración con Gemini, prompts, parsing y validación de respuestas.
-   `requirements.txt`, configuración por variables de entorno y
    secretos.
-   README e instrucciones de instalación y ejecución.
-   Manejo de errores, logging, seguridad básica y pruebas existentes.

Traza los flujos de extremo a extremo: descubrimiento → filtrado →
persistencia → extracción → análisis IA → actualización de estado →
visualización en la interfaz.

No afirmes que una funcionalidad funciona solo porque exista un botón o
una función. Sigue el flujo hasta su efecto real. Distingue entre
problemas confirmados por código, riesgos potenciales y comportamientos
que requieren ejecución para confirmarse.

### Fase 2 --- Informe de hallazgos y plan de estabilización

**Antes de implementar cambios**, entrega un plan priorizado. No
empieces una refactorización amplia sin presentar primero el
diagnóstico.

Para cada hallazgo, indica:

-   Prioridad: P0 (bloqueante), P1 (importante), P2 (mejora posterior).
-   Archivo y función o ubicación afectada.
-   Comportamiento actual y por qué es un problema.
-   Impacto en la fiabilidad, los datos, la experiencia de usuario o la
    demo.
-   Cambio propuesto.
-   Cómo se verificará la corrección.
-   Dependencias con otras correcciones y estimación relativa de
    esfuerzo (S/M/L).

Agrupa los hallazgos en: 1. Bugs funcionales. 2. Integridad y ciclo de
vida de los datos. 3. Scraping, red y dependencias externas. 4.
Integración y calidad de la IA. 5. Interfaz y experiencia de uso. 6.
Configuración, seguridad y dependencias. 7. Documentación y pruebas.

Añade cualquier problema nuevo que descubras, aunque no esté mencionado
en este documento. Si una observación previa no se confirma, indícalo en
vez de asumir que es un bug.

Al final, propone el alcance mínimo que consideras suficiente para
declarar el prototipo estable. Separa claramente lo imprescindible de
las mejoras que pueden esperar a la V2.

### Fase 3 --- Implementación incremental

Tras presentar el plan, espera mi aprobación antes de realizar cambios
sustanciales. Una vez aprobado:

-   Corrige primero los P0 y P1 que afecten la fiabilidad del prototipo.
-   Trabaja en cambios pequeños y coherentes.
-   Evita reescribir módulos completos cuando una corrección localizada
    sea suficiente.
-   No cambies de framework ni introduzcas servicios nuevos sin
    justificarlo y obtener aprobación.
-   Conserva las funciones que ya son útiles y están funcionando.
-   Si un cambio de esquema SQLite es necesario, hazlo de forma segura y
    compatible con las bases existentes. No borres datos del usuario ni
    reinicialices la base sin autorización.
-   Actualiza la documentación y las pruebas junto con el código
    afectado.
-   Si no puedes verificar algo por falta de credenciales, acceso al
    portal o entorno adecuado, indícalo explícitamente y proporciona una
    prueba reproducible para que yo pueda ejecutarla.

## 4. Lista inicial de riesgos a verificar

Esta lista es un punto de partida, no una auditoría cerrada. Confirma
cada punto inspeccionando el código y añade otros que encuentres.

### P1 --- Ciclo de vida de las licitaciones

-   Comprobar si se registran todas las licitaciones descubiertas antes
    de procesar solo un máximo por ejecución.
-   Verificar si las licitaciones `pendiente` o con extracción/análisis
    fallido pueden recuperarse en ejecuciones posteriores.
-   Revisar si los registros existentes se excluyen del descubrimiento
    aunque sigan pendientes.
-   Asegurar que cada estado tenga una semántica clara y que los errores
    no dejen registros bloqueados indefinidamente.
-   Definir reintentos seguros y evitar duplicados.
-   Verificar que los mensajes de éxito de la interfaz reflejen lo que
    realmente ocurrió.

### P1 --- Fechas

-   Verificar el formato en que se guardan las fechas y cómo se ordenan
    en SQLite y en Streamlit.
-   Garantizar el orden cronológico real.
-   No sustituir una fecha desconocida o inválida por la fecha actual.
-   Mostrar un estado claro cuando la fecha no esté disponible.

### P1 --- Indicador de pago y afirmaciones generadas por IA

-   Auditar cualquier condición que deduzca riesgo a partir de búsquedas
    simples de caracteres o subcadenas.
-   Verificar de dónde provienen los datos de reclamos o comportamiento
    de pago y si realmente se extraen de una fuente fiable.
-   No presentar como verificados datos inferidos por el modelo.
-   Si no hay evidencia suficiente, mostrar "Sin datos verificados" o
    una etiqueta equivalente.
-   Diferenciar información de la fuente, inferencias de IA y ausencia
    de información.

### P1 --- Notas, favoritas y checklists

-   Verificar si las notas y los checklists se persisten o solo viven
    durante la sesión de Streamlit.
-   Comparar el comportamiento real con lo que promete el README.
-   Recomendar persistencia sencilla si aporta valor al prototipo; si
    no, proponer retirar o etiquetar la función antes que dejar una
    interacción engañosa.
-   No eliminar funcionalidades sin explicar la decisión en el plan.

### P1 --- Acción "Re-evaluar"

-   Seguir el evento del botón hasta el resultado real.
-   Confirmar si ejecuta un nuevo análisis de Gemini o solo modifica el
    estado.
-   Corregir la implementación o cambiar el nombre/retirar la acción si
    no hace lo que promete.
-   Manejar fallos sin perder el análisis anterior.

### P1 --- Perfil ausente y filtros

-   Verificar el comportamiento cuando no existe un perfil empresarial
    guardado o está incompleto.
-   Evitar errores por acceder a campos de un perfil `None`.
-   Comprobar si las palabras clave positivas, las negativas y las
    regiones realmente afectan al filtrado.
-   Si una función no está implementada, corregirla o documentar su
    limitación de forma visible.
-   Definir el comportamiento cuando no hay palabras clave configuradas.

### P1 --- Respuestas de Gemini

-   Verificar el formato real de las respuestas, el parsing de JSON y
    los errores de la API.
-   Validar campos obligatorios, tipos, rangos del score y estructuras
    de listas antes de persistir.
-   Unificar la escala del score entre prompt, esquema, base de datos,
    umbrales y UI.
-   Manejar respuestas vacías, truncadas, malformadas, límites de cuota
    y fallos de red.
-   Evitar que una respuesta inválida rompa la interfaz.
-   Revisar el tratamiento del texto de las licitaciones como entrada no
    confiable.
-   Evaluar si hay límites de longitud razonables para el contenido
    enviado al modelo.

### P1/P2 --- Selenium, red y ejecución

-   Revisar creación y cierre del navegador, timeouts, esperas fijas,
    selectores frágiles e iframes.
-   Verificar si los errores de inicialización del driver están
    cubiertos.
-   Comprobar si el modo de ejecución documentado coincide con el
    comportamiento real.
-   Añadir timeouts y manejo de errores HTTP donde corresponda.
-   Evaluar el modo headless para despliegue, sin asumir que eso por sí
    solo garantiza compatibilidad con Streamlit Cloud.
-   No sustituir Selenium por otra tecnología en esta tarea salvo que la
    auditoría demuestre que es imprescindible y se apruebe el cambio.

### P2 --- Configuración y mantenibilidad

-   Verificar la codificación de `requirements.txt`, que se pueda
    instalar en un entorno limpio y que las versiones sean compatibles.
-   Identificar dependencias innecesarias, pero no eliminarlas sin
    comprobar su uso.
-   Confirmar que no existan secretos reales en el repositorio y que las
    instrucciones para variables de entorno sean correctas.
-   Revisar los `except` amplios o vacíos y añadir logging útil sin
    exponer secretos.
-   Comprobar que la inicialización de SQLite sea reproducible y no
    dependa de archivos locales accidentales.

### P1/P2 --- Interfaz y README

-   Revisar cada botón y formulario para confirmar que su acción
    funciona y persiste cuando corresponde.
-   Evitar mensajes de "éxito" cuando no se obtuvieron resultados o se
    produjeron fallos parciales.
-   Comprobar que las fechas, los scores, los estados y las etiquetas
    sean consistentes.
-   Corregir enlaces, nombres de usuario de ejemplo, instrucciones de
    instalación, variables de entorno y afirmaciones de despliegue.
-   Explicar claramente qué hace el prototipo, qué no hace y qué
    limitaciones tiene.
-   Mantener el alcance y el lenguaje adecuados para un prototipo, sin
    presentarlo como un producto de producción.

## 5. Pruebas y criterios de aceptación

La estabilización no se considera terminada solo porque la aplicación
arranque.

Como mínimo, prepara o ejecuta pruebas para:

-   Inicialización de la base de datos y operaciones CRUD principales.
-   Orden cronológico de fechas válidas y tratamiento de fechas
    inválidas.
-   Filtrado con palabras positivas, negativas, regiones y perfil vacío.
-   Descubrimiento de más licitaciones que el límite por ejecución.
-   Recuperación de pendientes y errores sin duplicar registros.
-   Respuestas de Gemini válidas, vacías y malformadas.
-   Score dentro del rango definido y consistente en toda la aplicación.
-   Ausencia de perfil guardado.
-   Persistencia de notas/checklists, si se mantienen.
-   Funcionamiento real de cada botón principal.
-   Manejo de fallos HTTP, Selenium y Gemini.
-   Inicio desde un entorno limpio siguiendo el README.

Si las pruebas de integración dependen del portal de Mercado Público o
de credenciales, separa las pruebas unitarias deterministas de las
pruebas externas. No hagas llamadas costosas o destructivas sin
necesidad. No inventes resultados de pruebas: informa exactamente cuáles
se ejecutaron, cuáles pasaron y cuáles quedaron pendientes.

## 6. Restricciones de alcance

Durante esta tarea:

-   No desarrollar la V2.
-   No migrar a FastAPI, React/Next.js o PostgreSQL.
-   No implementar procesamiento de bases PDF, RAG, Celery ni
    multitenencia.
-   No diseñar aún la demo pública de solo lectura.
-   No desactivar la recopilación ni el análisis real: necesito que el
    prototipo siga funcionando para recopilar y revisar análisis que se
    usarán posteriormente en el demo.
-   No reescribir el historial de Git, borrar la base de datos ni
    eliminar datos.
-   No afirmar que el despliegue funciona sin haberlo comprobado.
-   No añadir complejidad solo para utilizar tecnologías más modernas.

Puedes proponer estas ideas como recomendaciones separadas para la V2,
pero no implementarlas en esta tarea.

## 7. Entregables

### Antes de implementar

Entrega un informe con:

1.  Resumen ejecutivo de la salud del prototipo.
2.  Lista de hallazgos confirmados y riesgos por verificar.
3.  Priorización P0/P1/P2.
4.  Plan de trabajo por etapas.
5.  Alcance mínimo de estabilización.
6.  Estimación relativa de esfuerzo y principales incertidumbres.
7.  Pruebas que se ejecutarán para validar los cambios.
8.  Decisiones que necesitan mi aprobación.

### Después de implementar

Entrega:

1.  Resumen de cambios realizados, por archivo.
2.  Problemas corregidos y razón de cada solución.
3.  Pruebas ejecutadas con resultados reales.
4.  Pruebas pendientes y por qué no pudieron ejecutarse.
5.  Instrucciones para instalar, configurar y ejecutar desde cero.
6.  Limitaciones conocidas que permanecen.
7.  Checklist de preparación para recopilar análisis y, más adelante,
    preparar la demo pública.
8.  Recomendaciones separadas para LicitAI V2.

## 8. Definición de "terminado"

Consideraremos estabilizado el prototipo cuando:

-   El flujo principal de descubrimiento, análisis, persistencia y
    visualización sea coherente.
-   No haya bugs P0/P1 conocidos sin resolver que invaliden los
    resultados o la experiencia principal.
-   Los errores recuperables no dejen licitaciones en estados
    irrecuperables.
-   Los datos y puntuaciones se presenten con significado consistente y
    sin afirmaciones engañosas.
-   Las funciones expuestas en la interfaz hagan lo que indican o se
    hayan retirado/etiquetado correctamente.
-   Las instrucciones permitan instalar y ejecutar el proyecto desde un
    entorno limpio.
-   Exista evidencia de pruebas suficiente y se documenten las
    limitaciones no verificadas.

## Instrucción final

Empieza por la auditoría completa y el plan priorizado. **No modifiques
código todavía.** Sé proactivo: identifica problemas adicionales,
cuestiona supuestos de este documento cuando el código indique otra cosa
y recomienda la solución más sencilla que deje el prototipo estable.
Presenta el plan para aprobación antes de comenzar la implementación.
