---
stepsCompleted:
  - step-01-validate-prerequisites
  - step-02-design-epics
  - step-03-create-stories
  - step-04-final-validation
inputDocuments:
  - prds/prd-sistema-incendios-forestales-2026-10-07/prd.md
  - prds/prd-sistema-incendios-forestales-2026-10-07/validation-report.md
  - prds/prd-sistema-incendios-forestales-2026-10-07/revalidation-report.md
  - ux-designs/ux-sistema-incendios-forestales-2026-10-07/EXPERIENCE.md
  - ux-designs/ux-sistema-incendios-forestales-2026-10-07/DESIGN.md
  - ux-designs/ux-sistema-incendios-forestales-2026-10-07/mockups/key-uj1-main.html
  - ux-designs/ux-sistema-incendios-forestales-2026-10-07/mockups/key-uj1-states.html
  - architecture/architecture-sistema-incendios-forestales-2026-10-07/ARCHITECTURE-SPINE.md
  - architecture/architecture-sistema-incendios-forestales-2026-10-07/ARCHITECTURE-DISCUSSION.md
---

# FireWatch - Epic Breakdown

## Overview

Plan de implementación mínimo y ordenado para alcanzar el MVP de FireWatch y preparar su demostración académica. El camino prioriza un vertical slice real basado en el snapshot existente: selección válida, análisis diario, resultado FWI contextualizado, explicación y traza MAS inspeccionable. Las decisiones ratificadas de PRD, UX y Architecture son contratos; este plan no incorpora predicción, alertas, cuentas, historial de usuario ni infraestructura remota.

## Requirements Inventory

### Functional Requirements

- **FR-1 — Procedencia y cobertura:** permitir consultar fuentes, variables, cobertura, períodos y método; distinguir la cuadrícula de planificación de 0,25° de la resolución nativa ERA5.
- **FR-2 — Método y validación FWI:** exponer los seis componentes, implementación Python `cffdrs`, estados iniciales/spin-up y contraste con R `cffdrs` (31 días de enero de 2023; diferencia máxima observada 0 para los seis componentes solo en ese período; sin afirmar calibración ecológica local).
- **FR-3 — Integridad y disponibilidad de datos:** mostrar alcance y controles reportados: 370.448 registros FWI / 169 ubicaciones / 2020–2025 sin faltantes, duplicados, infinitos ni FWI negativos; 308.594 celdas-día analíticas / 2.286 con detección / 306.308 sin detección / 10.956 detecciones preservadas en `firms_count`.
- **FR-4 — FWI por contexto:** consultar FWI y componentes para una ubicación y fecha; identificar fecha/ubicación, rotular FWI como peligro meteorológico y no añadir categorías locales no validadas.
- **FR-5 — Referencia histórica local-mensual:** mostrar mediana para el mismo `weather_id` y mes y diferencia descriptiva, sin inferir predicción, causalidad o desempeño predictivo.
- **FR-6 — Evidencia FIRMS:** mostrar detecciones type=0 como detecciones térmicas *presumed vegetation fire*, con fecha, ubicación y distancia cuando estén disponibles; `firms_count=0` no significa ausencia de incendio.
- **FR-7 — Asociación FIRMS–FWI y límites:** comunicar conversión UTC/local, asociación a centro ERA5 más cercano y al FWI de las 12:00 local del mismo día, distancia media 10,234 km y máxima 20,944 km, y cautela pre-12:00; asociación histórica/descriptiva, no causal ni predictiva.
- **FR-8 — Resultados exploratorios:** si se presentan, distinguir las medianas globales (19,071 sin detección y 22,172 con detección) del análisis ajustado local-mensual; preservar denominadores, el 64,04% y anomalía mediana +3,183 para las 2.286 celdas-día con detección y su interpretación estrictamente descriptiva.
- **FR-9 — MAS visible:** inspeccionar agentes participantes y secuencia general; para cada análisis completado mostrar/registrar agente, tarea, estado y resultado/evidencia/referencia efectivamente producida, sin atribuciones inventadas y diferenciando MAS runtime de BMAD.
- **FR-10 — Cálculo separado de agentes:** obtener resultados cuantitativos de herramientas/servicios verificables; agentes coordinan, validan, contextualizan y explican, pero no calculan ni alteran FWI ni otras cifras.
- **FR-11 — Trazabilidad comprensible:** consultar desde el análisis procedencia, asociaciones, limitaciones, participaciones del MAS y uso de herramientas verificables.

### NonFunctional Requirements

El PRD no enumera NFR con identificadores propios. Estos NFR operativos y de calidad se derivan de las restricciones adoptadas en UX y Architecture:

- **NFR-1 — Integridad científica:** valores y resultados determinísticos proceden del snapshot/herramientas verificables; conservar unidades, procedencia y ausencia como null con motivo, nunca como cero.
- **NFR-2 — Bundle reproducible y seguro:** snapshot local inmutable con SQLite read-only, dos GeoJSON, manifiesto/procedencia y checksums; validar fail-closed antes de readiness.
- **NFR-3 — Contratos e independencia modular:** monolito modular FastAPI/React TypeScript, puertos/adaptadores, schemas/API tipados y dependencias con dirección verificable; no microservicios.
- **NFR-4 — Trazabilidad durable:** eventos append-only por run, persistidos antes de emitirse; secuencia estable, replay SSE, deduplicación y estado/resultados consistentes.
- **NFR-5 — Fallos explícitos:** distinguir `completed`, `partial` y `failed`; identificar la rama afectada y preservar resultados válidos; no fallback exitoso, no inventar actividad.
- **NFR-6 — Uso controlado del LLM:** OpenAI tras `LLMProvider`; configuración por entorno, modelo y timeout configurables, retries limitados, Structured Outputs/JSON Schema, techo por run, errores tipados y `MockLLM` solo explícito para desarrollo/tests; no latencia contractual.
- **NFR-7 — Seguridad y privacidad local:** loopback/same-origin, claves por entorno, no secretos/prompt/razonamiento oculto en logs; datos enviados al LLM solo evidencia ambiental pública necesaria. Revisar controles de cuenta antes de habilitar el proveedor real.
- **NFR-8 — Operabilidad de MVP:** un proceso FastAPI, migraciones ordenadas, retención local de 30 días configurable, logs con rotación finita y arranque/ready/apagado ensayables; sin cloud ni HA.
- **NFR-9 — Accesibilidad y adaptación:** objetivo WCAG 2.2 AA; teclado, foco visible, lectura/avisos accesibles, estados no dependientes solo del color y tablas/traza legibles en anchos reducidos.
- **NFR-10 — Reproducibilidad del stack:** comprobar versiones exactas/compatibilidad y guardar lockfiles al crear los proyectos Python y React; esto no es prerrequisito para ratificar arquitectura.

