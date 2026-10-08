---
title: FireWatch — PRD consolidado
status: final
created: 2026-10-07
updated: 2026-10-07
---

# PRD: FireWatch

## 0. Propósito del documento

Este documento consolida la definición de producto preliminar comunicada para FireWatch con la evidencia técnica de la investigación posterior. Sirve de referencia para UX, Architecture, implementación y evaluación del prototipo. La investigación se considera evidencia de factibilidad y límites metodológicos; no convierte el producto en un predictor ni cierra decisiones de diseño técnico.

En el contexto académico de Seminario II, la tecnología principal investigada es BMAD Method. FireWatch es el caso de aplicación utilizado para experimentar el proceso de planificación, diseño, arquitectura, implementación y revisión asistidos por BMAD. FireWatch también incluirá un Sistema Multiagente (MAS) en runtime, que es una capa del producto distinta de los agentes que BMAD utiliza durante el desarrollo.

La versión preliminar no quedó persistida como archivo independiente en el repositorio. Por tanto, este documento consolida el contexto preliminar compartido en la conversación y la investigación técnica proporcionada, junto con el estado de los artefactos de datos y scripts disponibles en el repositorio. No se presupone contenido de un documento preliminar no disponible.

El PRD especifica capacidades, comportamiento y criterios de aceptación. No prescribe framework de agentes, número de agentes, prompts, modelo LLM, orquestación, frontend, backend, persistencia ni infraestructura. Esas decisiones se reservan para Architecture; la interacción detallada se reserva para UX.

## 1. Visión

**FireWatch es un prototipo web para el análisis y visualización del peligro meteorológico de incendios forestales en la provincia de La Rioja, Argentina, con contextualización histórica, trazabilidad y un Sistema Multiagente visible para el usuario.**

FireWatch permite explorar valores y componentes del Canadian Fire Weather Index (FWI) en contexto espacial y temporal, compararlos con referencias históricas para la misma ubicación y mes y consultar detecciones térmicas históricas de NASA FIRMS cuando corresponda. El producto debe hacer visibles las fuentes, el método, las asociaciones realizadas y sus limitaciones para que los resultados puedan interpretarse y reproducirse.

El FWI describe **peligro meteorológico de incendio**; no expresa probabilidad de incendio. FireWatch no predice la ocurrencia, fecha ni ubicación de incendios. Su integración con FIRMS es histórica y descriptiva, no predictiva ni causal. No es un sistema oficial de alerta o prevención y no reemplaza a organismos ni sistemas operativos.

La capa MAS coordina tareas de análisis, validación, contextualización y explicación, y expone al usuario qué agentes participaron y qué acción realizó cada uno. Los agentes no sustituyen los cálculos científicos determinísticos: los valores cuantitativos deben proceder de servicios o herramientas verificables.

## 2. Usuarios objetivo

### 2.1 Necesidades y trabajos por realizar

**[ASSUMPTION: audiencia provisional]** El prototipo atenderá a quienes necesitan explorar o demostrar el análisis histórico del peligro meteorológico en La Rioja y comprender cómo se obtuvieron y contextualizaron los resultados. La definición de segmentos, perfiles y personas concretas queda para UX.

Necesidades que el producto debe atender:

- Consultar el FWI y sus componentes para una ubicación y fecha del período de estudio.
- Entender cómo se compara un valor con el comportamiento histórico de esa ubicación en el mismo mes.
- Consultar detecciones FIRMS históricas asociadas sin confundirlas con incendios individuales confirmados.
- Comprender las fuentes, transformaciones, método y limitaciones que afectan cada resultado.
- Observar la participación del MAS, las acciones realizadas y la trazabilidad del análisis.
- Reproducir los cálculos cuantitativos determinísticos a partir de las entradas y herramientas verificables.

### 2.2 No usuarios / usos excluidos

FireWatch no está destinado a personas que necesiten una alerta operativa oficial, una predicción de incendios, una probabilidad de ocurrencia o una decisión de respuesta de emergencia. Tampoco sustituye a autoridades, organismos de prevención ni sistemas oficiales.

### 2.3 Recorridos de usuario

Los recorridos narrativos con personas y los flujos detallados no están definidos en la evidencia suministrada. No se inventan personas ni secuencias de interfaz en este PRD. UX deberá elicitar y documentar los recorridos reales, incluidos el acceso al análisis, la selección espacial y temporal, la lectura de resultados y la inspección de la trazabilidad.

## 3. Glosario

