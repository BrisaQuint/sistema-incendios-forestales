from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from sistema_incendios_forestales.api.config import (
    RuntimeConfigurationError,
    load_settings,
)
from sistema_incendios_forestales.api.contracts import (
    CONTRACT_MODELS,
    APIError,
    ErrorResponse,
    ReadinessResponse,
)
from sistema_incendios_forestales.snapshot import SnapshotValidationError, validate_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    try:
        settings = load_settings()
    except RuntimeConfigurationError as error:
        raise RuntimeError(str(error)) from error

    if not (FRONTEND_DIST / "index.html").is_file():
        raise RuntimeError(
            f"Frontend build is missing: {FRONTEND_DIST / 'index.html'}. "
            "Run the documented frontend build before starting FireWatch."
        )

    try:
        snapshot = validate_snapshot(
            settings.snapshot_dir,
            expected_version=settings.snapshot_version,
            expected_manifest_sha256=settings.snapshot_manifest_sha256,
        )
    except SnapshotValidationError as error:
        raise RuntimeError(str(error)) from error

    application.state.settings = settings
    application.state.snapshot = snapshot
    try:
        yield
    finally:
        snapshot.close()


app = FastAPI(
    title="FireWatch API",
    version="0.1.0",
    description="Local API and typed contracts for the FireWatch analysis runtime.",
    lifespan=lifespan,
)


@app.middleware("http")
async def assign_request_id(request: Request, call_next):
    request_id = uuid4()
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = str(request_id)
    return response


@app.exception_handler(RequestValidationError)
async def request_validation_error(
    request: Request, error: RequestValidationError
) -> JSONResponse:
    response = ErrorResponse(
        error=APIError(
            code="INVALID_REQUEST",
            message="The request does not match the API contract.",
            details={
                "issues": [
                    {
                        "location": list(issue["loc"]),
                        "message": issue["msg"],
                        "code": issue["type"],
                    }
                    for issue in error.errors()
                ]
            },
        ),
        request_id=request.state.request_id,
    )
    return JSONResponse(status_code=422, content=response.model_dump(mode="json"))


@app.exception_handler(HTTPException)
async def http_error(request: Request, error: HTTPException) -> JSONResponse:
    response = ErrorResponse(
        error=APIError(
            code=f"HTTP_{error.status_code}",
            message=str(error.detail),
            details={},
        ),
        request_id=request.state.request_id,
    )
    return JSONResponse(status_code=error.status_code, content=response.model_dump(mode="json"))


@app.get("/api/health/ready", response_model=ReadinessResponse)
async def readiness(request: Request) -> ReadinessResponse:
    snapshot = request.app.state.snapshot
    return ReadinessResponse(
        status="ready",
        snapshot_version=snapshot.manifest["bundle_version"],
    )


@app.get("/", include_in_schema=False)
@app.get("/{requested_path:path}", include_in_schema=False)
async def serve_frontend(requested_path: str = ""):
    if requested_path == "api" or requested_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found.")

    dist_directory = FRONTEND_DIST.resolve()
    requested_file = (dist_directory / requested_path).resolve()
    if requested_path and requested_file.is_relative_to(dist_directory) and requested_file.is_file():
        return FileResponse(requested_file)

    index_file = dist_directory / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=503, detail="Frontend build is unavailable.")
    return FileResponse(index_file)


def _add_contract_schemas(openapi: dict) -> None:
    components = openapi.setdefault("components", {}).setdefault("schemas", {})
    for model in CONTRACT_MODELS:
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        definitions = schema.pop("$defs", {})
        components.update(definitions)
        components[model.__name__] = schema


def custom_openapi() -> dict:
    if app.openapi_schema is not None:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    app.openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    _add_contract_schemas(app.openapi_schema)
    return app.openapi_schema


app.openapi = custom_openapi