### Additional Requirements

- Retener el pipeline offline existente en `src/data`; no regenerar ni consultar ERA5/FIRMS online en una ejecución.
- Crear un release builder que valide las salidas existentes y empaquete SQLite + `coverage/province.geojson` + `coverage/weather-grid.geojson` + `manifest.json` con versiones, procedencia, cobertura, tamaños y SHA-256.
- El startup rechaza bundle ausente, incompatible o corrupto. Runtime científico abre SQLite read-only.
- Cobertura: 169 `weather_id` canónicos; el frontend toma el ID exacto de un feature GeoJSON. API analiza `{weather_id, date}` diario, valida membresía/disponibilidad y no acepta coordenadas libres, interpolación ni nearest substitution. Para el MVP, la story 1.4 concreta la selección visual como control HTML nativo, sin modificar el contrato API.
- Fechas de análisis 2021–2025; 2020 solo spin-up. Período de varios días significa navegación por análisis diarios independientes.
- Separar DB científica de solo lectura de audit SQLite local para runs, resultados, eventos y evidencias; retención por defecto 30 días.
- Tres roles MAS ratificados: contextualizador, validador y explicador, coordinados por state machine Python determinística; una única revisión máxima; agentes sin acceso arbitrario a SQL, filesystem o APIs.
- Contratos JSON Schema versionados para EvidenceBundle, roles, eventos; IDs de evidencia run-scoped.
- API FastAPI/Pydantic por HTTP; progreso mediante SSE con `Last-Event-ID`; frontend React/TypeScript/Vite servido same-origin por FastAPI.
- OpenAI real requiere credenciales/configuración válidas; fallos no hacen fallback a MockLLM. Persistir proveedor/modelo utilizado y metadatos permitidos.
- Un resultado FWI central confirmado se persiste antes de llamar LLM; fallos/inicio interrumpido terminan según disponibilidad de FWI como `partial` o `failed`, con eventos de sistema reales.
- No usar PostGIS, microservicios, servidor remoto, auth/cuentas, historial UI o distribución remota del snapshot en este MVP.
- La selección visual MVP se resuelve con controles HTML nativos, no con mapa: lista/select de features cargados desde la API (etiquetados con `weather_id` y centro/identificación disponible), más control de fecha limitado por las fechas que anuncia el backend. La UI envía el ID canónico seleccionado sin convertir coordenadas. Si una fecha dentro del rango no está disponible, el error explícito del backend se presenta sin sustitución. Es una elección de interfaz dentro del contrato UX abierto, no un cambio de Architecture.

### UX Design Requirements

- **UX-DR1 — Superficie única:** conservar contexto y resultado en una única superficie continua; acceder progresivamente a detalles sin crear páginas separadas.
- **UX-DR2 — Jerarquía del resultado:** priorizar ubicación/período, FWI como peligro meteorológico, referencia local-mensual, diferencia y síntesis; datos meteorológicos/componentes/FIRMS son secundarios.
- **UX-DR3 — Controles de contexto:** permitir seleccionar ubicación y fecha/período disponibles, comunicar fuera de cobertura, mantener contexto y no sustituir una selección inválida. Este plan elige la alternativa mínima de controles HTML nativos en Story 1.4.
- **UX-DR4 — Tabla ambiental y FWI:** valores con unidades, faltantes expresos distintos de cero; consultar temperatura, humedad, viento, precipitación, FFMC, DMC, DC, ISI, BUI y FWI.
- **UX-DR5 — Explicación por tipo de información:** separar observaciones, cálculos determinísticos e interpretación; el texto generado no altera cifras ni inventa valores.
- **UX-DR6 — FIRMS cauteloso:** siempre exponer las cuatro advertencias aprobadas: `type=0` = *presumed vegetation fire*; detección no confirma incendio individual; ausencia no prueba que no haya incendio; asociación a FWI 12:00 del mismo día es descriptiva/no predictiva.
- **UX-DR7 — Fuentes y limitaciones accesibles:** identificar ERA5/Open-Meteo, NASA FIRMS, IGN y método FWI, período y límites relevantes desde el resultado, de forma breve y trazable.
- **UX-DR8 — Traza fiel del MAS:** mostrar solo eventos realmente persistidos, secuencia general y campos Agente/Tarea/Estado/Resultado-Evidencia; distinguir completo/parcial/error y actividad de agente/herramienta/sistema.
- **UX-DR9 — Estados:** diseñar carga inicial, ejecución, completado, datos insuficientes, referencia no disponible, sin FIRMS, error de herramienta/agente, parcial, traza incompleta/no disponible y contexto inválido.
- **UX-DR10 — Dirección visual provisional:** superficie clara, neutros con verde petróleo/azul para datos e interacción, ámbar/rojo para estados, sans serif de sistema, desktop-first adaptable, efectos mínimos; no colorear el FWI como categoría de riesgo ni hacer del MAS protagonista.
- **UX-DR11 — Accesibilidad:** verificar WCAG 2.2 AA sobre componentes reales, navegación teclado, foco, contraste, nombres/unidades y lectura de tablas, anuncios dinámicos moderados y estados comprensibles sin color.
- **UX-DR12 — Responsive:** mantener legibles tabla meteorológica y trazabilidad en anchos menores; no perder encabezados/campos ni relación de datos.
- **UX-DR13 — Periodos de varios días:** cada fecha se analiza/recorre individualmente, sin agregar FWI entre días.