- **Canadian Fire Weather Index System (FWI System):** método canadiense de evaluación del peligro meteorológico de incendio. En este proyecto se utiliza su versión clásica.
- **Componentes FWI:** FFMC, DMC, DC, ISI, BUI y FWI, calculados como parte del FWI System.
- **Peligro meteorológico de incendio:** condiciones meteorológicas representadas por el FWI System. No es probabilidad de ocurrencia ni confirmación de un incendio.
- **Ubicación meteorológica:** punto efectivo de la cobertura ERA5, identificado por `weather_id`, al que corresponden datos meteorológicos y resultados FWI.
- **Celda-día:** unidad analítica identificada por la combinación `weather_id` + fecha.
- **Detección FIRMS:** detección térmica satelital. Para este estudio se consideran registros VIIRS S-NPP con `type=0`, clasificados por FIRMS como *presumed vegetation fire*. No equivale a un incendio forestal individual confirmado.
- **`firms_count`:** cantidad de detecciones FIRMS asociadas a una celda-día. Cero significa que no se asoció una detección FIRMS; no demuestra ausencia de incendio.
- **Referencia histórica local-mensual:** mediana histórica de FWI para una combinación de ubicación meteorológica (`weather_id`) y mes calendario.
- **Anomalía respecto de referencia:** diferencia entre el FWI observado y la referencia histórica local-mensual correspondiente.
- **MAS (Sistema Multiagente):** sistema de agentes propio de FireWatch ejecutado en runtime para coordinar y exponer tareas de análisis. No son los agentes de BMAD usados durante el desarrollo.
- **BMAD Method:** método utilizado como tecnología principal de investigación académica para asistir el proceso de planificación, diseño, arquitectura, implementación y revisión del caso FireWatch.
- **Período de spin-up:** período previo al análisis principal utilizado para inicializar y continuar los estados del FWI System.

## 4. Funcionalidades

### 4.1 Cobertura, fuentes y método de cálculo

**Descripción:** FireWatch presenta análisis históricos de la provincia de La Rioja basados en límites geográficos del Instituto Geográfico Nacional de Argentina, meteorología histórica de Open-Meteo Historical API utilizando ERA5, detecciones térmicas históricas NASA FIRMS VIIRS S-NPP y el Canadian Fire Weather Index System clásico.

La cobertura meteorológica se construyó con una cuadrícula de planificación de 0,25 grados y 169 ubicaciones meteorológicas efectivas ERA5. Se procesaron temperatura a 2 m, humedad relativa a 2 m, velocidad del viento a 10 m y precipitación. Los componentes FWI se calculan diariamente con las condiciones de las 12:00 hora local de La Rioja y la precipitación acumulada durante las 24 horas previas. El año 2020 se utiliza para spin-up; el período principal de análisis es 2021–2025.

**Requisitos funcionales**

#### FR-1: Mostrar procedencia y cobertura de los datos

El usuario puede consultar las fuentes, variables, cobertura espacial, períodos y método de cálculo que sustentan el análisis.

**Consecuencias verificables:**
- Se identifican IGN Argentina, Open-Meteo Historical API/ERA5, NASA FIRMS VIIRS S-NPP y el Canadian Fire Weather Index System clásico.
- Se informa que la cuadrícula de planificación es de 0,25 grados y contiene 169 ubicaciones meteorológicas efectivas; no se presenta ese tamaño de planificación como resolución nativa de ERA5.
- Se distinguen 2020 como spin-up y 2021–2025 como período principal.
- Se indican las variables meteorológicas, la hora local de referencia y la ventana de precipitación utilizada.

#### FR-2: Mostrar el método y el estado de validación del FWI

El usuario puede consultar los seis componentes calculados y una descripción de cómo se obtuvieron y contrastaron.

**Consecuencias verificables:**
- Se identifican FFMC, DMC, DC, ISI, BUI y FWI.
- Se informa que la implementación principal está en Python mediante `cffdrs`.
- Se informa que la implementación Python de FFMC, DMC, DC, ISI, BUI y FWI fue contrastada contra la implementación R `cffdrs` durante 31 días de enero de 2023, con diferencia máxima observada de 0 para los seis componentes en ese período comprobado. El resultado no se generaliza más allá de esos 31 días.
- Se exponen los estados iniciales FFMC=85, DMC=6 y DC=15, y que 2020 funciona como spin-up con estados continuados entre años.
- No se describe este procedimiento como calibración ecológica específica y validada para La Rioja.

