# LicitAI — Especificación de scoring de idoneidad (v1)

## 1. Objetivo

Definir un criterio uniforme, explicable y evaluable para estimar la **idoneidad de una licitación para una empresa determinada**. El score representa compatibilidad con el perfil empresarial; **no representa la probabilidad de ganar la licitación** ni una probabilidad de éxito comercial.

Esta rúbrica es una hipótesis inicial de negocio. Sus pesos y umbrales deben validarse con evaluaciones humanas; no se consideran científicamente calibrados.

## 2. Principios obligatorios

1. Evidencia antes que puntuación: no asignar una nota alta solo porque el modelo no haya encontrado problemas.
2. Separar hechos encontrados en la fuente, inferencias del modelo e información desconocida.
3. No ocultar incertidumbre: la falta de datos no equivale a compatibilidad ni incompatibilidad.
4. Los requisitos excluyentes prevalecen: una incompatibilidad obligatoria demostrada no puede compensarse con otros puntos.
5. Riesgo de pago y urgencia son indicadores separados; no forman parte del score de idoneidad.
6. Python calcula el total a partir de las notas por criterio; no confiar en un total calculado libremente por el LLM.
7. Versionar cada rúbrica y prompt utilizado.
8. Conservar los análisis históricos. No recalcularlos silenciosamente; cualquier reevaluación debe ser explícita.

## 3. Criterios y ponderaciones

Gemini asignará una nota entera entre 0 y 5 por criterio y proporcionará evidencia y explicación.

| Criterio | Peso | Qué evalúa |
|---|---:|---|
| Compatibilidad comercial | 35% | Correspondencia entre el objeto de la licitación y los productos/servicios que ofrece la empresa. |
| Requisitos obligatorios | 25% | Compatibilidad con requisitos técnicos, legales, certificaciones, experiencia y otras condiciones obligatorias. |
| Capacidad de cumplimiento | 20% | Capacidad para responder al volumen, cantidades, especificaciones, plazos y condiciones operativas. |
| Viabilidad geográfica y logística | 10% | Capacidad para entregar o prestar el servicio en la ubicación requerida. |
| Viabilidad económica y contractual | 10% | Compatibilidad aparente con presupuesto, costes y condiciones contractuales disponibles. |

Los pesos suman 100%. Son una propuesta inicial y deben revisarse a partir de evaluaciones humanas.

### Escala común de cada criterio

| Nota | Interpretación |
|---:|---|
| 0 | Incompatible o incumplimiento demostrado. |
| 1 | Compatibilidad muy baja. |
| 2 | Compatibilidad parcial, con brechas importantes. |
| 3 | Compatibilidad razonable, con condiciones pendientes. |
| 4 | Buena compatibilidad, con brechas menores. |
| 5 | Compatibilidad completa, respaldada por evidencia suficiente. |

Una nota 5 no significa simplemente “no se encontraron problemas”; debe existir evidencia suficiente.

## 4. Cálculo del score

Cuando los cinco criterios están evaluados y hay evidencia suficiente:

`score = 35*(r1/5) + 25*(r2/5) + 20*(r3/5) + 10*(r4/5) + 10*(r5/5)`

El resultado va de 0 a 100. Definir una regla consistente de redondeo en el código y documentarla.

Ejemplo: notas `[5, 4, 4, 3, 3]` producen `84/100`.

El LLM no es la fuente de verdad del total: devuelve notas por criterio; Python valida y calcula.

## 5. Estados especiales y reglas

### Requisito excluyente incumplido — `no_elegible`

Si hay evidencia clara de que la empresa no cumple un requisito obligatorio, marcar `no_elegible` y guardar el requisito y la evidencia.

- El score no puede compensar ese incumplimiento.
- No usar este estado si solo falta información.
- Distinguir entre incumplimiento confirmado y requisito no verificable.

### Evidencia insuficiente — `evaluacion_insuficiente`

No emitir recomendación definitiva cuando falte información esencial del perfil, no se pueda determinar el objeto principal de la licitación, falten datos para evaluar compatibilidad comercial/requisitos obligatorios o la respuesta de IA sea inválida.

Mostrar el motivo y los datos faltantes. No inventar notas para completar campos.

### Datos incompletos en criterios no esenciales

Si falta información en un criterio no esencial, se puede calcular un score provisional normalizado, solo si los criterios esenciales están suficientemente respaldados:

`score_provisional = Σ(peso_i × nota_i / 5) / Σ(peso_i_evaluado) × 100`

Acompañar el resultado de estado `provisional`, cobertura de evidencia, criterios pendientes y una advertencia de que no es directamente comparable con un score definitivo. Si el esquema actual no puede representarlo, proponer el cambio mínimo de esquema y UI.

### Riesgo de pago separado