### FR Coverage Map

| Requisito | Epic(s) | Cobertura |
|---|---|---|
| FR-1 | Epic 2 | Procedencia, cobertura, período y método accesibles desde el resultado. |
| FR-2 | Epic 2 | Componentes, inicialización/spin-up y alcance preciso del contraste Python/R. |
| FR-3 | Epic 2 | Alcance y resultados de controles de calidad de los conjuntos. |
| FR-4 | Epic 1 | Selección de contexto y resultado FWI/componentes para fecha y ubicación. |
| FR-5 | Epic 1 | Referencia histórica local-mensual y diferencia determinística. |
| FR-6 | Epic 2 | Evidencia FIRMS y cautelas contra sobreinterpretación. |
| FR-7 | Epic 2 | Método, distancias y límites temporales/descriptivos de asociación. |
| FR-8 | Epic 2 | Resultados exploratorios, denominadores y lectura descriptiva correcta. |
| FR-9 | Epic 1; Epic 2 | Epic 1 entrega agentes/secuencia/campos mínimos; Epic 2 completa presentación de evidencia/errores. |
| FR-10 | Epic 1 | Los cálculos son determinísticos; roles MAS solo contextualizan, validan y explican. |
| FR-11 | Epic 1; Epic 2 | Epic 1 conecta resultado y traza real; Epic 2 completa procedencia y límites. |

Métricas: SM-1 se comprueba al completar las stories demo de Epic 1; SM-2/SM-5 en Stories 1.5, 1.7 y 1.8; SM-3 en Stories 1.3 y 2.1; SM-4 en Stories 2.1–2.4; SM-6 en Story 1.4. Las contramétricas SM-C1/SM-C2 son guardrails de revisión, no objetivos de story.

| NFR | Stories |
|---|---|
| NFR-1 | 1.2, 1.3, 2.1, 2.2 |
| NFR-2 | 1.2 |
| NFR-3 | 1.1 |
| NFR-4 | 1.3, 1.5, 1.8 |
| NFR-5 | 1.5, 1.6, 1.7, 2.5 |
| NFR-6 | 1.6, 1.7, 1.9 |
| NFR-7 | 1.1, 1.6, 1.9, 2.5 |
| NFR-8 | 1.1, 1.2, 1.5, 2.5 |
| NFR-9 | 2.4 |
| NFR-10 | 1.1 |

## Epic List

### Epic 1: Ejecutar y comprender un análisis diario contextualizado
El usuario selecciona un contexto disponible y obtiene un análisis diario real con FWI, referencia histórica local-mensual, diferencia, explicación y traza inspeccionable. Incluye únicamente la base técnica necesaria para entregar el recorrido como funcionalidad vertical.
**FRs covered:** FR-4, FR-5, FR-9 (mínimo), FR-10, FR-11 (traza y resultado).

### Epic 2: Inspeccionar evidencia, procedencia y límites del análisis
El usuario puede auditar fuentes, método, calidad reportada, evidencia FIRMS, resultados descriptivos y límites del análisis en los detalles progresivos de la misma superficie; el sistema queda preparado y ensayado para la defensa.
**FRs covered:** FR-1, FR-2, FR-3, FR-6, FR-7, FR-8, FR-9 (estados de traza), FR-11 (procedencia y límites).

## Dependencias, camino crítico y priorización

Epic 1 es la base inicial de implementación y debe producir primero el vertical slice con snapshot real. Epic 2 consume los contratos de resultado/evidencia/traza de Epic 1; sus trabajos de contenido, evidencia y pulido no deben bloquear la primera demo funcional. Las dependencias concretas por story y los hilos paralelos se indican en cada epic.

**Camino crítico recomendado:** 1.1 contratos/runtime mínimo → 1.2 bundle local construido y fail-closed → 1.3 lectura determinística/API → 1.4 recorrido UI real selección–resultado → 1.5 audit/eventos durables → 1.6 adaptador OpenAI real → 1.7 orquestación MAS → 1.8 vista de explicación/traza con SSE → 1.9 aceptación integrada y ensayo de llamada OpenAI real. Epic 2 continúa después o en paralelo tras fijarse los contratos de 1.1/1.3.

**Indispensable para demo end-to-end:** 1.1–1.9, 2.1, 2.2 y 2.5. La demo debe demostrar una ejecución real con OpenAI; MockLLM solo valida desarrollo/tests. Story 2.4 es requisito de calidad para entregar la interfaz según UX y objetivo AA, pero si el tiempo es crítico puede reducirse a los bloqueos de accesibilidad/responsive identificados, sin afirmar conformidad AA integral que no se haya comprobado. Story 2.3 (estadísticas agregadas FR-8) puede diferirse si el equipo decide no presentarlas en la demo; esto no autoriza a mostrar cifras sin contexto. No diferir cautelas científicas, comportamiento honesto de estados ni controles de acceso al proveedor.

## Epic 1: Ejecutar y comprender un análisis diario contextualizado

**Objetivo:** completar el flujo crítico desde contexto espacial/temporal válido hasta resultado FWI contextualizado, explicación OpenAI controlada y traza MAS real. El snapshot existente validado, no datos ficticios, es la fuente del recorrido.

