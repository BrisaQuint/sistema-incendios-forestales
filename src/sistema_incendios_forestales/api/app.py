from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3
import asyncio
from typing import AsyncIterator
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

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
    ProvinceBoundaryResponse,
    ExploratoryResults,
    ErrorResponse,
    ReadinessResponse,
    TraceEventView,
    TraceResponse,
)
from sistema_incendios_forestales.analysis import (
    AnalysisContextError,
    build_deterministic_result,
    build_exploratory_results,
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
        application.state.exploratory_results = build_exploratory_results(
            snapshot, settings.snapshot_manifest_sha256
        )
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


@app.get("/api/coverage/province", response_model=ProvinceBoundaryResponse)
async def get_province_boundary(request: Request) -> ProvinceBoundaryResponse:
    snapshot = request.app.state.snapshot
    return ProvinceBoundaryResponse(
        type="FeatureCollection", release_id=snapshot.release_id,
        features=snapshot.province["features"],
    )


@app.get("/api/study/exploratory", response_model=ExploratoryResults)
async def get_exploratory_results(request: Request) -> ExploratoryResults:
    return request.app.state.exploratory_results


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


def _parse_analysis_id(analysis_id: str) -> UUID:
    try:
        return UUID(analysis_id)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "INVALID_ANALYSIS_ID",
                "message": "analysis_id must be a UUID.",
                "details": {},
            },
        ) from error


def _trace_view(
    parsed_analysis_id: UUID,
    events,
    analysis: AnalysisResult,
) -> TraceResponse:
    result = analysis.result
    evidence_labels: dict[str, str] = {}
    if result is not None:
        source_labels = {
            "weather_daily": "Datos meteorológicos y FWI observados del snapshot",
            "monthly_fwi_reference": "Referencia histórica local-mensual",
            "manifest": "Manifiesto y procedencia del snapshot",
        }
        for index, source_ref in enumerate(result.evidence_refs, start=1):
            if ":weather_daily:" in source_ref:
                source_type = "weather_daily"
            elif ":monthly_fwi_reference:" in source_ref:
                source_type = "monthly_fwi_reference"
            else:
                source_type = "manifest"
            evidence_labels[
                f"analysis:{parsed_analysis_id}:evidence:{index:03d}"
            ] = source_labels[source_type]
        if analysis.explanation:
            for event in events:
                if (
                    event.event_type == "intervention_completed"
                    and event.agent_role == "contextualizer"
                    and event.output_ref
                ):
                    evidence_labels[event.output_ref] = (
                        event.result_summary or "Contextualización registrada"
                    )

    views: list[TraceEventView] = []
    for event in sorted(
        { (event.analysis_id, event.sequence): event for event in events }.values(),
        key=lambda item: (str(item.analysis_id), item.sequence),
    ):
        run_scoped_refs = list(
            dict.fromkeys(
                [
                    *(event.input_evidence_refs or []),
                    *(event.evidence_refs or []),
                    *(event.issue_refs or []),
                    *([event.output_ref] if event.output_ref else []),
                ]
            )
        )
        resolved = {
            reference: evidence_labels[reference]
            for reference in run_scoped_refs
            if reference in evidence_labels
            and reference.startswith(f"analysis:{parsed_analysis_id}:")
        }
        status_value = {
            "intervention_started": "started",
            "intervention_completed": "completed",
            "intervention_failed": "failed",
        }.get(event.event_type, "recorded")
        views.append(
            TraceEventView(
                analysis_id=event.analysis_id,
                sequence=event.sequence,
                event_type=event.event_type,
                occurred_at=event.occurred_at,
                intervention_id=event.intervention_id,
                agent_role=event.agent_role,
                task=event.task,
                status=status_value,
                result_summary=event.result_summary,
                evidence_refs=[
                    reference
                    for reference in run_scoped_refs
                    if reference.startswith(f"analysis:{parsed_analysis_id}:")
                ],
                evidence=resolved,
                tool_name=event.tool_name,
                error_code=event.error_code,
                affected_outputs=event.affected_outputs or [],
            )
        )
    earliest, latest = (
        (views[0].sequence, views[-1].sequence) if views else (None, None)
    )
    if not views:
        trace_status = (
            "unavailable"
            if analysis.state in {"completed", "partial", "failed"}
            else "not_yet_recorded"
        )
    elif analysis.state in {"queued", "running"}:
        trace_status = "incomplete"
    elif analysis.state in {"partial", "failed"}:
        trace_status = "incomplete"
    elif [view.sequence for view in views] != list(
        range(views[0].sequence, views[-1].sequence + 1)
    ) or views[0].sequence != 1:
        trace_status = "incomplete"
    else:
        trace_status = "available"
    return TraceResponse(
        analysis_id=parsed_analysis_id,
        run_state=analysis.state,
        trace_status=trace_status,
        earliest_sequence=earliest,
        latest_sequence=latest,
        events=views,
    )