#### FR-3: Exponer integridad y disponibilidad de los conjuntos de datos de investigación

El usuario puede consultar el alcance y las comprobaciones de calidad de los conjuntos que respaldan la demostración.

**Consecuencias verificables:**
- El conjunto FWI se describe con 169 ubicaciones y 370.448 registros diarios para 2020–2025.
- Para ese conjunto se informa que no hay faltantes, duplicados, infinitos ni componentes FWI negativos.
- El conjunto analítico 2021–2025 se describe con 308.594 celdas-día, de las cuales 2.286 tienen al menos una detección FIRMS asociada y 306.308 no tienen detecciones asociadas.
- Se informa que las 10.956 detecciones individuales se conservan mediante `firms_count`.

### 4.2 Exploración y contextualización del peligro meteorológico

**Descripción:** El dashboard permite examinar espacial y temporalmente el FWI observado y sus componentes, con referencia histórica local-mensual. La visualización debe evitar categorías locales de peligro que no hayan sido validadas. Los diseños, controles y disposición de vistas quedan para UX.

#### FR-4: Consultar FWI y componentes por ubicación y fecha

El usuario puede contextualizar un valor FWI dentro de la cobertura y el período disponibles, y consultar FFMC, DMC, DC, ISI y BUI para la misma ubicación y fecha.

**Consecuencias verificables:**
- El valor FWI se etiqueta como indicador de peligro meteorológico de incendio, no como probabilidad de incendio.
- La fecha y la ubicación meteorológica del resultado quedan identificables.
- No se presentan categorías locales de peligro inventadas o no validadas.

#### FR-5: Comparar con la referencia histórica local-mensual

El usuario puede consultar la mediana histórica de FWI para la misma ubicación y mes calendario y la diferencia del valor observado respecto de esa referencia.

**Consecuencias verificables:**
- La referencia identifica la ubicación y el mes que la definen.
- La diferencia se presenta como anomalía descriptiva, no como predicción, causalidad ni evaluación de desempeño predictivo.
- Se explica que la referencia se calcula por combinación `weather_id` + mes.

### 4.3 Detecciones térmicas históricas y análisis descriptivo

**Descripción:** FireWatch permite consultar detecciones FIRMS históricas en relación temporal y espacial con el conjunto meteorológico. La asociación no es causal ni predictiva y debe comunicarse con sus limitaciones.

#### FR-6: Mostrar detecciones FIRMS sin sobreinterpretarlas

El usuario puede consultar las detecciones FIRMS type=0 pertinentes al análisis, distinguiéndolas de los valores FWI y de una confirmación individual de incendio.

**Consecuencias verificables:**
- Las detecciones se describen como detecciones térmicas clasificadas como *presumed vegetation fire*.
- `firms_count=0` se explica como ausencia de detección FIRMS asociada, no como ausencia comprobada de incendio.
- Se muestran, cuando se presenten resultados asociados, la fecha local, la ubicación meteorológica asociada y la distancia de asociación disponible.

#### FR-7: Comunicar la integración FIRMS–FWI y sus límites

El usuario puede inspeccionar el método de asociación utilizado para el análisis histórico.

**Consecuencias verificables:**
- Se informa que las horas FIRMS UTC se transformaron a hora local y que cada detección se asoció a la ubicación ERA5 más cercana.
- Se informa que cada detección se asoció con el FWI de las 12:00 del mismo día local.
- Se exponen las distancias de asociación observadas: media de 10,234 km y máxima de 20,944 km.
- Se advierte expresamente que una detección anterior a las 12:00 puede quedar asociada a un FWI calculado con condiciones meteorológicas posteriores dentro del mismo día.
- Se indica que, por este motivo, la asociación no evalúa predicción ni demuestra causalidad.

#### FR-8: Presentar resultados exploratorios con denominadores e interpretación correctos

Cuando se presenten los resultados descriptivos del estudio, el usuario puede identificar la población comparada, la referencia y el significado limitado de los porcentajes y diferencias.

**Consecuencias verificables:**
- Se distingue la comparación global observada —mediana FWI 19,071 sin detección asociada y 22,172 con detección asociada— de la comparación ajustada por referencia histórica local-mensual.
- Para las 2.286 celdas-día con detección asociada, se informa que 64,04% tuvo FWI superior a su referencia local-mensual y que la anomalía mediana fue +3,183 puntos FWI.
- Se informa que la anomalía mediana fue positiva en los 12 meses y los cinco años estudiados, con distinta intensidad.
- El 64,04% no se presenta como precisión, sensibilidad o porcentaje de incendios predichos.
- La conclusión permitida se formula como asociación descriptiva entre detecciones FIRMS y condiciones FWI relativamente elevadas respecto de lo habitual para la ubicación y época del año.