### Story 1.1: Iniciar el runtime local y fijar contratos verticales mínimos

Como integrante del equipo de FireWatch,  
quiero ejecutar la aplicación local con contratos tipados compartidos,  
para construir y probar el primer recorrido funcional sobre una base reproducible.

**Dependencias:** ninguna.  
**Prioridad:** P0, demo indispensable.  
**Camino crítico:** sí.  
**Paralelizable:** no al inicio; fija contratos que desbloquean backend/UI en paralelo.

**Acceptance Criteria:**

**Given** un entorno de desarrollo limpio y versiones compatibles seleccionadas  
**When** instalo usando los lockfiles Python y frontend y ejecuto el comando local documentado  
**Then** inicia un único proceso FastAPI que sirve la SPA React/TypeScript same-origin y expone readiness y OpenAPI.

**Given** se acuerdan los contratos mínimos de cobertura, request diario, resultado, error y evento  
**When** se generan o comparten los tipos usados por frontend y backend  
**Then** el request de análisis contiene solo `weather_id` canónico y fecha local ISO; ninguna capa depende de internals de la otra.

**Given** el bundle/configuración local obligatoria falta o el proveedor OpenAI está seleccionado con configuración inválida  
**When** el runtime inicia  
**Then** falla con error identificable y no se presenta como ready.

**And** la story no instala servicios de nube, microservicios, autenticación ni infraestructura remota.

### Story 1.2: Construir y validar el snapshot científico local

Como usuario del prototipo,  
quiero que el análisis se apoye en un paquete de datos local íntegro y versionado,  
para obtener resultados reproducibles sin depender de fuentes meteorológicas online durante el run.

**Dependencias:** 1.1 para el contrato de configuración/readiness.  
**Prioridad:** P0, demo indispensable.  
**Camino crítico:** sí.  
**Paralelizable:** implementación del validador y diseño del builder pueden dividirse solo si comparten el manifiesto fijado en 1.1.

**Acceptance Criteria:**

**Given** las salidas offline existentes en `src/data`  
**When** se ejecuta el release builder  
**Then** produce `manifest.json`, SQLite científico, `coverage/province.geojson` y `coverage/weather-grid.geojson`, con versión, procedencia/cobertura y ruta/tipo/tamaño/SHA-256 por payload.

**Given** un bundle válido y configuración esperada de versión/digest de manifiesto  
**When** inicia la aplicación  
**Then** valida versión, integridad, esquema, disponibilidad de fechas y correspondencia entre los 169 `weather_id` y features antes de readiness, y abre SQLite en modo read-only.

**Given** falta un archivo, no coincide un checksum/tamaño, el schema o versión no es compatible o la cobertura no corresponde  
**When** se valida el bundle  
**Then** la app no queda ready y no sustituye bundle ni descarga/regenera datos.

**And** el builder conserva la semántica de los generadores científicos existentes y no se ejecuta por request.

### Story 1.3: Consultar cobertura y producir un resultado diario determinístico

Como técnico de monitoreo ambiental,  
quiero consultar un `weather_id` y fecha disponibles y obtener sus datos cuantitativos verificados,  
para conocer el peligro meteorológico y su referencia histórica sin depender de una interpretación generada.

**Dependencias:** 1.2.  
**Prioridad:** P0, demo indispensable.  
**Camino crítico:** sí.  
**Paralelizable:** API de cobertura y consultas de resultados pueden implementarse en dos ramas una vez fijado el schema de snapshot de 1.2; integración es secuencial.

**Acceptance Criteria:**

**Given** el snapshot validado  
**When** el cliente solicita cobertura  
**Then** la API devuelve GeoJSON de 169 features con `properties.weather_id` canónico, geometría, centro, indicadores de cobertura, fechas disponibles y procedencia.

**Given** un request con ID y fecha disponibles  
**When** se ejecuta el caso de uso diario  
**Then** `POST /api/analyses` crea un `analysis_id` y devuelve `202`; el run persiste su ciclo determinístico mínimo y `GET /api/analyses/{id}` devuelve FWI/componentes y variables disponibles, referencia mediana de la misma ubicación y mes, diferencia descriptiva, FIRMS asociado y refs de evidencia/procedencia que realmente existan.

**Given** un ID desconocido, fecha no disponible o valor faltante  
**When** se solicita el análisis  
**Then** rechaza explícitamente el contexto inválido o representa el faltante como null con estado/motivo; nunca elige vecino, interpola ni convierte ausencia a cero.

**Given** el run se inicia y termina su rama determinística  
**When** se registra el resultado  
**Then** los eventos mínimos de run (queued/started/core result y terminal completed/partial/failed) y la proyección/resultado se confirman de forma consistente; esto no inventa eventos de agente.

**And** el endpoint no calcula FWI mediante LLM ni agrega valores FWI entre fechas.

### Story 1.4: Seleccionar contexto y ver el resultado contextualizado

Como usuario de FireWatch,  
quiero seleccionar una ubicación de cobertura y una fecha disponible y ver el resultado principal,  
para completar el recorrido central con datos reales en una sola superficie.

**Dependencias:** 1.3 y decisión UX de control accesible apoyada en el GeoJSON ya expuesto; no requiere aún interacción MAS.  
**Prioridad:** P0, demo indispensable.  
**Camino crítico:** sí.  
**Paralelizable:** UI de la superficie puede desarrollarse desde el contrato compartido de 1.1 mientras 1.3 se implementa; conexión real espera 1.3.

**Acceptance Criteria:**

**Given** cobertura y límites/fechas disponibles cargados desde API  
**When** el usuario elige una ubicación mediante un `<select>` nativo (etiqueta con identificador y centro legibles) y una fecha o período mediante controles nativos  
**Then** la interfaz conserva y muestra el contexto y envía exactamente el `weather_id` de la feature seleccionada más la fecha local disponible del día ejecutado.

