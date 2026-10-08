---
title: FireWatch — Experience
status: approved
created: 2026-10-07
updated: 2026-10-07
sources:
  - ../../prds/prd-sistema-incendios-forestales-2026-10-07/prd.md
  - ../../prds/prd-sistema-incendios-forestales-2026-10-07/validation-report.md
  - ../../prds/prd-sistema-incendios-forestales-2026-10-07/revalidation-report.md
---

# FireWatch — Experience

## Foundation

Prototipo web adaptable, desktop-first, para explorar históricamente el peligro meteorológico de incendios en La Rioja, Argentina. La base UX de UJ-1 queda aprobada: una única superficie continua de análisis mantiene el contexto espacial y temporal seleccionado; la explicación, las fuentes, las limitaciones y la traza del MAS se consultan progresivamente desde ella, sin páginas independientes de dashboard, contexto y trazabilidad. “Continua” describe la experiencia durante el recorrido, no el almacenamiento entre sesiones. La dirección visual sigue siendo provisional y los criterios de accesibilidad deben verificarse en la implementación.

`DESIGN.md` es la referencia visual provisional; este documento define comportamiento y estructura de información. No se seleccionó un sistema de interfaz, valores de puntos de quiebre ni tecnología.

### Principios de experiencia

- FireWatch comunica **peligro meteorológico histórico de incendio**, nunca predicción, probabilidad, certeza de ocurrencia ni alerta oficial.
- Priorizar el FWI contextualizado, no una cifra aislada: hacer comprensibles la ubicación y el período seleccionados, la referencia histórica de esa ubicación y mes, la diferencia y la síntesis.
- Permitir consultar variables meteorológicas y componentes FWI sin que compitan con el resultado principal.
- Distinguir datos observados, cálculos determinísticos e interpretación del sistema tanto en la explicación como en la traza.
- Hacer inspeccionable la traza del MAS, pero secundaria al análisis ambiental. Mostrar solo intervenciones y estados que realmente ocurrieron.
- No representar valores faltantes o no disponibles como cero. “Sin detección FIRMS asociada” no significa “sin incendio”.
- No asumir cuentas, análisis guardados, historial persistente, uso compartido ni persistencia de la traza entre sesiones.
- Evitar animaciones decorativas o representaciones que sugieran actividad de agentes cuando no se haya registrado el evento correspondiente.

## Information Architecture

El MVP utiliza una superficie continua de análisis con consulta progresiva. Abrir un detalle no debe descartar el contexto espacial/temporal seleccionado ni reemplazar el análisis principal por una página independiente.

| Superficie / sección | Propósito | Prioridad de información |
|---|---|---|
| Superficie principal de análisis | Orientar al usuario, seleccionar un contexto válido, ejecutar el análisis y consultar el resultado principal. | Alta |
| Selección del contexto | Definir ubicación/sector y fecha/período dentro de la cobertura disponible. Aquí no se prescribe el mecanismo espacial. | Alta antes de ejecutar |
| Resultado principal | Presentar ubicación y período seleccionados, FWI identificado como peligro meteorológico, referencia histórica local-mensual, diferencia y síntesis breve. | Alta |
| Detalle ambiental y FWI | Mantener una tabla meteorológica con temperatura, humedad relativa, viento y precipitación, y permitir consultar FFMC, DMC, DC, ISI, BUI y FWI. En datos reales, cada valor muestra su unidad; los faltantes se indican explícitamente y nunca se representan como cero. | Media |
| Contexto histórico | Explicar la referencia histórica local-mensual y la diferencia observada para la ubicación/contexto seleccionado. | Alta en la síntesis; detalle progresivo para el respaldo |
| Evidencia FIRMS | Mostrar detecciones térmicas históricas pertinentes y su contexto de asociación, aclarando que no son confirmación y explicando límites temporales y metodológicos. | Media / condicional |
| Explicación | Separar datos observados, cálculos determinísticos y contextualización/interpretación del sistema. | Detalle progresivo |
| Fuentes y limitaciones | Mantener accesible desde el resultado la procedencia (IGN, Open-Meteo/ERA5, NASA FIRMS y método FWI), el período de estudio y las limitaciones pertinentes en lenguaje breve y claro. | Detalle progresivo |
| Traza del MAS | Inspeccionar agentes participantes reales y la secuencia general, con campos Agente / Tarea / Estado / Resultado-Evidencia. Distinguir visual y textualmente ejecución completa, parcial y error, reflejando únicamente el estado y los eventos registrados. | Secundaria, inspeccionable |