### 4.4 Sistema Multiagente visible en runtime

**Descripción:** El MAS es una capacidad propia del producto FireWatch. Debe hacer visible su participación en el flujo analítico, sin confundirse con los agentes de BMAD usados para construir el prototipo. La arquitectura interna queda abierta.

#### FR-9: Hacer observable la participación del MAS

El usuario puede observar qué agentes participaron en una ejecución del análisis y qué acción realizó cada uno.

**Consecuencias verificables:**
- Para cada análisis completado, el registro permite identificar como mínimo el agente participante, la tarea o responsabilidad ejecutada, el estado de ejecución y el resultado, evidencia o referencia producida.
- Desde el dashboard, el usuario puede inspeccionar qué agentes participaron en el análisis completado y la secuencia general de sus intervenciones.
- La vista no atribuye a un agente acciones que no se hayan ejecutado ni registrado.
- La interfaz distingue la actividad del MAS en runtime del uso de BMAD durante el desarrollo del proyecto.
- La forma visual exacta de inspeccionar la secuencia queda para UX.

#### FR-10: Separar análisis de agentes y cálculo determinístico

El MAS puede coordinar tareas, validar datos y resultados, contextualizar información y generar explicaciones; los agentes no reemplazan las herramientas o servicios verificables que producen los resultados cuantitativos.

**Consecuencias verificables:**
- Los valores FWI y demás cálculos cuantitativos se obtienen de servicios o herramientas verificables.
- Las explicaciones generadas por agentes no se presentan como cálculo científico si no proceden de dichas herramientas.
- El propósito funcional del MAS incluye separación de responsabilidades, coordinación, validación, contextualización, explicación y trazabilidad visible.
- El cumplimiento de este requisito no fija número, nombres, framework ni diseño interno de agentes.

### 4.5 Trazabilidad, fuentes y límites de interpretación

**Descripción:** Las vistas y explicaciones que presentan resultados deben permitir al usuario entender su origen y sus restricciones metodológicas.

#### FR-11: Mantener trazabilidad comprensible

El usuario puede inspeccionar las fuentes y las acciones que sustentan el análisis presentado, incluidas las participaciones registradas del MAS y el uso de herramientas verificables para los resultados cuantitativos.

**Consecuencias verificables:**
- La procedencia de los datos, las asociaciones relevantes y las limitaciones interpretativas pueden consultarse desde el análisis.
- En todo análisis completado, la trazabilidad identifica agente participante, tarea o responsabilidad, estado de ejecución y resultado, evidencia o referencia producida.
- La explicación no convierte una detección FIRMS en incendio confirmado ni un valor FWI en probabilidad.
- La representación visual queda por especificar en UX; persistencia e infraestructura de la traza quedan para Architecture.

### 4.6 Evidencia técnica consolidada

La investigación técnica posterior al PRD preliminar aporta la siguiente evidencia para delimitar el producto:

- La cobertura se basa en límites del Instituto Geográfico Nacional de Argentina y una cuadrícula de planificación de 0,25 grados, con 169 ubicaciones meteorológicas efectivas ERA5.
- Se procesaron temperatura a 2 m, humedad relativa a 2 m, viento a 10 m y precipitación a través de Open-Meteo Historical API utilizando ERA5.
- El FWI clásico se calcula diariamente con condiciones de las 12:00 hora local de La Rioja y precipitación acumulada de las 24 horas previas.
- Python con `cffdrs` es la implementación principal. Se contrastaron FFMC, DMC, DC, ISI, BUI y FWI contra la implementación R `cffdrs` durante 31 días de enero de 2023; la diferencia máxima observada fue 0 para cada componente en ese período comprobado. Este resultado no se generaliza a otros períodos.
- Los estados iniciales son FFMC=85, DMC=6 y DC=15. El año 2020 se usa como spin-up y los estados continúan entre años; esto no constituye calibración ecológica específica validada para La Rioja.
- Se documentó una corrección local para el caso límite de `drought_code`: cuando la precipitación es menor o igual a 2,8 mm, evita evaluar una rama de humectación que no corresponde.
- El conjunto FWI cubre 2020–2025: 169 ubicaciones y 370.448 registros diarios, sin faltantes, duplicados, infinitos ni componentes FWI negativos.
- La integración FIRMS–FWI de 2021–2025 contiene 10.956 detecciones FIRMS type=0. Convierte UTC a hora local, asocia cada detección a la ubicación meteorológica ERA5 más cercana y al FWI de las 12:00 del mismo día local; la distancia media fue 10,234 km y la máxima 20,944 km.
- El conjunto analítico tiene unidad `weather_id` + fecha y contiene 308.594 celdas-día; 2.286 tienen al menos una detección asociada y 306.308 no tienen detección asociada. Las detecciones individuales se conservan en `firms_count`.
- La comparación global de medianas FWI fue 19,071 para celdas-día sin detección y 22,172 con detección. La diferencia global estaba condicionada por estacionalidad y heterogeneidad espacial, por lo que se examinó también la referencia histórica local-mensual.
- Sobre las 2.286 celdas-día con detección, 64,04% superó su referencia histórica local-mensual y la anomalía mediana fue +3,183 puntos FWI. Las anomalías medianas fueron positivas en cada uno de los 12 meses y los cinco años, con intensidad diferente.