@app.get(
    "/api/analyses/{analysis_id}/trace",
    response_model=TraceResponse,
    name="get_analysis_trace",
)
async def get_analysis_trace(analysis_id: str, request: Request) -> TraceResponse:
    parsed_id = _parse_analysis_id(analysis_id)
    store: AuditStore = request.app.state.audit_store
    analysis = store.get(parsed_id)
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ANALYSIS_NOT_FOUND",
                "message": "No analysis exists for this analysis_id.",
                "details": {},
            },
        )
    return _trace_view(parsed_id, store.events(parsed_id), analysis)


def _parse_trace_cursor(value: str | None) -> int:
    if value is None or value == "":
        return 0
    if not value.isascii() or not value.isdecimal():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_TRACE_CURSOR",
                "message": "Last-Event-ID must be a non-negative sequence integer.",
                "details": {},
            },
        )
    return int(value)


@app.get(
    "/api/analyses/{analysis_id}/trace/events",
    name="stream_analysis_trace",
)
async def stream_analysis_trace(
    analysis_id: str,
    request: Request,
) -> StreamingResponse:
    parsed_id = _parse_analysis_id(analysis_id)
    store: AuditStore = request.app.state.audit_store
    if store.get(parsed_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ANALYSIS_NOT_FOUND",
                "message": "No analysis exists for this analysis_id.",
                "details": {},
            },
        )
    cursor = _parse_trace_cursor(request.headers.get("last-event-id"))
    earliest, latest = store.event_bounds(parsed_id)
    if latest is not None and cursor > latest:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TRACE_CURSOR_IN_FUTURE",
                "message": "The requested trace cursor is newer than the durable trace.",
                "details": {"latest_sequence": latest},
            },
        )
    if earliest is not None and cursor < earliest - 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TRACE_RESET_REQUIRED",
                "message": "The requested cursor predates the retained durable trace.",
                "details": {"earliest_sequence": earliest},
            },
        )

    async def event_stream():
        nonlocal cursor
        while True:
            if await request.is_disconnected():
                return
            persisted = store.events_after(parsed_id, cursor)
            if persisted:
                deduplicated = {
                    (event.analysis_id, event.sequence): event for event in persisted
                }
                for (event_analysis_id, sequence), event in sorted(
                    deduplicated.items(),
                    key=lambda item: (str(item[0][0]), item[0][1]),
                ):
                    if event_analysis_id != parsed_id or sequence <= cursor:
                        continue
                    payload = event.model_dump_json()
                    yield (
                        f"id: {sequence}\n"
                        f"event: {event.event_type}\n"
                        f"data: {payload}\n\n"
                    )
                    cursor = sequence
                run = store.get(parsed_id)
                if run is not None and run.state in {
                    "completed",
                    "partial",
                    "failed",
                }:
                    earliest_sequence, latest_sequence = store.event_bounds(parsed_id)
                    if latest_sequence is not None and cursor >= latest_sequence:
                        return
            else:
                run = store.get(parsed_id)
                if run is not None and run.state in {
                    "completed",
                    "partial",
                    "failed",
                }:
                    return
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
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