No se define una superficie separada de archivo o historial de análisis. Los niveles funcionales de la tabla son secciones/detalles de una sola experiencia; no deciden usar tres páginas, pestañas, tarjetas ni paneles.

## Voice and Tone

Usar lenguaje breve, literal y no alarmista. Indicar qué midió o calculó el sistema y qué no puede establecer. Evitar lenguaje promocional o que presente una asociación como causal.

| Preferir | Evitar |
|---|---|
| “Peligro meteorológico (FWI)” | “Probabilidad de incendio” |
| “FWI superior a la referencia histórica local de este mes” | “Riesgo alto” si no está validado y autorizado explícitamente |
| “No hay detecciones FIRMS asociadas a este contexto” | “No hubo incendios” |
| “Detección térmica FIRMS; no confirma por sí sola un incendio individual” | “Incendio confirmado” para una detección `type=0` |
| “Dato no disponible” / “No calculado”, con el motivo pertinente | Un espacio vacío o un cero que pueda leerse como valor medido |
| “Intervención registrada: {tarea}, estado {estado}” | Actividad, progreso o éxito de un agente que no se haya registrado |
| “La asociación usa el FWI de las 12:00 local del mismo día” | Texto que implique precedencia temporal para una detección anterior al mediodía |

La terminología exacta de la síntesis queda sujeta a validación UX; no introducir categorías locales de peligro.

## Component Patterns

Solo contratos de comportamiento. Las especificaciones visuales pertenecen a `DESIGN.md` una vez que se eliciten.

| Patrón | Uso | Reglas de comportamiento |
|---|---|---|
| Selección del contexto | Antes de un análisis | Mantener identificables la ubicación/sector y la fecha/período elegidos. Impedir ejecutar un contexto inválido o no disponible y explicar qué falta y por qué. El patrón específico de mapa/control queda abierto. |
| Ejecutar análisis | Contexto seleccionado válido | El usuario inicia explícitamente el análisis. Mantener el contexto mientras se procesa. Si hay eventos del MAS disponibles, no mostrar un indicador genérico como única señal de actividad. |
| Síntesis del resultado principal | Análisis completado | Priorizar FWI y su significado como peligro meteorológico, lugar/período, referencia histórica local-mensual, diferencia e interpretación breve y matizada. Nunca sugerir ocurrencia predicha. |
| Período de varios días | El período seleccionado incluye más de una fecha | Presentar y contextualizar cada fecha individualmente. No agregar FWI entre fechas; el usuario recorre los análisis diarios del período seleccionado. |
| Detalle progresivo | Contexto de un resultado | Permitir consultar variables meteorológicas, componentes FWI relevantes, evidencia FIRMS, explicación, fuentes, limitaciones y traza MAS sin perder el contexto principal. El control exacto para desplegar el detalle queda abierto. |
| Explicación | Resultado completo o parcial | Mantener separados los datos de entrada observados, los resultados determinísticos y la contextualización generada por agentes. La explicación no puede inventar valores ni reemplazar resultados determinísticos. |
| Actividad y traza MAS | Análisis en curso, completado o parcial | Durante la ejecución solo se pueden mostrar eventos realmente registrados. Las trazas completas identifican agente, tarea/responsabilidad, estado de ejecución, resultado/evidencia/referencia y secuencia general de intervenciones. Nunca inferir ni inventar eventos. |
| Evidencia FIRMS | Al abrir el detalle, haya detecciones o no | Mantener visibles las cautelas: `type=0` significa *presumed vegetation fire*; una detección térmica no confirma por sí sola un incendio individual; la ausencia de detecciones asociadas no demuestra ausencia de incendio; la asociación del mismo día con el FWI de las 12:00 local es histórica/descriptiva y no predictiva. |
| Tabla meteorológica | Al abrir el detalle de variables | En implementación real, mostrar valor y unidad cuando estén disponibles; diferenciar faltante/no disponible de cero e indicar explícitamente la condición o motivo del faltante cuando se conozca. |
| Procedencia | Al abrir fuentes y limitaciones desde el resultado | Mantener fuentes y límites accesibles y concisos, priorizando qué fuente sustenta cada dato y las limitaciones pertinentes; evitar un bloque legal extenso. |
| Tratamiento de valores faltantes | Cualquier detalle de datos/resultados | Distinguir no disponible, insuficiente, no calculado y cero cuando se conozca. Nunca sustituir un valor faltante por cero. |
| Resultado parcial | Falla un agente/herramienta o entrada mientras otras salidas siguen disponibles | Identificar qué parte está afectada, qué resultados siguen disponibles y cuáles no. No presentar como completo un análisis en el que falló una parte esperada. |