**Given** una selección espacial/temporal fuera de cobertura  
**When** el usuario intenta continuar  
**Then** la interfaz explica la restricción y no cambia silenciosamente ubicación o fecha.

**And** la ubicación no se elige mediante coordenadas libres ni se exige un mapa; si el servidor rechaza una fecha no disponible, la UI explica el motivo y mantiene la fecha/contexto seleccionado.

**Given** el usuario define un período de varios días  
**When** navega y ejecuta cada fecha  
**Then** cada fecha crea un run independiente y la interfaz no combina ni promedia FWI entre fechas.

**Given** respuesta válida del caso de uso  
**When** el análisis determinístico termina  
**Then** la misma superficie prioriza FWI rotulado como peligro meteorológico, ubicación/período, referencia local-mensual, diferencia y síntesis neutral, sin categorías locales de riesgo.

**And** se puede consultar cada día de un período por separado; no se presenta FWI agregado para varios días.

### Story 1.5: Persistir el estado y los eventos reales de un análisis

Como responsable de auditoría del análisis,  
quiero que cada transición relevante quede persistida antes de exponerse,  
para que el estado y la traza nunca dependan de actividad simulada o volátil.

**Dependencias:** 1.1; resultado determinístico de 1.3.  
**Prioridad:** P0, demo indispensable.  
**Camino crítico:** sí.  
**Paralelizable:** esquema/migraciones y pruebas de transición pueden dividirse tras congelar `trace-event.v1`; la integración con el caso de uso es secuencial.

**Acceptance Criteria:**

**Given** comienza una ejecución válida  
**When** se registran run, intervención, decisión o evento de herramienta  
**Then** el evento inmutable incluye secuencia por run, timestamp UTC, tipo y clave idempotente; intervenciones reales incluyen agente, tarea y referencias de evidencia.

**Given** una transición cambia estado o hace disponible un resultado  
**When** la aplicación confirma la transacción  
**Then** evento, proyección de estado y resultado visible cambian atómicamente; no se emite evento no persistido ni se conserva terminal contradictorio.

**Given** ocurre error determinístico de herramienta o no hay FWI central utilizable  
**When** el run se cierra  
**Then** se registra el evento/error real y queda `partial` si hay FWI central utilizable o `failed` si no; las ramas afectadas se identifican.

**Given** el proceso reinicia con un run persistido queued/running sin terminal  
**When** se recupera la audit DB  
**Then** cierra el run transaccionalmente con evento de sistema `run_interrupted` y terminal `partial` si FWI quedó comprometido, o `failed` si no; no reinicia la llamada LLM.

**And** la migración inicial de audit SQLite se ejecuta antes de readiness, separado del snapshot científico.

### Story 1.6: Conectar el proveedor OpenAI con salida estructurada

Como integrador del MAS,  
quiero invocar OpenAI mediante el puerto desacoplado con límites y validación,  
para obtener salidas estructuradas reproducibles desde los roles sin acoplar el dominio al SDK.

**Dependencias:** 1.1 para configuración/schemas. La integración de errores con el audit store se conecta tras 1.5; el adaptador puede construirse en paralelo con esa story.  
**Prioridad:** P0, demo indispensable.  
**Camino crítico:** sí para la demostración real.  
**Paralelizable:** adapter y schemas/Mock tests se pueden implementar concurrentemente solo con el schema fijado.

**Acceptance Criteria:**

**Given** configuración explícita de proveedor, clave, modelo, timeout finito positivo, retries 0..2 y techo positivo de tokens por run  
**When** el adaptador envía una solicitud estructurada  
**Then** valida respuesta contra JSON Schema, registra proveedor/modelo y metadatos disponibles y aplica límites; jamás guarda clave o razonamiento oculto.

**Given** falta o es inválida configuración real  
**When** se selecciona OpenAI  
**Then** falla explícitamente y no cambia a MockLLM.

**Given** proveedor devuelve error de autenticación, cuota, timeout/red, refusal o contenido/schema inválido  
**When** el adaptador traduce el fallo  
**Then** entrega un error tipado apto para una intervención fallida, sin respuesta exitosa de reserva.

**And** los reintentos no superan la configuración 0..2 y solo aplican a fallos transitorios; no reintentan refusal, credenciales inválidas ni salida/schema inválidos.

**And** MockLLM se selecciona explícitamente para test/desarrollo y comprueba contratos sin afirmar disponibilidad del servicio real ni latencia de producto.

### Story 1.7: Ejecutar la colaboración MAS determinística y trazable

Como usuario que necesita entender cómo se obtuvo el análisis,  
quiero que el sistema ejecute las responsabilidades MAS acordadas con proveedor real controlado,  
para recibir una explicación validada y una actividad auditable sin alterar los resultados determinísticos.

**Dependencias:** 1.3, 1.5 y 1.6.  
**Prioridad:** P0, demo indispensable.  
**Camino crítico:** sí.  
**Paralelizable:** schemas/MockLLM tests y adaptador OpenAI pueden trabajarse en paralelo tras fijar schemas; no paralelizar cambios al mismo contrato.

**Acceptance Criteria:**

**Given** un resultado determinístico y evidencia ya persistidos  
**When** el orquestador inicia el flujo  
**Then** ejecuta contextualizador, validador y explicador por la state machine Python con contratos versionados y máximo una revisión al contextualizador.

**Given** cada rol recibe evidencia  
**When** produce su resultado  
**Then** el runtime registra start y terminal reales con IDs propios, tarea, estado y evidencia/ref producida; los agentes no tienen herramientas arbitrarias ni pueden cambiar cifras determinísticas.

