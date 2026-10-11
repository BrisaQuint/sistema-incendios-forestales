# sistema-incendios-forestales
Sistema de análisis de incendios forestales mediante datos satelitales, meteorológicos e inteligencia artificial.

## Runtime local de FireWatch

Story 1.1 incorpora un único proceso FastAPI local, que sirve la SPA compilada en el mismo origen, publica readiness en `/api/health/ready` y expone OpenAPI en `/openapi.json` y `/docs`. Los contratos HTTP autoritativos son los modelos Pydantic de backend; `contracts/openapi.json` y `frontend/src/api/generated.ts` se regeneran desde ellos. El evento `trace-event.v1` se define en `contracts/schemas/trace-event.v1.json`. TypeScript está fijado en 5.9.3 porque `openapi-typescript` declara compatibilidad peer con TypeScript 5.x; la versión 7.0.2 candidata de arquitectura no resuelve ese contrato de dependencias.

### Preparación

Se requiere Python 3.13 o superior, `uv`, Node.js compatible con Vite 8 y npm:

```powershell
uv sync --frozen
npm --prefix frontend ci
npm --prefix frontend run build
```

### Configuración y arranque

Para la defensa, reutilice el snapshot validado **`2026-10-08-2`**. No ejecute el builder ni regenere los datos. El snapshot y la auditoría histórica están fuera de Git: deben estar disponibles en el equipo de defensa, junto con las dependencias y el build, antes de trabajar sin conexión externa.

Desde la raíz del repositorio, configure la sesión de PowerShell para consultar resultados persistidos sin habilitar llamadas reales:

```powershell
$env:FIREWATCH_SNAPSHOT_DIR = (Resolve-Path 'data/snapshots/2026-10-08-2').Path
$env:FIREWATCH_SNAPSHOT_VERSION = '1.0.0'
$env:FIREWATCH_SNAPSHOT_MANIFEST_SHA256 = '45fc6de5ca472435c954e93a8a276660907bad0b4e7b20b47668fbd495da833a'
$env:FIREWATCH_AUDIT_DB = (Resolve-Path 'data/firewatch-audit.sqlite').Path
$env:FIREWATCH_LLM_PROVIDER = 'mock'
```

El proveedor mock aquí es explícito y no se invoca al recuperar un resultado mediante GET; no reemplaza la explicación OpenAI guardada. No pulse «Ejecutar este día»: el mock del arranque no tiene respuestas de roles preconfiguradas y no constituye otra ejecución de aceptación. La aplicación no carga automáticamente un archivo `.env`; configure las variables en la sesión o mediante el lanzador autorizado.

El builder consume el límite IGN, la cuadrícula y sus 169 ubicaciones meteorológicas, los CSV gzip meteorológicos/FWI 2020–2025 y el dataset analítico/FIRMS 2021–2025. No llama a servicios de datos. Comprueba esquema y cobertura temporal por año, identidad canónica, duplicados, faltantes, finitud y rangos; contrasta los componentes FWI del dataset analítico con sus salidas fuente, y verifica los totales publicados del período: 370.448 filas diarias, 308.594 celdas-día, 10.956 detecciones y 2.286 celdas-día con detección.

El release builder crea una sola vez `manifest.json`, `data/scientific.sqlite`, `coverage/province.geojson` y `coverage/weather-grid.geojson`; valida el artefacto terminado y se niega a sobrescribir un release existente. Imprime el SHA-256 del manifiesto para fijarlo en `FIREWATCH_SNAPSHOT_MANIFEST_SHA256`. Los bundles generados viven bajo `data/snapshots/`, están fuera de Git y no se reemplazan automáticamente.

Configure `FIREWATCH_SNAPSHOT_DIR` con el directorio del release, `FIREWATCH_SNAPSHOT_VERSION=1.0.0` y el digest impreso. Antes de readiness, el runtime valida el schema/versiones del manifiesto, su digest configurado, tamaño/SHA-256 de cada payload, integridad/esquema SQLite, IDs y fechas diarios, referencias mensuales, geometrías EPSG:4326 y la correspondencia exacta entre SQLite y los 169 features. Abre SQLite con `mode=ro&immutable=1` y lo cierra al apagar. Si alguna verificación falla, el proceso no llega a readiness: no descarga ni repara datos, ni cambia o sustituye el bundle.

