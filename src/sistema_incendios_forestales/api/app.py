from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3
from typing import AsyncIterator
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from sistema_incendios_forestales.api.config import (
    RuntimeConfigurationError,
    load_settings,
)
from sistema_incendios_forestales.api.contracts import (
    CONTRACT_MODELS,
    APIError,
    AnalysisAccepted,
    AnalysisRequest,
    AnalysisResult,
    CoverageResponse,
    ErrorResponse,
    ReadinessResponse,
)
from sistema_incendios_forestales.analysis import (
    AnalysisContextError,
    build_deterministic_result,
    validate_analysis_request,
)
from sistema_incendios_forestales.audit import AuditStore
from sistema_incendios_forestales.api.config import RuntimeSettings
from sistema_incendios_forestales.llm import LLMProvider, create_llm_provider
from sistema_incendios_forestales.mas import (
    DeterministicMASOrchestrator,
    MASExecutionError,
)
from sistema_incendios_forestales.snapshot import SnapshotValidationError, validate_snapshot
from sistema_incendios_forestales.snapshot import ValidatedSnapshot

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

    llm_provider = create_llm_provider(settings)
    try:
        audit_store = AuditStore.open(settings.audit_db_path)
    except (OSError, sqlite3.DatabaseError, RuntimeError):
        snapshot.close()
        raise

    application.state.settings = settings
    application.state.snapshot = snapshot
    application.state.audit_store = audit_store
    application.state.llm_provider = llm_provider
    try:
        yield
    finally:
        audit_store.close()
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
    if isinstance(error.detail, dict) and {"code", "message", "details"} <= set(
        error.detail
    ):
        api_error = APIError.model_validate(error.detail)
    else:
        api_error = APIError(
            code=f"HTTP_{error.status_code}",
            message=str(error.detail),
            details={},
        )
    response = ErrorResponse(
        error=api_error,
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


@app.get("/api/coverage", response_model=CoverageResponse)
async def get_coverage(request: Request) -> CoverageResponse:
    snapshot = request.app.state.snapshot
    manifest = snapshot.manifest
    return CoverageResponse(
        type="FeatureCollection",
        snapshot_version=manifest["bundle_version"],
        release_id=manifest["release_id"],
        provenance=manifest["provenance"],
        source_references=manifest["source_references"],
        date_coverage=manifest["date_coverage"],
        features=snapshot.coverage["features"],
    )


async def _execute_analysis(
    audit_store: AuditStore,
    snapshot: ValidatedSnapshot,
    settings: RuntimeSettings,
    llm_provider: LLMProvider,
    analysis_id: UUID,
    analysis_request: AnalysisRequest,
) -> None:
    def collaborate(result: AnalysisResult) -> AnalysisResult:
        token_budget = settings.llm_max_output_tokens_per_run or 10_000
        orchestrator = DeterministicMASOrchestrator(
            provider=llm_provider,
            audit_store=audit_store,
            token_budget=token_budget,
        )
        try:
            return orchestrator.run(result)
        except MASExecutionError as error:
            return result.model_copy(
                update={
                    "state": "partial",
                    "error_code": error.code,
                    "error_message": str(error),
                    "affected_outputs": error.affected_outputs,
                    "provider_metadata": error.provider_metadata
                    or [
                        {
                            "provider": settings.llm_provider,
                            "model": settings.openai_model or "explicit-mock",
                        }
                    ],
                }
            )

    audit_store.execute(
        analysis_id,
        lambda: build_deterministic_result(
            snapshot,
            analysis_request,
            analysis_id,
            settings.snapshot_manifest_sha256,
        ),
        collaborate=collaborate,
    )


@app.post(
    "/api/analyses",
    response_model=AnalysisAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_analysis(
    analysis_request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> AnalysisAccepted:
    snapshot = request.app.state.snapshot
    try:
        validate_analysis_request(snapshot, analysis_request)
    except AnalysisContextError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": error.code, "message": str(error), "details": {}},
        ) from error

    analysis_id = uuid4()
    audit_store = request.app.state.audit_store
    audit_store.create_queued(analysis_id, analysis_request)
    background_tasks.add_task(
        _execute_analysis,
        audit_store,
        snapshot,
        request.app.state.settings,
        request.app.state.llm_provider,
        analysis_id,
        analysis_request,
    )
    return AnalysisAccepted(analysis_id=analysis_id, state="queued")


@app.get("/api/analyses/{analysis_id}", response_model=AnalysisResult)
async def get_analysis(analysis_id: str, request: Request) -> AnalysisResult:
    try:
        parsed_analysis_id = UUID(analysis_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "INVALID_ANALYSIS_ID",
                "message": "analysis_id must be a UUID.",
                "details": {},
            },
        ) from error
    result = request.app.state.audit_store.get(parsed_analysis_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ANALYSIS_NOT_FOUND",
                "message": "No analysis exists for this analysis_id.",
                "details": {},
            },
        )
    return result


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