**Given** el validador no aprueba tras la revisión permitida o una llamada de agente falla  
**When** se determina el resultado del run  
**Then** no se muestra explicación no aprobada; se conserva el FWI válido y se indica la rama afectada en el estado parcial/error.

**And** los contratos rechazan referencias de evidencia inexistentes o ajenas al análisis.

### Story 1.8: Inspeccionar explicación y traza real con SSE

Como usuario de FireWatch,  
quiero consultar desde el resultado la explicación y la secuencia real de intervenciones,  
para distinguir datos observados, cálculo determinístico e interpretación y auditar qué ocurrió.

**Dependencias:** 1.5 y 1.7.  
**Prioridad:** P0, demo indispensable.  
**Camino crítico:** sí.  
**Paralelizable:** proyección de consulta y UI de componentes pueden avanzar en paralelo desde `trace-event.v1`; la integración y accesibilidad de anuncios requiere contrato común.

**Acceptance Criteria:**

**Given** un run en curso o terminado  
**When** el cliente consulta trace/result o se conecta al stream SSE  
**Then** muestra solo eventos persistidos, ordenados y deduplicados por `(analysis_id, sequence)`, con agente, tarea, estado y resultado/evidencia reales para cada intervención.

**Given** la traza se desconecta y el cliente conserva `analysis_id` y cursor  
**When** reconecta con `Last-Event-ID`  
**Then** recibe replay durable ordenado; el cierre/reinicio del navegador no implica historial global ni restaura automáticamente otro análisis.

**Given** trace aún no registrada, incompleta, no disponible o run `partial`/`failed`  
**When** la UI representa el estado  
**Then** diferencia esas condiciones textualmente y señala la tarea/salida afectada; evento de sistema/herramienta no se presenta como agente.

**And** la explicación mantiene separados observación, cálculo determinístico e interpretación; claims/ref evidencias se resuelven dentro del run.

### Story 1.9: Verificar el recorrido MVP con snapshot y OpenAI reales

Como equipo que prepara la defensa,  
quiero ejecutar pruebas de aceptación del recorrido completo en el entorno local de demostración,  
para confirmar que el usuario puede completar el flujo con datos y proveedor reales.

**Dependencias:** 1.2–1.8.  
**Prioridad:** P0, demo indispensable.  
**Camino crítico:** sí, puerta de salida antes del ensayo.  
**Paralelizable:** preparación de dataset/contexto de prueba y guion pueden adelantarse; aceptación solo tras integración.

**Acceptance Criteria:**

**Given** instalación limpia, bundle verificado, configuración OpenAI aprobada y conectividad  
**When** un usuario recorre selección → análisis → resultado → explicación → traza  
**Then** completa las seis acciones mínimas del PRD con datos del snapshot real, sin respuestas MockLLM.

**Given** falla OpenAI o una rama opcional durante el ensayo  
**When** se observa el resultado  
**Then** el estado es parcial/error honesto, se conserva lo determinístico que sigue siendo utilizable y se identifica qué parte falló.

**And** se registra una corrida de aceptación reproducible y se verifica que no se filtren secretos ni se afirme predicción/incendio confirmado.

## Epic 2: Inspeccionar evidencia, procedencia y límites del análisis

**Objetivo:** completar los detalles progresivos y la evidencia requeridos por PRD/UX y dejar un MVP defendible. No introduce funcionalidades fuera del producto aprobado ni condiciona el primer recorrido FWI operativo.

### Story 2.1: Consultar método, procedencia, cobertura y calidad de datos

Como técnico que necesita evaluar la confiabilidad del resultado,
quiero consultar de dónde provienen los datos, qué metodología se utiliza y qué controles de calidad se reportaron,
para entender el alcance y los límites de la evidencia disponible.

**Dependencias:** 1.3 (contrato de procedencia/resultados).
**Prioridad:** P1, demo requerida para explicar límites.
**Camino crítico:** no después de 1.4; las fuentes se pueden preparar en paralelo con 1.5 tras congelar contrato de procedencia.
**Paralelizable:** sí, con 2.2.

**Acceptance Criteria:**

**AC1 — Fuentes, método y cobertura**

**Given** un resultado disponible
**When** el usuario abre la sección de fuentes, metodología y calidad desde la misma superficie del dashboard
**Then** encuentra las fuentes IGN, Open-Meteo Historical API/ERA5 y FIRMS VIIRS S-NPP, el método FWI clásico, las variables meteorológicas utilizadas, la cobertura de 169 ubicaciones, la cuadrícula de planificación de 0,25°, el año 2020 utilizado como spin-up y el período analítico 2021–2025.

**AC2 — Documentación de validación técnica**

**Given** la documentación metodológica del proyecto
**When** se consulta la evidencia de contraste de implementaciones
**Then** se informa que Python `cffdrs` fue contrastado con R `cffdrs` durante los 31 días de enero de 2023, con diferencia máxima observada de 0 para FFMC, DMC, DC, ISI, BUI y FWI exclusivamente durante ese período, sin generalizar el resultado ni afirmar calibración ecológica local.

La comparación entre implementaciones constituye evidencia técnica para la documentación y la defensa académica. No es obligatorio mostrarla en el dashboard.

**AC3 — Calidad y disponibilidad de los conjuntos de datos**

**Given** un resultado disponible
**When** el usuario consulta la información de calidad de los datos
**Then** encuentra los conteos y controles establecidos en FR-3, identificando la población, el período y la versión del conjunto de datos correspondientes, sin convertir sus resultados en garantías aplicables a otros releases.

### Story 2.2: Consultar detecciones FIRMS con sus cautelas

Como usuario que contextualiza una fecha histórica,  
quiero inspeccionar las detecciones FIRMS asociadas con sus cautelas,  
para evaluar la evidencia sin confundir asociación con confirmación o predicción.

