# sistema-incendios-forestales
Sistema de análisis de incendios forestales mediante datos satelitales, meteorológicos e inteligencia artificial.

## Runtime local de FireWatch

Story 1.1 incorpora un único proceso FastAPI local, que sirve la SPA compilada en el mismo origen, publica readiness en `/api/health/ready` y expone OpenAPI en `/openapi.json` y `/docs`. Los contratos HTTP autoritativos son los modelos Pydantic de backend; `contracts/openapi.json` y `frontend/src/api/generated.ts` se regeneran desde ellos. El evento `trace-event.v1` se define en `contracts/schemas/trace-event.v1.json`. TypeScript está fijado en 5.9.3 porque `openapi-typescript` declara compatibilidad peer con TypeScript 5.x; la versión 7.0.2 candidata de arquitectura no resuelve ese contrato de dependencias.

### Preparación

Se requiere Python 3.13 o superior, `uv`, Node.js compatible con Vite 8 y npm:

```powershell
uv sync --frozen
npm --prefix frontend ci
uv run python scripts/export_openapi.py
npm --prefix frontend run generate:api
npm --prefix frontend run build
```

### Configuración y arranque

Antes de iniciar, construya una release local del snapshot a partir de las salidas offline existentes:

```powershell
uv run python src/data/build_snapshot.py --release-id 2026-10-08-1
```

El builder consume el límite IGN, la cuadrícula y sus 169 ubicaciones meteorológicas, los CSV gzip meteorológicos/FWI 2020–2025 y el dataset analítico/FIRMS 2021–2025. No llama a servicios de datos. Comprueba esquema y cobertura temporal por año, identidad canónica, duplicados, faltantes, finitud y rangos; contrasta los componentes FWI del dataset analítico con sus salidas fuente, y verifica los totales publicados del período: 370.448 filas diarias, 308.594 celdas-día, 10.956 detecciones y 2.286 celdas-día con detección.

El release builder crea una sola vez `manifest.json`, `data/scientific.sqlite`, `coverage/province.geojson` y `coverage/weather-grid.geojson`; valida el artefacto terminado y se niega a sobrescribir un release existente. Imprime el SHA-256 del manifiesto para fijarlo en `FIREWATCH_SNAPSHOT_MANIFEST_SHA256`. Los bundles generados viven bajo `data/snapshots/`, están fuera de Git y no se reemplazan automáticamente.

Configure `FIREWATCH_SNAPSHOT_DIR` con el directorio del release, `FIREWATCH_SNAPSHOT_VERSION=1.0.0` y el digest impreso. Antes de readiness, el runtime valida el schema/versiones del manifiesto, su digest configurado, tamaño/SHA-256 de cada payload, integridad/esquema SQLite, IDs y fechas diarios, referencias mensuales, geometrías EPSG:4326 y la correspondencia exacta entre SQLite y los 169 features. Abre SQLite con `mode=ro&immutable=1` y lo cierra al apagar. Si alguna verificación falla, el proceso no llega a readiness: no descarga ni repara datos, ni cambia o sustituye el bundle.

El proveedor por defecto es OpenAI. Selecciónelo solo con `OPENAI_API_KEY`, `FIREWATCH_OPENAI_MODEL`, `FIREWATCH_LLM_TIMEOUT_SECONDS`, `FIREWATCH_LLM_MAX_RETRIES` (0–2) y `FIREWATCH_LLM_MAX_OUTPUT_TOKENS_PER_RUN` válidos. Para desarrollo sin llamadas externas, `FIREWATCH_LLM_PROVIDER=mock` debe seleccionarse explícitamente; nunca se usa como fallback.

Con la configuración completa, el comando documentado de ejecución es:

```powershell
uv run sistema-incendios-forestales
```

El servidor escucha solo en `127.0.0.1:8000` y se ejecuta con un worker. `FIREWATCH_AUDIT_DB` permite elegir la ruta de la base local de análisis; su valor predeterminado es `data/firewatch-audit.sqlite`. La base de auditoría es independiente del snapshot científico, que permanece read-only.

`GET /api/coverage` entrega el GeoJSON de las 169 ubicaciones, fechas y procedencia del bundle. `POST /api/analyses` recibe `{ "weather_id": "...", "date": "YYYY-MM-DD" }` y responde `202` con el `analysis_id`; `GET /api/analyses/{analysis_id}` permite consultar el estado y resultado diario. Cada run consulta exactamente una ubicación y fecha; no interpola ni agrega FWI entre días. El resultado incluye meteorología, componentes FWI, referencia mediana de la misma ubicación y mes, diferencia descriptiva, cantidad `firms_count` y referencias reales al snapshot/manifest. Cero FIRMS asociado no significa ausencia de incendio. Las ausencias se expresan como `null` con motivo, nunca como cero.

La primera implementación persiste `run_queued`, `run_started`, `analysis_core_result_persisted` y el evento terminal junto con la proyección del resultado; no crea eventos de agente. La transacción de finalización confirma conjuntamente resultado/proyección y eventos de inicio, resultado central y terminal.

### Pruebas focalizadas de Stories 1.1–1.3

```powershell
uv run pytest tests/test_analysis_api.py tests/test_runtime_contracts.py tests/test_snapshot_bundle.py
npm --prefix frontend run build
```