Esta evidencia fundamenta análisis histórico y descriptivo. No demuestra causalidad, capacidad predictiva, calibración ecológica local ni ausencia de incendios cuando no se observó una detección asociada.

## 5. No objetivos explícitos

FireWatch no incluirá, como producto definido por este PRD:

- Predicción exacta de ocurrencia, fecha o ubicación de incendios.
- Estimación de probabilidad futura de ocurrencia de un incendio.
- Simulación de propagación del fuego.
- Visión por computadora o análisis multimodal.
- Alertas oficiales o sustitución de organismos, sistemas operativos de prevención o respuesta.
- Calibración ecológica definitiva del FWI para La Rioja.
- Interpretar `type=0` como confirmación de un incendio forestal individual.
- Interpretar ausencia de detección FIRMS asociada como prueba de ausencia de incendio.
- Presentar asociaciones FIRMS–FWI como causalidad o evaluación predictiva.
- Presentar el FWI como probabilidad, precisión o sensibilidad.
- Incorporar categorías locales de peligro sin validación.
- Permitir que los agentes sustituyan los cálculos científicos determinísticos verificables.
- Definir ahora el framework, cantidad, prompts, modelo, herramientas u orquestación del MAS.

## 6. Alcance del MVP

### 6.1 Incluido

- Prototipo web enfocado en la provincia de La Rioja, Argentina.
- Consulta y visualización espacial y temporal del FWI para el período principal 2021–2025, con 2020 identificado como período de spin-up.
- Consulta de FFMC, DMC, DC, ISI y BUI junto al FWI.
- Contextualización mediante la referencia histórica de la misma ubicación y mes y su diferencia respecto del FWI observado.
- Consulta descriptiva de detecciones FIRMS type=0 y `firms_count`, con lenguaje inequívoco sobre su significado.
- Exposición de fuentes, método, cobertura, calidad comprobada y limitaciones de la integración FIRMS–FWI.
- Sistema Multiagente propio en runtime, visible para el usuario en cuanto a participación y acciones registradas.
- Uso de herramientas o servicios verificables para los valores cuantitativos, separación de responsabilidades y trazabilidad comprensible.
- Demostración del análisis histórico y reproducibilidad de los cálculos determinísticos.

**Criterio mínimo de aceptación del flujo end-to-end:** el MVP se considera funcional cuando un usuario puede:

1. Seleccionar un contexto espacial y temporal válido dentro de la cobertura y período disponibles.
2. Ejecutar un análisis para ese contexto.
3. Visualizar el FWI y sus componentes relevantes.
4. Visualizar la contextualización histórica/local disponible para ese contexto.
5. Recibir una explicación del análisis.
6. Consultar la trazabilidad del MAS, identificando agentes participantes y la secuencia general de sus intervenciones; para cada análisis completado, la trazabilidad incluye agente, tarea o responsabilidad, estado de ejecución y resultado, evidencia o referencia producida.

El criterio define el resultado observable, no una secuencia de pantallas ni un diseño visual. La representación visual queda para UX; número de agentes, framework, LLM, orquestación, persistencia e infraestructura quedan para Architecture.

### 6.2 Fuera del MVP

- Predicción, probabilidad de ocurrencia y alertas oficiales.
- Propagación, visión por computadora, análisis multimodal y usos operativos de prevención o respuesta.
- Calibración ecológica definitiva para La Rioja y categorías locales de peligro no validadas.
- Definición de una arquitectura técnica o de agentes en este PRD.
- Datos meteorológicos operativos en tiempo real; el alcance de análisis definido aquí es histórico. La modalidad de actualización en runtime de las trazas del MAS queda abierta para Architecture.