**Dependencias:** 1.3 para evidencia por run; el contrato de detalle/resultados debe permanecer estable.  
**Prioridad:** P1, demo requerida para cubrir investigación central si hay tiempo de defensa previsto.  
**Camino crítico:** no para el primer FWI+explicación; sí para cobertura PRD completa.  
**Paralelizable:** sí, con 2.1.

**Acceptance Criteria:**

**Given** una celda-día con detecciones  
**When** el usuario abre FIRMS  
**Then** ve fecha local, `weather_id` asociado, distancia disponible y la etiqueta *presumed vegetation fire* para `type=0`.

**Given** hay detecciones o no las hay  
**When** se despliega el detalle FIRMS  
**Then** siempre se explica que una detección térmica no confirma un incendio individual, que ninguna detección asociada no demuestra ausencia de incendio y que la asociación al FWI de las 12:00 del mismo día es histórica/descriptiva, no causal ni predictiva; se advierte el caso pre-12:00.

**And** ausencia de detecciones se representa como tal, nunca como “sin incendio”.

### Story 2.3: Presentar los hallazgos exploratorios con denominadores

Como usuario que consulta resultados globales del estudio,  
quiero distinguir la comparación general de la contextualizada local-mensual y sus poblaciones,  
para interpretar correctamente qué describen las estadísticas publicadas.

**Dependencias:** 2.1 para procedencia/conteos y 2.2 para semántica FIRMS.  
**Prioridad:** P2, diferible si FR-8 no se presenta en la demo.  
**Camino crítico:** no.  
**Paralelizable:** implementación de la presentación puede hacerse tras fijar el contrato de resultados exploratorios; no bloquea 2.4 ni 2.5.

**Acceptance Criteria:**

**Given** el usuario abre los resultados exploratorios del estudio  
**When** se muestran medianas globales y la comparación local-mensual  
**Then** se identifican por separado la mediana FWI 19,071 sin detección y 22,172 con detección, frente al análisis ajustado por referencia local-mensual.

**Given** se muestra el análisis de las celdas-día con detección  
**When** se presenta 64,04% y anomalía mediana +3,183  
**Then** se conserva el denominador de 2.286 celdas-día, el período de 12 meses y cinco años y el carácter descriptivo; no se etiqueta como precisión, recall ni probabilidad.

**And** si la visualización agregada se difiere, ninguna otra sección debe sugerir que estos hallazgos se presentaron o implican predicción.

### Story 2.4: Completar accesibilidad y presentación responsive del análisis

Como usuario que navega con diferentes dispositivos o tecnologías de asistencia,  
quiero leer y operar los detalles, tablas, estados y traza con claridad,  
para usar el flujo sin depender exclusivamente de color, puntero o pantalla ancha.

**Dependencias:** 1.4 y 1.8 para los componentes interactivos reales; puede iniciarse auditoría de prototipo tras contrato de UX.  
**Prioridad:** P1, necesaria para calidad de entrega; solo puede reducirse a corregir bloqueos si el calendario es insuficiente.  
**Camino crítico:** no para conectividad científica, sí para declarar cumplimiento accesible.  
**Paralelizable:** auditoría por componente sí; correcciones de componentes compartidos coordinadas para evitar churn.

**Acceptance Criteria:**

**Given** la superficie y los detalles progresivos reales  
**When** se navegan únicamente con teclado y tecnologías de asistencia  
**Then** el orden es significativo, el foco es visible, los controles expandibles son operables y los cambios de estado relevantes se anuncian sin interrupciones repetitivas por cada evento.

**Given** tablas meteorológicas, explicaciones y traza  
**When** se leen en escritorio y anchos menores  
**Then** nombres, encabezados, valores/unidades, campos de traza y asociación fila-columna permanecen comprensibles sin ocultar datos esenciales.

**Given** colores, advertencias, errores y valores FWI  
**When** se presenta cualquier estado  
**Then** los estados se identifican también mediante texto/semántica, hay contraste/foco adecuados, no se comunica el peligro solo por color y no se asignan categorías locales al FWI.

**And** se registra el resultado de una revisión WCAG 2.2 AA sobre componentes/estados implementados; no se afirma conformidad total si quedan criterios sin verificar.

### Story 2.5: Ensayar errores, recuperación local y demostración

Como equipo que defenderá FireWatch,  
quiero ensayar operación local y casos de fallo representativos,  
para demostrar estados completos/parciales/fallidos honestos y recuperar la aplicación de forma previsible.

**Dependencias:** 1.9 y 2.1/2.2; revisión puede comenzar en paralelo con Epic 1 solo cuando las reglas de recuperación y eventos estén fijadas.  
**Prioridad:** P1, demo/preparación obligatoria antes de defensa.  
**Camino crítico:** ensayo de proveedor real sí; endurecimiento operativo puede ejecutarse en paralelo con 2.1–2.3.  
**Paralelizable:** sí, pruebas de bundle, proveedor, reinicio/SSE y accesibilidad en ramas independientes contra contratos aprobados.

**Acceptance Criteria:**

**Given** un error de herramienta, proveedor o datos insuficientes  
**When** ocurre durante una ejecución de aceptación  
**Then** se genera error/evento real, el resultado señala la tarea/salida afectada y mantiene únicamente salidas no afectadas; sin FWI central utilizable queda `failed`, con FWI central utilizable puede quedar `partial`.

**Given** se desconecta SSE y luego se reinicia backend durante un run retenido  
**When** el backend vuelve a iniciar y el cliente conserva el ID/cursor  
**Then** el stream reproduce eventos persistidos; un run activo interrumpido se cierra con evento system `run_interrupted` y terminal `partial`/`failed` según FWI comprometido, sin repetir automáticamente llamadas LLM ni inventar intervenciones.

