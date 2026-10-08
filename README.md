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

Antes de iniciar, aprovisione un snapshot local con `manifest.json`, `data/scientific.sqlite`, `coverage/province.geojson` y `coverage/weather-grid.geojson`. Configure `FIREWATCH_SNAPSHOT_DIR`, `FIREWATCH_SNAPSHOT_VERSION` y `FIREWATCH_SNAPSHOT_MANIFEST_SHA256`. El runtime no está listo si falta cualquiera de estos archivos o valores.

El proveedor por defecto es OpenAI. Selecciónelo solo con `OPENAI_API_KEY`, `FIREWATCH_OPENAI_MODEL`, `FIREWATCH_LLM_TIMEOUT_SECONDS`, `FIREWATCH_LLM_MAX_RETRIES` (0–2) y `FIREWATCH_LLM_MAX_OUTPUT_TOKENS_PER_RUN` válidos. Para desarrollo sin llamadas externas, `FIREWATCH_LLM_PROVIDER=mock` debe seleccionarse explícitamente; nunca se usa como fallback.

Con la configuración completa, el comando documentado de ejecución es:

```powershell
uv run sistema-incendios-forestales
```

El servidor escucha solo en `127.0.0.1:8000` y se ejecuta con un worker. En esta story readiness comprueba configuración y presencia de los archivos requeridos; la validación de versión, digest, esquema y contenido íntegro del snapshot corresponde a Story 1.2.

### Pruebas focalizadas de Story 1.1

```powershell
uv run pytest tests/test_runtime_contracts.py
npm --prefix frontend run build
```