## 7. Métricas de éxito

Las métricas se verifican mediante resultados observables del flujo y de los datos existentes; no miden desempeño predictivo ni requieren umbrales de adopción, latencia o disponibilidad que no fueron definidos.

- **SM-1 — Completitud del flujo end-to-end:** el criterio de §6.1 se cumple si, en una ejecución de aceptación, el usuario puede realizar en orden las seis acciones enumeradas y consultar sus resultados. Se registra cada acción como completada o no completada; el flujo pasa únicamente si las seis se completan.
- **SM-2 — Trazabilidad de análisis completados:** todos los análisis completados disponibles para inspección incluyen los cuatro datos mínimos de FR-9/FR-11: agente participante, tarea o responsabilidad, estado de ejecución y resultado, evidencia o referencia producida. La métrica se cumple si no hay análisis completado al que le falte alguno de esos datos.
- **SM-3 — Reproducibilidad de cálculos determinísticos:** al recalcular con las mismas entradas, las herramientas verificables reproducen los mismos resultados cuantitativos. La validación de contraste documentada para los seis componentes Python frente a R `cffdrs` reporta diferencia máxima observada 0 durante los 31 días de enero de 2023; este resultado se limita a ese período comprobado.
- **SM-4 — Presentación de fuentes y limitaciones:** la revisión de la interfaz confirma que identifica las fuentes definidas en §4.1 y muestra las limitaciones metodológicas relevantes de FIRMS–FWI descritas en FR-6/FR-7, sin presentar detecciones como incendios confirmados ni FWI como probabilidad.
- **SM-5 — Colaboración multiagente visible:** para un análisis completado, el dashboard permite inspeccionar agentes participantes y la secuencia general de intervenciones, y la traza permite consultar los cuatro datos mínimos establecidos en SM-2. La evaluación confirma si ambos aspectos están presentes.
- **SM-6 — Visualización del análisis contextualizado:** para un contexto espacial/temporal válido, la interfaz presenta FWI, sus componentes relevantes y la contextualización histórica/local disponible; se verifica la presencia de cada elemento en la vista correspondiente.

Las medianas, anomalías y porcentajes de la sección §4.6 son resultados descriptivos de investigación, no métricas de éxito del producto.

**Contramétricas (no optimizar):**

- **SM-C1:** cantidad de detecciones FIRMS o celdas-día con detección. Un aumento no demuestra aumento de incendios confirmados ni mejora del producto; contrapesa cualquier incentivo a presentar más detecciones como éxito.
- **SM-C2:** número de agentes, acciones o explicaciones producidas por el MAS. Más actividad no implica mejor análisis; contrapesa incentivos a complejizar u ocultar la trazabilidad.

## 8. Preguntas abiertas

### Para UX

1. ¿Qué perfiles y recorridos reales deben priorizarse en la demostración?
2. ¿Cómo se organizan las vistas, controles y explicaciones para explorar ubicación, fecha, FWI, referencia, anomalía y detecciones?
3. ¿Cómo se presentan visualmente la actividad del MAS, las fuentes y las limitaciones sin sugerir certeza predictiva?

### Para Architecture

4. ¿Cuál será la arquitectura técnica del prototipo, incluida la separación frontend/backend, persistencia e infraestructura?
5. ¿Cuál será el diseño definitivo del MAS: cantidad de agentes, responsabilidades finales, herramientas por agente, comunicación, coordinación y orquestación?
6. ¿Se evaluará CrewAI u otro framework de agentes? La elección sigue abierta.
7. ¿Qué modelo LLM se usará, si corresponde, y cuál será la política de uso del modelo?
8. ¿Cómo se implementará la persistencia y el mecanismo de trazabilidad en runtime?

Estas preguntas no cambian las definiciones cerradas de producto ni autorizan a interpretar el prototipo como predictor.

## 9. Índice de supuestos

- §2.1 — **[ASSUMPTION: audiencia provisional]** El prototipo sirve a personas que exploran o demuestran el análisis histórico; perfiles y segmentos concretos se definirán en UX.

No se incorporan supuestos de datos, desempeño, categorías de peligro, predicción ni arquitectura en esta versión. La definición de perfiles y recorridos de usuario permanece pendiente de elicitación en UX; no se considera una persona o flujo confirmado.