## State Patterns

| Estado | Comportamiento visible para el usuario |
|---|---|
| Inicio / sin contexto seleccionado | Explicar brevemente que FireWatch analiza peligro meteorológico histórico, no ocurrencia de incendios. Invitar a seleccionar contexto; no exigir documentación técnica para comenzar. |
| Contexto válido / listo | Mantener visibles la ubicación y fecha/período seleccionados y habilitar la acción explícita de análisis. |
| Ubicación o período no disponible | No ejecutar como si el contexto fuera válido. Explicar si la selección está fuera de la cobertura o período y qué parte no puede analizarse. No sustituir silenciosamente por otra ubicación/fecha cercana. |
| Análisis en ejecución | Mantener el contexto. Exponer solo eventos reales de agentes/herramientas y estados registrados a medida que llegan. Si aún no se registró ningún evento, no inventar actividad ni sugerir que una etapa terminó. |
| Análisis completado | Mostrar el resultado principal contextualizado. Hacer accesibles desde la misma superficie la explicación y la traza; marcar como completo solo con el estado real registrado. |
| Datos meteorológicos insuficientes | Explicar qué dato o resultado requerido no está disponible y qué consecuencia tiene para el análisis. Mostrar únicamente resultados disponibles, con alcance claro; no representar faltantes como cero. |
| Referencia no disponible | Distinguir el FWI observado de la comparación histórica local-mensual no disponible. No inventar una referencia o anomalía sustituta. |
| Sin detecciones FIRMS asociadas | Indicar que no hay detecciones FIRMS asociadas al contexto seleccionado; aclarar explícitamente que eso no implica ausencia de incendio. Mantener disponible el análisis FWI que sí sea válido. |
| Detecciones FIRMS disponibles | Presentarlas como detecciones térmicas con contexto de fecha/asociación local y límites pertinentes; no etiquetarlas como incendios individuales confirmados. |
| Error de herramienta o agente | Identificar tarea/resultado afectado y su estado de ejecución. Conservar resultados no afectados si están disponibles; no marcar el análisis completo si falló una parte requerida. El error debe distinguirse del estado parcial. |
| Análisis parcial | Distinguir resultados completados de los no disponibles/fallidos. La traza muestra solo eventos y estados reales. Explicar la parte afectada; no inventar una explicación satisfactoria para trabajo fallido. |
| Traza MAS vacía o incompleta | Indicar que faltan eventos/detalles de traza o que todavía no se registraron, según corresponda. No inferir que ningún agente participó únicamente porque no se pueda mostrar la traza. |

