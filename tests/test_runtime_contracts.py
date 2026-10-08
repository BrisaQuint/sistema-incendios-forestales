from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from conftest import create_valid_snapshot
from sistema_incendios_forestales import main
from sistema_incendios_forestales.api.app import FRONTEND_DIST, app
from sistema_incendios_forestales.api.config import (
    RuntimeConfigurationError,
    load_settings,
)
from sistema_incendios_forestales.api.contracts import AnalysisRequest, TraceEvent


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ready_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    manifest_sha256 = create_valid_snapshot(tmp_path)
    environment = {
        "FIREWATCH_SNAPSHOT_DIR": str(tmp_path),
        "FIREWATCH_SNAPSHOT_VERSION": "1.0.0",
        "FIREWATCH_SNAPSHOT_MANIFEST_SHA256": manifest_sha256,
        "FIREWATCH_AUDIT_DB": str(tmp_path / "audit.sqlite"),
        "FIREWATCH_LLM_PROVIDER": "mock",
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)


def test_runtime_rejects_missing_snapshot_configuration() -> None:
    with pytest.raises(RuntimeConfigurationError, match="FIREWATCH_SNAPSHOT_DIR is required"):
        load_settings({})


def test_runtime_rejects_invalid_openai_provider_configuration(tmp_path: Path) -> None:
    manifest_sha256 = create_valid_snapshot(tmp_path)
    environment = {
        "FIREWATCH_SNAPSHOT_DIR": str(tmp_path),
        "FIREWATCH_SNAPSHOT_VERSION": "1.0.0",
        "FIREWATCH_SNAPSHOT_MANIFEST_SHA256": manifest_sha256,
        "FIREWATCH_LLM_PROVIDER": "openai",
    }

    with pytest.raises(RuntimeConfigurationError) as error:
        load_settings(environment)

    assert "OPENAI_API_KEY is required" in str(error.value)
    assert "FIREWATCH_LLM_TIMEOUT_SECONDS" in str(error.value)


def test_runtime_does_not_start_or_report_ready_without_required_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "FIREWATCH_SNAPSHOT_DIR",
        "FIREWATCH_SNAPSHOT_VERSION",
        "FIREWATCH_SNAPSHOT_MANIFEST_SHA256",
    ):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(RuntimeError, match="FIREWATCH_SNAPSHOT_DIR is required"):
        with TestClient(app):
            pass


def test_runtime_does_not_start_with_invalid_openai_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for key in (
        "OPENAI_API_KEY",
        "FIREWATCH_OPENAI_MODEL",
        "FIREWATCH_LLM_TIMEOUT_SECONDS",
        "FIREWATCH_LLM_MAX_RETRIES",
        "FIREWATCH_LLM_MAX_OUTPUT_TOKENS_PER_RUN",
    ):
        monkeypatch.delenv(key, raising=False)
    manifest_sha256 = create_valid_snapshot(tmp_path)
    environment = {
        "FIREWATCH_SNAPSHOT_DIR": str(tmp_path),
        "FIREWATCH_SNAPSHOT_VERSION": "1.0.0",
        "FIREWATCH_SNAPSHOT_MANIFEST_SHA256": manifest_sha256,
        "FIREWATCH_LLM_PROVIDER": "openai",
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
        with TestClient(app):
            pass


def test_runtime_accepts_explicit_mock_provider_and_complete_snapshot(
    tmp_path: Path,
) -> None:
    manifest_sha256 = create_valid_snapshot(tmp_path)
    settings = load_settings(
        {
            "FIREWATCH_SNAPSHOT_DIR": str(tmp_path),
            "FIREWATCH_SNAPSHOT_VERSION": "1.0.0",
            "FIREWATCH_SNAPSHOT_MANIFEST_SHA256": manifest_sha256,
            "FIREWATCH_LLM_PROVIDER": "mock",
        }
    )

    assert settings.snapshot_version == "1.0.0"
    assert settings.llm_provider == "mock"
    assert settings.snapshot_dir == tmp_path.resolve()


def test_analysis_request_has_only_canonical_id_and_local_date() -> None:
    request = AnalysisRequest.model_validate(
        {"weather_id": "weather-001", "date": "2024-08-15"}
    )

    assert request.model_dump(mode="json") == {
        "weather_id": "weather-001",
        "date": "2024-08-15",
    }
    with pytest.raises(ValidationError):
        AnalysisRequest.model_validate(
            {"weather_id": "weather-001", "date": "2024-08-15", "latitude": -29.4}
        )
    with pytest.raises(ValidationError):
        AnalysisRequest.model_validate(
            {"weather_id": "weather-001", "date": "2024-08-15T00:00:00Z"}
        )


def test_local_entry_point_uses_one_loopback_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    run_server = Mock()
    monkeypatch.setattr("uvicorn.run", run_server)

    main()

    run_server.assert_called_once_with(app, host="127.0.0.1", port=8000, workers=1)


def test_openapi_exposes_typed_vertical_contracts(ready_runtime: None) -> None:
    with TestClient(app) as client:
        schemas = client.get("/openapi.json").json()["components"]["schemas"]
        ready = client.get("/api/health/ready")
        page = client.get("/")
        asset_path = next((FRONTEND_DIST / "assets").iterdir()).name
        asset = client.get(f"/assets/{asset_path}")

    assert {
        "CoverageResponse",
        "AnalysisRequest",
        "AnalysisResult",
        "ErrorResponse",
        "TraceEvent",
    }.issubset(schemas)
    request_schema = schemas["AnalysisRequest"]
    assert set(request_schema["properties"]) == {"weather_id", "date"}
    assert set(request_schema["required"]) == {"weather_id", "date"}
    assert request_schema["properties"]["date"]["format"] == "date"
    assert request_schema["additionalProperties"] is False
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "snapshot_version": "1.0.0"}
    assert page.status_code == 200
    assert "FireWatch" in page.text
    assert asset.status_code == 200
    assert asset.headers["content-type"] in {
        "application/javascript",
        "text/javascript",
        "text/css",
    }


def test_trace_event_schema_and_pydantic_contract_agree() -> None:
    schema_path = PROJECT_ROOT / "contracts" / "schemas" / "trace-event.v1.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    valid_event = {
        "schema_version": "trace-event.v1",
        "analysis_id": str(uuid4()),
        "sequence": 1,
        "event_type": "run_queued",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": "run-queued-1",
    }

    Draft202012Validator(schema).validate(valid_event)
    assert TraceEvent.model_validate(valid_event).sequence == 1

    invalid_event = {**valid_event, "sequence": 0, "unexpected": True}
    assert not Draft202012Validator(schema).is_valid(invalid_event)
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(invalid_event)

    incomplete_intervention = {**valid_event, "event_type": "intervention_started"}
    assert not Draft202012Validator(schema).is_valid(incomplete_intervention)
    with pytest.raises(ValidationError):
        TraceEvent.model_validate(incomplete_intervention)


def test_frontend_fallback_does_not_mask_unknown_api_routes(ready_runtime: None) -> None:
    with TestClient(app) as client:
        response = client.get("/api/not-yet-implemented")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "HTTP_404"
    assert response.headers["X-Request-ID"]
