# FireWatch — Sistema de análisis de incendios forestales

Sistema de análisis histórico de condiciones meteorológicas y detecciones satelitales de incendios forestales en La Rioja, Argentina. Integra FWI, FIRMS, backend FastAPI, interfaz React y orquestación de agentes de IA para explicaciones trazables. **No es un sistema de predicción de incendios ni presenta el FWI como probabilidad de ocurrencia.**

> **Alcance de esta guía:** el código y las pruebas se versionan aquí; el snapshot científico no se distribuye mediante Git. Para iniciar la aplicación se necesita el snapshot validado 2026-10-08-2. La base de auditoría histórica es independiente. Instalar dependencias no equivale a reproducir íntegramente una ejecución histórica.

## Inicio rápido: ejecución local con snapshot disponible

Guía para **Windows y PowerShell**, el entorno usado en el proyecto. No requiere reconstruir fuentes científicas originales.

**Requisitos:** Git, Python 3.13 o superior, uv (https://docs.astral.sh/uv/), Node.js compatible con Vite 8 y npm. Se requiere conexión para descargar dependencias la primera vez. Python y las dependencias están especificados en .python-version y uv.lock; las del frontend, en frontend/package-lock.json.

**1. Clonar e instalar:**

~~~powershell
git clone https://github.com/BrisaQuint/sistema-incendios-forestales.git
cd sistema-incendios-forestales
uv sync --frozen
npm --prefix frontend ci
npm --prefix frontend run build
~~~

**2. Provisionar el snapshot científico de manera independiente:**

Se requiere el release validado 2026-10-08-2 con esta estructura:

~~~text
data/
└── snapshots/
    └── 2026-10-08-2/
        ├── manifest.json
        ├── data/
        │   └── scientific.sqlite
        └── coverage/
            ├── province.geojson
            └── weather-grid.geojson
~~~

**Distribución:** el paquete no está en este repositorio. Su enlace de descarga pública está **pendiente de autorización y publicación**, sujetas a la revisión de procedencia y licencias. Hasta entonces la instalación con datos científicos requiere un ejemplar facilitado por el equipo. Sin él, el backend no iniciará.

La huella SHA-256 del manifest.json de la versión validada es:

~~~text
45fc6de5ca472435c954e93a8a276660907bad0b4e7b20b47668fbd495da833a
~~~

Comprobar el archivo local:

~~~powershell
(Get-FileHash 'data/snapshots/2026-10-08-2/manifest.json' -Algorithm SHA256).Hash.ToLower()
~~~

El backend verifica además los hashes de los otros payloads, esquema, cobertura y consistencia interna antes de declarar disponibilidad.

**3. Configurar en la misma sesión PowerShell:** la aplicación no carga automáticamente archivos .env.

~~~powershell
$env:FIREWATCH_SNAPSHOT_DIR = (Resolve-Path 'data/snapshots/2026-10-08-2').Path
$env:FIREWATCH_SNAPSHOT_VERSION = '1.0.0'
$env:FIREWATCH_SNAPSHOT_MANIFEST_SHA256 = '45fc6de5ca472435c954e93a8a276660907bad0b4e7b20b47668fbd495da833a'
$env:FIREWATCH_AUDIT_DB = (Join-Path (Get-Location).Path 'data/firewatch-audit.sqlite')
$env:FIREWATCH_LLM_PROVIDER = 'mock'
~~~

Si no existe la base de auditoría, el sistema crea una nueva al arrancar; **esa base no contiene la ejecución histórica de la defensa**. El modo mock no trae respuestas de los roles preconfiguradas: no utilizar «Ejecutar este día» para intentar reproducir la explicación OpenAI real de aceptación. Una nueva ejecución con proveedor OpenAI requiere credenciales y configuración propias y puede tener costo.

**4. Iniciar y verificar:**

~~~powershell
uv run sistema-incendios-forestales
~~~

En una segunda consola:

~~~powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/health/ready'
~~~

Abrir http://127.0.0.1:8000/ y explorar el mapa, cobertura, fechas y hallazgos exploratorios. La documentación de la API se encuentra en http://127.0.0.1:8000/docs. Si falla el inicio, revisar rutas, huella del manifiesto, build del frontend y puerto 8000.

**5. Verificar pruebas y compilación:**

La suite automatizada del producto se encuentra en `tests/`. La configuración de pytest en `pyproject.toml` limita la colección predeterminada a esa carpeta; `src/data/test_fwi_components.py` es un experimento exploratorio heredado que depende de una interfaz histórica de la biblioteca científica y **no** es una prueba de la aplicación.

~~~powershell
uv run pytest
npm --prefix frontend run build
~~~

## Política de datos científicos y alcance de replicabilidad

La exclusión de data/raw/, data/processed/ y data/snapshots/ mediante .gitignore es **intencional**. El código, scripts de procesamiento, contratos, pruebas y dependencias se versionan en Git; los datos se administran como artefactos independientes.

Esta decisión protege la **integridad y trazabilidad científica**: la aplicación valida el manifiesto, huellas SHA-256, esquemas y cobertura geográfica/temporal del release antes de iniciar, y abre el SQLite científico de solo lectura. El snapshot fija el contexto de las consultas históricas y evita sustituirlo silenciosamente por datos recalculados. La construcción de nuevos snapshots es otro procedimiento, no parte del inicio rápido.

**Niveles diferenciados de reproducción:**

- **Código y pruebas:** accesibles desde el repositorio.
- **Ejecución funcional con datos históricos:** requiere el snapshot científico separado y debidamente validado; no se garantiza con el clon del código solamente.
- **Recuperación exacta de la demostración con IA:** exige además la base de auditoría histórica (no incluida en Git). La base nueva solo registra nuevas ejecuciones.
- **Reconstrucción científica desde fuentes originales:** depende de las entradas originales/procesadas, las condiciones de acceso y el pipeline; no queda garantizada únicamente con el repositorio.

No se publican automáticamente datasets de origen, el SQLite histórico de auditoría, claves privadas ni registros locales. Antes de distribuir el ZIP del snapshot, se deben comprobar licencias, procedencia y permisos, mantener la estructura interna del bundle y confirmar su validación de integridad. El enlace al paquete complementario quedará pendiente hasta completar esa revisión.

**Licencias/publicación:** antes de cambiar el repositorio a público, el equipo debe revisar el historial de commits y las referencias a datos personales, credenciales y terceros; también debe seleccionar una licencia explícita para el código propio y comprobar las condiciones de los componentes incorporados. No se presupone autorización para redistribuir todo el material.

**Créditos y atribuciones existentes:** consultar [avisos de terceros](THIRD_PARTY_NOTICES.md) para BMAD, cffdrs_py y fuentes científicas. La licencia del código propio de FireWatch sigue pendiente de decisión de sus autores.


### Revisión de secretos en el repositorio

Desde la raíz del proyecto, ejecutar `gitleaks git . --log-opts="--all" --redact`. La configuración `.gitleaks.toml` conserva las reglas predeterminadas y exceptúa exclusivamente un falso positivo de `generic-api-key` en la fila `key-screens` del manifiesto instalado por BMAD: el campo es una huella SHA-256 de archivo. La excepción exige simultáneamente la ruta precisa y el formato completo de esa fila; no exime otros datos ni otros tipos de alertas. Cualquier nuevo hallazgo debe examinarse antes de publicar.

## Detalles técnicos, arquitectura y evidencia

La documentación técnica original se conserva a continuación. Véanse también contracts/, docs/bmad/ y docs/defense-readiness.md para contratos, decisiones de diseño, validaciones y límites funcionales.

---

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