Solo para una nueva ejecución real expresamente autorizada, seleccione `FIREWATCH_LLM_PROVIDER=openai` y configure `OPENAI_API_KEY`, `FIREWATCH_OPENAI_MODEL`, `FIREWATCH_LLM_TIMEOUT_SECONDS` (finito/positivo), `FIREWATCH_LLM_MAX_RETRIES` (0–2) y `FIREWATCH_LLM_MAX_OUTPUT_TOKENS_PER_RUN` (entero positivo). No es necesario para recuperar la evidencia histórica durante la defensa. El adaptador usa Structured Outputs con JSON Schema y valida localmente cada respuesta; clasifica errores sin respuesta de reserva y solo reintenta fallos transitorios. El SDK no realiza reintentos adicionales. Una instancia de `LLMRunBudget` limita conjuntamente las llamadas del análisis. Para desarrollo/tests, seleccione explícitamente `FIREWATCH_LLM_PROVIDER=mock` y configure respuestas mock para cada schema utilizado. No se usa MockLLM como fallback.

El puerto `LLMProvider` mantiene el dominio desacoplado del SDK. Se conservan proveedor, modelo, versiones de prompt/schema e identificador/uso de la respuesta como metadatos permitidos; no se registran la clave, los prompts ni razonamiento oculto. Esta integración no calcula ni modifica FWI ni evidencia científica.

Con la configuración completa, el comando documentado de ejecución es:

```powershell
uv run sistema-incendios-forestales
```

Desde una segunda consola, compruebe `Invoke-RestMethod 'http://127.0.0.1:8000/api/health/ready'` y abra `http://127.0.0.1:8000/?analysis_id=73356254-ffa8-4397-b208-938579eee91d`. Se recupera la ejecución real histórica de Story 1.9: ubicación `-27.50000_-68.50000`, fecha `2021-01-01`, FWI mostrado 57,34, explicación aprobada y 11 eventos. Puede consultar su traza con GET `/api/analyses/73356254-ffa8-4397-b208-938579eee91d/trace`. No se crea otro análisis ni se repiten llamadas LLM.

Los selectores y el mapa no se restauran necesariamente al contexto del resultado guardado; la interfaz lo advierte. Use otra pestaña para demostrar selección, ya que cambiarla limpia el resultado visible. Los hallazgos globales se consultan sin análisis mediante `/api/study/exploratory`.

Si el puerto está ocupado, inspeccione `Get-NetTCPConnection -LocalPort 8000` y acuerde qué instancia utilizar; no finalice procesos ajenos ni lance otra instancia contra la misma auditoría. Apague únicamente la consola propia con Ctrl+C. El ensayo de cierre automatizado usa `should_exit`; Ctrl+C interactivo en el equipo de defensa sigue pendiente de ensayo. La configuración inválida impide readiness: revise rutas, versión, digest, build y permisos sin imprimir secretos.

El servidor escucha solo en `127.0.0.1:8000` y se ejecuta con un worker. `FIREWATCH_AUDIT_DB` permite elegir la ruta de la base local de análisis; su valor predeterminado es `data/firewatch-audit.sqlite`. La base de auditoría es independiente del snapshot científico, que permanece read-only.

Se conserva íntegramente la auditoría durante el desarrollo y la defensa: **no hay purga automática, compactación ni retención temporal configurable implementada**. Esta decisión aprobada sustituye el objetivo original de 30 días; la diferencia permanece registrada en [la consolidación documental](docs/defense-readiness.md), sin borrar el compromiso de los documentos de planificación. Startup puede aplicar migraciones y cerrar ejecuciones activas interrumpidas; consultar por GET no equivale a abrir toda la aplicación en modo read-only.