**Given** se ejecuta en el equipo local de defensa  
**When** se sigue el procedimiento documentado  
**Then** bundle/readiness, migraciones, proceso único, configuración/secreto OpenAI, shutdown y rotación/retención de logs se verifican; logs no contienen credenciales, prompts ni razonamiento oculto.

**And** el guion de ensayo incluye al menos una ejecución completa con OpenAI real y un escenario de fallo controlado; no se presenta MockLLM como prueba del proveedor real.

## Orden recomendado de Build y paralelización

| Ola | Trabajo en orden | Puede correr en paralelo | Gate para avanzar |
|---|---|---|---|
| 0 — Contratos | 1.1: repositorios ejecutables, lockfiles iniciales, OpenAPI/tipos mínimos, estructura de schemas. | Preparación de datos/contexto demo e inspección de formatos existentes, sin modificar contratos ya usados. | Runtime local/health y contratos acordados. |
| 1 — Fuente real | 1.2: builder + validador del snapshot. Luego 1.3: API coverage y run determinístico. | Con el manifiesto/schema de snapshot fijado, builder y validador pueden ser ramas coordinadas; pruebas de API se preparan con fixtures. | Bundle real pass en integridad y análisis diario devuelve contexto/datos. |
| 2 — Primer slice visual | 1.4: select nativo de `weather_id` y control de fecha + FWI/referencia/diferencia en la única superficie. | UI puede implementarse desde el contrato 1.1 mientras backend completa 1.3; integración requiere endpoint listo. | Usuario puede seleccionar y observar resultado real sin MAS; primer checkpoint demo útil. |
| 3 — MAS real | 1.5: run/audit/eventos; 1.6: OpenAI adapter; 1.7: state machine/roles; 1.8: explicación/traza/SSE. | 1.6 puede empezar al congelarse schemas, en paralelo a persistencia inicial 1.5; UI de trace puede avanzar desde contrato de eventos, luego conectar con 1.7. | Completa el flujo de seis acciones con agente y evidencia verdaderos. |
| 4 — Preparar defensa | 1.9: aceptación end-to-end con OpenAI real. 2.1 + 2.2: procedencia y FIRMS; después 2.4 + 2.5: accesibilidad esencial y ensayo operativo. | 2.1 y 2.2 entre sí; auditorías de accesibilidad por componente; 2.5 puede probar errores/reinicio contra contratos mientras 2.3 se desarrolla. | Bundle y cuenta OpenAI reales verificados; ensayo completo y errores no se ocultan. |

**Trabajo explícitamente diferible:** 2.3 puede diferirse si las estadísticas agregadas FR-8 no se van a mostrar en la defensa; no se difieren las cautelas FIRMS de 2.2. Si el tiempo limita 2.4, reducir primero a bloqueos identificados de teclado/foco/contraste/lectura/responsive y reportar honestamente lo no auditado; no declarar WCAG 2.2 AA sin verificación. Ninguna story P0 del camino 1.1–1.9 se considera diferible para la demo end-to-end.

### Mapa de UX Design Requirements a stories

| UX-DR | Stories |
|---|---|
| UX-DR1–3 | 1.4 |
| UX-DR4–5 | 1.3, 1.4, 1.8 |
| UX-DR6–7 | 2.1, 2.2 |
| UX-DR8 | 1.5, 1.7, 1.8 |
| UX-DR9 | 1.5, 1.7, 1.8, 2.5 |
| UX-DR10 | 1.4, 2.4 |
| UX-DR11–12 | 2.4 |
| UX-DR13 | 1.3, 1.4 |

## Epic 3: Selección geográfica local de ubicaciones meteorológicas

Mejora posterior al MVP, aprobada independientemente de los epics 1 y 2 completados. Conserva la superficie principal UJ-1, los identificadores canónicos y el análisis existente. No amplía las historias anteriores.

### Story 3.1: Seleccionar ubicaciones meteorológicas en mapa local

Como usuario de FireWatch, quiero reconocer y seleccionar una celda de La Rioja en un mapa, para elegir el contexto del análisis sin tener que interpretar solamente un identificador de ubicación.

**Criterios de aceptación:**

1. Al desplegar el mapa, se muestran el contorno provincial y las 169 celdas que intersectan La Rioja, desde el snapshot validado, con procedencia visible. Se distingue el centro geométrico de grilla de la coordenada meteorológica asociada al `weather_id`. La grilla de planificación de 0,25° no se presenta como resolución nativa ERA5.
2. Al seleccionar una celda se transmite su `weather_id` exacto mediante `chooseLocation`; al cambiar el selector HTML se actualiza el resaltado del mapa, sin sustituciones por cercanía.
3. Seleccionar una celda no inicia análisis ni envía POST. Se mantienen las validaciones existentes de ubicación y fecha y la ejecución explícita del análisis.
4. Las 169 ubicaciones siguen disponibles, incluidas las celdas cuyos centros quedan fuera del límite provincial; no se filtran por pertenencia de su centro.
5. El selector HTML sigue siendo completamente operable por teclado. El mapa permite zoom y desplazamiento con controles identificados y foco visible, sin bloquear la navegación.
6. La visualización funciona con recursos locales, sin servicios pagos ni teselas externas. Se carga al solicitarla, limpia listeners al desmontarse y, ante un fallo de carga, permite continuar mediante el selector existente.
7. La presentación se adapta a pantallas estrechas, usa grilla neutra y borde de selección identificable, sin categorías de peligro, mapas de calor, interpolación, pronósticos ni detecciones FIRMS individuales.

**Dependencias:** cobertura canónica de Story 1.3, selección UJ-1 de Story 1.4 y snapshot validado `2026-10-08-2`. No modifica contratos científicos, FWI, agentes ni evidencia histórica.
