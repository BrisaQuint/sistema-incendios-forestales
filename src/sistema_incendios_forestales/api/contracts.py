from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AnalysisState = Literal["queued", "running", "completed", "partial", "failed"]
TraceEventType = Literal[
    "run_queued",
    "run_started",
    "analysis_core_result_persisted",
    "tool_failed",
    "intervention_started",
    "intervention_completed",
    "intervention_failed",
    "review_approved",
    "review_revision_requested",
    "run_interrupted",
    "run_completed",
    "run_partial",
    "run_failed",
]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Coordinates(ContractModel):
    latitude: float
    longitude: float


class CoverageProperties(ContractModel):
    weather_id: str = Field(min_length=1)
    center: Coordinates
    center_inside: bool
    intersects: bool
    available_dates: list[date]


class PolygonGeometry(ContractModel):
    type: Literal["Polygon"]
    coordinates: list[list[tuple[float, float]]]


class MultiPolygonGeometry(ContractModel):
    type: Literal["MultiPolygon"]
    coordinates: list[list[list[tuple[float, float]]]]


GeoJSONGeometry = Annotated[
    PolygonGeometry | MultiPolygonGeometry,
    Field(discriminator="type"),
]


class CoverageFeature(ContractModel):
    type: Literal["Feature"]
    geometry: GeoJSONGeometry
    properties: CoverageProperties


class CoverageResponse(ContractModel):
    type: Literal["FeatureCollection"]
    snapshot_version: str
    features: list[CoverageFeature]


class AnalysisRequest(ContractModel):
    weather_id: str = Field(min_length=1)
    date: date

    @field_validator("weather_id")
    @classmethod
    def require_non_blank_canonical_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("weather_id must be a canonical non-blank identifier")
        return value

    @field_validator("date", mode="before")
    @classmethod
    def require_iso_local_date(cls, value: Any) -> date:
        if isinstance(value, datetime) or not isinstance(value, (str, date)):
            raise ValueError("date must be an ISO local calendar date")
        if isinstance(value, str):
            try:
                parsed = date.fromisoformat(value)
            except ValueError as error:
                raise ValueError("date must be an ISO local calendar date") from error
            if parsed.isoformat() != value:
                raise ValueError("date must use canonical YYYY-MM-DD format")
            return parsed
        return value


class DataValue(ContractModel):
    value: float | None
    unit: str | None
    missing_reason: str | None

    @model_validator(mode="after")
    def require_reason_for_missing_values(self) -> DataValue:
        if self.value is None and not self.missing_reason:
            raise ValueError("missing_reason is required when value is unavailable")
        if self.value is not None and self.missing_reason is not None:
            raise ValueError("missing_reason must be null when value is available")
        return self


class AnalysisResult(ContractModel):
    analysis_id: UUID
    weather_id: str
    date: date
    state: AnalysisState
    fwi: DataValue
    historical_reference_fwi: DataValue
    difference_from_reference: DataValue


class APIError(ContractModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, Any]


class ErrorResponse(ContractModel):
    error: APIError
    request_id: UUID
    analysis_id: UUID | None = None


class ReadinessResponse(ContractModel):
    status: Literal["ready"]
    snapshot_version: str


class TraceEvent(ContractModel):
    schema_version: Literal["trace-event.v1"]
    analysis_id: UUID
    sequence: int = Field(ge=1)
    event_type: TraceEventType
    occurred_at: datetime
    idempotency_key: str = Field(min_length=1)
    intervention_id: UUID | None = None
    agent_role: str | None = None
    task: str | None = None
    input_evidence_refs: list[str] | None = None
    result_summary: str | None = None
    output_ref: str | None = None
    evidence_refs: list[str] | None = None
    tool_name: str | None = None
    decision: Literal["approved", "revision_requested"] | None = None
    issue_refs: list[str] | None = None
    result_ref: str | None = None
    error_code: str | None = None
    affected_outputs: list[str] | None = None

    @model_validator(mode="after")
    def validate_event_requirements(self) -> TraceEvent:
        if self.occurred_at.utcoffset() != timedelta(0):
            raise ValueError("occurred_at must use UTC")

        intervention_events = {
            "intervention_started",
            "intervention_completed",
            "intervention_failed",
        }
        if self.event_type in intervention_events:
            required = (
                self.intervention_id,
                self.agent_role,
                self.task,
                self.input_evidence_refs,
            )
            if any(value is None for value in required):
                raise ValueError("intervention events require id, role, task, and input evidence")

        if self.event_type == "intervention_completed" and not (
            self.result_summary or self.output_ref
        ):
            raise ValueError("completed interventions require a result summary or output ref")
        if self.event_type == "intervention_completed" and not self.evidence_refs:
            raise ValueError("completed interventions require evidence refs")
        if self.event_type in {"intervention_failed", "tool_failed"}:
            if not self.error_code or not self.affected_outputs:
                raise ValueError("failed operations require an error code and affected outputs")
        if self.event_type == "tool_failed" and (not self.tool_name or not self.task):
            raise ValueError("tool failures require the actual tool name and task")
        if self.event_type in {"review_approved", "review_revision_requested"}:
            if not self.intervention_id or not self.decision or self.issue_refs is None:
                raise ValueError("review decisions require validator, decision, and issue refs")
            expected_decision = (
                "approved"
                if self.event_type == "review_approved"
                else "revision_requested"
            )
            if self.decision != expected_decision:
                raise ValueError("review event type and decision must agree")
        if self.event_type == "analysis_core_result_persisted" and not self.result_ref:
            raise ValueError("persisted core results require a result ref")
        if self.event_type in {"run_completed", "run_partial", "run_failed"}:
            if self.affected_outputs is None:
                raise ValueError("terminal run events require affected outputs")
        if self.event_type == "run_completed" and not self.result_ref:
            raise ValueError("completed runs require a result ref")
        if self.event_type == "run_failed" and not self.error_code:
            raise ValueError("failed runs require an error code")
        return self


CONTRACT_MODELS = (
    CoverageResponse,
    AnalysisRequest,
    AnalysisResult,
    ErrorResponse,
    ReadinessResponse,
    TraceEvent,
)