Los logs operativos tienen rotación independiente: `FIREWATCH_LOG_PATH` (por defecto `data/logs/firewatch.log`), `FIREWATCH_LOG_MAX_BYTES` (1048576) y `FIREWATCH_LOG_BACKUP_COUNT` (3 copias más el archivo actual). No se garantiza la retención de stdout/stderr o handlers externos. El formato excluye mensajes libres, prompts, secretos y razonamiento oculto, a costa de menor detalle diagnóstico.

La superficie principal obtiene `GET /api/coverage` y presenta el selector nativo para las 169 ubicaciones, con `weather_id` y centro legibles. Los controles nativos permiten elegir un rango y navegar fecha a fecha; “Ejecutar este día” envía exactamente la feature seleccionada y el día visible. Si una fecha queda fuera de la cobertura de esa ubicación, la interfaz conserva la selección, explica el problema y no la sustituye. Cada día ejecutado obtiene su propio análisis: no se calcula ni muestra un FWI agregado para el período.

`POST /api/analyses` recibe `{ "weather_id": "...", "date": "YYYY-MM-DD" }` y responde `202` con el `analysis_id`; `GET /api/analyses/{analysis_id}` permite consultar el estado y resultado diario. El resultado incluye meteorología, componentes FWI, referencia mediana de la misma ubicación y mes, diferencia descriptiva, cantidad `firms_count` y referencias reales al snapshot/manifest. Cero FIRMS asociado no significa ausencia de incendio. Las ausencias se expresan como `null` con motivo, nunca como cero. FWI se rotula como peligro meteorológico, no probabilidad; la síntesis describe la comparación sin categorías locales de peligro.

La base de auditoría usa migraciones SQLite ordenadas y versionadas, aplicadas durante startup antes de readiness. Cada evento es inmutable, lleva secuencia consecutiva por run, timestamp UTC y clave idempotente. Las transiciones de estado y sus eventos se confirman atómicamente; `analysis_core_result_persisted` se compromete junto con el resultado científico antes de cualquier contextualización. Los fallos determinísticos registran `tool_failed` con tarea/error/salida afectados y terminan en `failed` cuando no hay FWI utilizable. Al reiniciar, los runs `queued`/`running` sin terminal se cierran con `run_interrupted` más `run_failed` o `run_partial` según exista FWI central persistido; el runtime no repite el trabajo interrumpido.

Story 1.7 ejecuta una state machine Python fija: contextualizador → validador → explicador, con como máximo una nueva intervención de contextualización si el validador solicita revisión. Solo un resultado aprobado llega al explicador; un segundo rechazo o cualquier fallo de rol termina `partial` y conserva el FWI, sin una explicación no aprobada. Los siete schemas versionados `evidence-bundle.v1` y de entradas/salidas de los tres roles están en `contracts/schemas/`. Las referencias de evidencia se reescriben como IDs de alcance por análisis, se validan contra el registro del run y no pueden resolver a otro `analysis_id`. Cada llamada genera eventos persistidos de inicio y terminal con ID de intervención, rol, tarea y referencias. Los roles reciben únicamente JSON explícito, sin herramientas ni acceso a SQL, filesystem o APIs. Las respuestas interpretativas no pueden introducir cantidades numéricas ni cambiar el cálculo/evidencia determinísticos. La API incluye explicación aprobada y referencias solo tras completar el flujo.

`GET /api/analyses/{analysis_id}/trace` devuelve únicamente la traza ya persistida, ordenada y deduplicada por análisis/secuencia, con las referencias de evidencia limitadas al run. `GET /api/analyses/{analysis_id}/trace/events` ofrece SSE durable con IDs de secuencia; el navegador puede reanudar desde `Last-Event-ID` sin volver a ejecutar agentes. Desconectar el stream no cancela el análisis ni crea historial global. La interfaz separa observación, resultado determinístico e interpretación aprobada y distingue la traza pendiente, disponible, incompleta o no disponible, además de los estados completo, parcial y error.

### Pruebas focalizadas de Stories 1.1–1.8

```powershell
uv run pytest tests/test_audit_store.py tests/test_analysis_api.py tests/test_runtime_contracts.py tests/test_snapshot_bundle.py tests/test_llm_provider.py tests/test_mas_orchestrator.py tests/test_trace_api.py
npm --prefix frontend run build
```