## Interaction Primitives

- Mantener estable el contexto principal mientras el usuario abre y cierra detalles progresivos.
- Hacer explícita la acción que inicia el análisis; desplegar un detalle no debe iniciar un análisis nuevo por sí solo.
- Ofrecer una forma comprensible de volver desde el detalle al resultado principal sin restablecer el contexto seleccionado.
- Para un período de varios días, recorrer las fechas individualmente; cada fecha conserva su FWI, referencia histórica local-mensual, diferencia, explicación y evidencia disponible. No calcular ni sugerir un FWI agregado para todo el período.
- Durante el procesamiento, usar solo evidencia en vivo: mostrar un evento únicamente después de que se haya registrado.
- Los detalles se expanden y contraen dentro de la superficie principal, según los mockups aprobados. El selector espacial y el control de fecha/período se representan solo de forma conceptual; el mecanismo concreto queda por definir al implementar la selección, debe limitarse a cobertura/períodos disponibles y comunicar selecciones inválidas sin sustituirlas silenciosamente. No se especifican atajos de teclado.

## Accessibility Floor

- El objetivo de conformidad del prototipo es WCAG 2.2 nivel AA.
- Conservar un orden significativo de lectura y foco de teclado: contexto, resultado y detalles progresivos.
- Exponer en texto el contexto espacial/temporal seleccionado y el estado del análisis; no depender solo de color o animación.
- Distinguir estados faltantes, cero, error, parcial y completado mediante texto accesible.
- Anunciar actualizaciones dinámicas de eventos reales de agentes/herramientas sin interrumpir repetidamente al usuario; validar el comportamiento de anuncios según la semántica de interfaz elegida.
- Asegurar que tecnologías de asistencia expongan junto al resultado las advertencias clave: FWI no es probabilidad y las detecciones FIRMS no son incendios confirmados.
- Verificar tamaños de texto, foco visible en los controles de expansión, navegación completa por teclado, contraste, lectura/relación de encabezados de las tablas y estados distinguibles sin depender solo del color.
- En anchos estrechos, adaptar tablas y trazabilidad sin perder legibilidad, orden de lectura ni asociación entre datos y encabezados.
- El objetivo WCAG 2.2 AA debe comprobarse sobre los componentes y estados implementados; los mockups no constituyen conformidad certificada.

## Key Flows

### UJ-1 — Luis contextualiza el peligro meteorológico de una zona de La Rioja

**Protagonista y contexto:** Luis, 34 años, técnico que realiza tareas de monitoreo ambiental en La Rioja. Entiende variables meteorológicas, no es especialista en IA y necesita interpretar con rapidez las condiciones de una zona determinada.

1. Luis abre FireWatch. En la superficie principal reconoce qué analiza el sistema y que el FWI expresa peligro meteorológico histórico, no una predicción de incendios. La superficie identifica el contexto actual durante este recorrido, sin presuponer un análisis previo guardado.
2. Selecciona una ubicación o sector de La Rioja y una fecha o período disponible. Si el contexto está fuera de cobertura o período, el sistema explica qué no puede analizar; no lo sustituye silenciosamente. Si elige varios días, cada día se presenta y contextualiza individualmente, sin resumen FWI agregado.
3. Luis inicia el análisis. Mientras corre, puede observar solo los eventos y estados reales de herramientas/agentes registrados; no se simula colaboración con animación decorativa.
4. El análisis se completa y la misma superficie presenta ubicación/período, FWI como peligro meteorológico, referencia histórica local-mensual, diferencia y una síntesis comprensible.
5. **Clímax:** Luis deja de ver un valor FWI aislado y entiende si las condiciones eran superiores o no a lo habitual para esa ubicación y época, con una explicación de lo que contribuyó y de lo que la comparación no permite concluir.
6. Sin perder contexto, profundiza en variables meteorológicas y componentes FWI; consulta la comparación histórica y detecciones FIRMS pertinentes, si existen.
7. Inspecciona la explicación en partes distinguibles: datos observados, cálculos determinísticos y contextualización/interpretación del sistema. La explicación no inventa valores ni altera cálculos.
8. Consulta fuentes y límites desde el análisis, incluyendo el alcance histórico, limitaciones de FIRMS y la asociación de detecciones pre-12:00 con FWI del mismo día calculado a las 12:00 local.
9. Si desea auditar el proceso, abre la traza secundaria e inspecciona agentes, secuencia general, tarea, estado y resultado/evidencia de intervenciones efectivamente registradas.
10. Luis vuelve al resultado principal con el contexto intacto. No se presupone guardado, historial o capacidad de compartir.