No incluirlo en los 100 puntos. Mostrarlo como campo independiente con fuente, fecha y estado de evidencia cuando estén disponibles. Si no hay fuente verificable, mostrar `Sin datos verificados`; no inferir bajo riesgo por ausencia de reclamos en el texto.

### Urgencia separada

Mostrar fecha de cierre y días restantes por separado. La cercanía del cierre no reduce por sí misma la idoneidad comercial.

## 6. Rangos de interpretación iniciales

| Score | Etiqueta | Interpretación |
|---:|---|---|
| 90–100 | Idoneidad excelente | Ajuste muy alto respaldado por evidencia suficiente. |
| 75–89 | Buena oportunidad | Buen encaje; revisar condiciones pendientes. |
| 60–74 | Oportunidad potencial | Puede ser relevante, pero existen brechas por evaluar. |
| 40–59 | Encaje limitado | Diferencias importantes respecto al perfil. |
| 0–39 | Baja idoneidad | Poca compatibilidad con la oferta empresarial. |

Los umbrales son iniciales y no están validados. No equivalen a probabilidades de adjudicación ni éxito comercial. `no_elegible` y `evaluacion_insuficiente` prevalecen sobre las etiquetas numéricas. Los scores provisionales deben identificarse como tales.

## 7. Contrato esperado de salida de IA

Inspeccionar primero la estructura actual y proponer un esquema compatible con el proyecto. La salida conceptual debe incluir:
- Nota de 0 a 5 para cada criterio.
- Evidencia concreta y explicación breve para cada nota.
- Estado de evidencia: suficiente, parcial o ausente.
- Requisitos obligatorios identificados.
- Requisitos excluyentes incumplidos, con evidencia y estado de verificación.
- Incertidumbres y datos faltantes.
- Separación entre hechos de la fuente e inferencias.
- Riesgos comerciales como información separada del score.
- Versión de rúbrica y prompt utilizada.

El score total, la cobertura y los estados derivados deben calcularse/validarse en código.

## 8. Validación y pruebas requeridas

Añadir pruebas deterministas para:
1. Score mínimo y máximo.
2. Cálculo `[5,4,4,3,3] = 84`.
3. Rechazo de notas fuera de 0–5, tipos inválidos y criterios ausentes.
4. Incumplimiento confirmado de requisito excluyente.
5. Falta de evidencia crítica y estado `evaluacion_insuficiente`.
6. Cálculo provisional y cobertura.
7. Score provisional no confundido con definitivo.
8. Riesgo de pago desconocido no mostrado como bajo.
9. Fecha de cierre tratada fuera del score.
10. Consistencia de etiquetas en los límites de rango.
11. Persistencia de versión de rúbrica/prompt.
12. Compatibilidad con análisis históricos.
13. Respuestas malformadas del LLM.
14. Renderizado correcto de estados en Streamlit.

Separar pruebas unitarias de llamadas reales a Gemini. No consumir API en pruebas unitarias deterministas ni afirmar que las pruebas pasaron si no se ejecutaron.

## 9. Evaluación humana posterior

Preparar un flujo para revisar una muestra de licitaciones y registrar:
- Score y desglose generados.
- Decisión humana: adecuada, parcialmente adecuada o inadecuada.
- Si la explicación cita evidencia correcta.
- Requisitos excluyentes omitidos.
- Información insuficiente detectada.
- Motivo de desacuerdo y observaciones.

Comenzar con una muestra pequeña y representativa. No afirmar precisión, ahorro de tiempo ni mejora comercial sin mediciones adecuadas.

## 10. Alcance y restricciones

- Aplicar al prototipo actual de Streamlit.
- No migrar de framework ni desarrollar la V2.
- No reescribir módulos completos si basta una modificación localizada.
- No borrar ni sobrescribir análisis históricos.
- Antes de cambiar SQLite, explicar la migración y cómo se conservarán los datos.
- Inspeccionar cómo se usa actualmente `score_ia` en backend y todas las vistas.
- Presentar primero diagnóstico y plan priorizado; esperar aprobación antes de cambios sustanciales.
- Identificar conflictos entre esta especificación y el código; proponer la solución mínima.
- Si una regla es ambigua o incompatible con el código actual, señalarlo en lugar de inventar una interpretación.

## 11. Criterios de aceptación

La implementación estará lista cuando:
- Criterios, pesos y escala estén definidos en un lugar versionado.
- El total se calcule en código.
- Las reglas de exclusión y evidencia insuficiente prevalezcan sobre la etiqueta numérica.
- La UI distinga score definitivo, provisional, no elegible y evaluación insuficiente.
- Riesgo de pago y urgencia estén separados de la idoneidad.
- Se conserven datos históricos y los análisis nuevos identifiquen la versión de rúbrica.
- Pasen las pruebas deterministas relevantes y se documenten los resultados reales.
- Las limitaciones de validación humana se declaren con honestidad.