**Errores y casos límite:**

- Datos meteorológicos insuficientes: explicar la parte afectada y mostrar solo lo que sigue siendo válido.
- Sin referencia histórica local-mensual: mostrar el FWI observado por separado e indicar que la contextualización de referencia no está disponible.
- Sin detecciones FIRMS asociadas: comunicarlo como ausencia de detecciones asociadas, nunca como ausencia de incendio.
- Error de agente/herramienta: exponer tarea y resultado afectados; conservar salidas no afectadas y rotular el análisis parcial.
- Traza aún no registrada o incompleta: mostrar su condición real, sin inferir participación o éxito.

## Claridad y carga cognitiva

- La respuesta inicial prioriza “qué condiciones y dónde/cuándo” antes de explicar el sistema.
- FWI, referencia local-mensual y diferencia aparecen juntos para evitar que el usuario tenga que recordar valores al comparar.
- La síntesis no se convierte en una nueva categoría local de peligro; comunica comparación y límites en lenguaje ordinario.
- Variables, componentes y detecciones son consultables, pero subordinados visual y narrativamente a la síntesis.
- La explicación separa explícitamente entradas observadas, resultados determinísticos y contextualización del sistema para que una explicación de agente no parezca origen del cálculo FWI.
- La traza del MAS queda disponible sin dominar la primera lectura. Su contenido mínimo es estable; su formato visual no se decide en esta especificación.
- Advertencias y limitaciones aparecen junto al dato al que afectan además de estar disponibles en el detalle de fuentes.
- No mostrar todos los componentes con igual jerarquía por defecto es un principio de contenido; el orden final debe comprobarse con usuarios y no se fija aquí.

## Criterios de verificación para implementación

- Mantener como foco principal FWI observado, referencia histórica local-mensual, diferencia y síntesis; variables, FIRMS, fuentes y traza siguen siendo secundarias.
- En resultados reales, completar la tabla meteorológica con valores y unidades disponibles y representar explícitamente los faltantes, nunca como cero.
- Al expandir FIRMS, exponer juntas las cuatro cautelas definidas en Component Patterns, incluso cuando no haya detecciones asociadas.
- En cada intervención real de la traza, mostrar Agente / Tarea / Estado / Resultado-Evidencia; no inferir eventos y distinguir ejecución completa, parcial y error.
- Comprobar accesibilidad y adaptación responsive conforme a Accessibility Floor, incluyendo foco y lectura por teclado de secciones expandibles, tablas y traza.

## Límites abiertos para Architecture

Architecture decide la cantidad y responsabilidades finales de agentes, framework, modelo LLM, herramientas por agente, comunicación/orquestación, persistencia, infraestructura y tecnologías frontend/backend. También define cómo se producen y exponen estados y referencias reales de la traza sin alterar los contratos observables de UX. No hay decisiones UX pendientes que bloqueen la arquitectura; antes de implementar los controles de selección espacial/temporal debe concretarse su mecanismo accesible según la cobertura y períodos realmente disponibles. No quedan otros bloqueos UX identificados.
