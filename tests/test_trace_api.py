from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import create_valid_snapshot
from sistema_incendios_forestales.api.app import app
from test_mas_orchestrator import ScriptedProvider
from sistema_incendios_forestales.api.contracts import AnalysisRequest
from sistema_incendios_forestales.analysis import build_deterministic_result
from uuid import uuid4


@pytest.fixture
def trace_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    snapshot_dir = tmp_path / "snapshot"
    manifest_digest = create_valid_snapshot(snapshot_dir)
    database_path = tmp_path / "audit.sqlite"
    for key, value in {
        "FIREWATCH_SNAPSHOT_DIR": str(snapshot_dir),
        "FIREWATCH_SNAPSHOT_VERSION": "1.0.0",
        "FIREWATCH_SNAPSHOT_MANIFEST_SHA256": manifest_digest,
        "FIREWATCH_AUDIT_DB": str(database_path),
        "FIREWATCH_LLM_PROVIDER": "mock",
    }.items():
        monkeypatch.setenv(key, value)
    return database_path


def completed_analysis(
    client: TestClient,
    *,
    fail_role: str | None = None,
) -> tuple[str, ScriptedProvider]:
    provider = ScriptedProvider(fail_role=fail_role)
    app.state.llm_provider = provider
    weather_id = client.get("/api/coverage").json()["features"][0]["properties"][
        "weather_id"
    ]
    accepted = client.post(
        "/api/analyses",
        json={"weather_id": weather_id, "date": "2021-01-01"},
    )
    assert accepted.status_code == 202
    return accepted.json()["analysis_id"], provider


@pytest.mark.parametrize("persist_core", [False, True])
def test_restart_then_resume_cursor_without_provider_calls(trace_runtime, persist_core):
    analysis_id = uuid4()
    with TestClient(app) as client:
        snapshot = app.state.snapshot
        request = AnalysisRequest(weather_id=snapshot.coverage["features"][0]["properties"]["weather_id"], date="2021-01-01")
        store = app.state.audit_store
        async def seed_interrupted_run():
            store.create_queued(analysis_id, request)
            store._mark_started(analysis_id)
            if persist_core:
                store._persist_core_result(analysis_id, build_deterministic_result(
                    snapshot, request, analysis_id, app.state.settings.snapshot_manifest_sha256))
            return store.event_bounds(analysis_id)[1]
        cursor = client.portal.call(seed_interrupted_run)
        # Closing this isolated lifespan models a lost client and interrupted process.
    with TestClient(app) as client:
        class ForbiddenProvider:
            def __getattr__(self, name):
                raise AssertionError("Recovery must not invoke LLM")
        app.state.llm_provider = ForbiddenProvider()
        response = client.get(f"/api/analyses/{analysis_id}/trace/events", headers={"Last-Event-ID": str(cursor)})
        assert response.status_code == 200
        assert [int(line[4:]) for line in response.text.splitlines() if line.startswith("id: ")] == [cursor + 1, cursor + 2]
        assert "event: run_interrupted" in response.text
        assert f"event: run_{'partial' if persist_core else 'failed'}" in response.text
        result = client.get(f"/api/analyses/{analysis_id}").json()
        assert result["state"] == ("partial" if persist_core else "failed")
        if persist_core:
            assert result["result"]["fwi"]["value"] == 3


def test_trace_query_returns_only_persisted_ordered_events_and_resolved_run_refs(
    trace_runtime: Path,
) -> None:
    with TestClient(app) as client:
        analysis_id, _ = completed_analysis(client)
        response = client.get(f"/api/analyses/{analysis_id}/trace")

    assert response.status_code == 200
    trace = response.json()
    assert trace["run_state"] == "completed"
    assert trace["trace_status"] == "available"
    events = trace["events"]
    assert [event["sequence"] for event in events] == list(
        range(1, len(events) + 1)
    )
    assert all(event["analysis_id"] == analysis_id for event in events)
    starts = [event for event in events if event["event_type"] == "intervention_started"]
    assert [event["agent_role"] for event in starts] == [
        "contextualizer",
        "validator",
        "explainer",
    ]
    assert all(event["task"] and event["intervention_id"] for event in starts)
    assert all(event["evidence_refs"] for event in starts)
    assert all(
        reference.startswith(f"analysis:{analysis_id}:")
        for event in starts
        for reference in event["evidence_refs"]
    )
    contextualizer_terminal = next(
        event
        for event in events
        if event["event_type"] == "intervention_completed"
        and event["agent_role"] == "contextualizer"
    )
    assert contextualizer_terminal["evidence"]
    assert all(
        reference.startswith(f"analysis:{analysis_id}:")
        for reference in contextualizer_terminal["evidence"]
    )


def test_sse_replays_durable_events_exclusively_and_never_reexecutes_agents(
    trace_runtime: Path,
) -> None:
    with TestClient(app) as client:
        analysis_id, provider = completed_analysis(client)
        before = len(provider.calls)
        response = client.get(
            f"/api/analyses/{analysis_id}/trace/events",
            headers={"Last-Event-ID": "3"},
        )
        latest = client.get(f"/api/analyses/{analysis_id}/trace").json()[
            "latest_sequence"
        ]
        resume_response = client.get(
            f"/api/analyses/{analysis_id}/trace/events",
            headers={"Last-Event-ID": str(latest)},
        )

    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line.startswith("id: ")]
    assert lines
    assert lines[0] == "id: 4"
    assert [int(line.removeprefix("id: ")) for line in lines] == list(
        range(4, latest + 1)
    )
    assert "event: intervention_started" in response.text
    assert "data: " in response.text
    assert resume_response.status_code == 200
    assert not [line for line in resume_response.text.splitlines() if line.startswith("id: ")]
    assert len(provider.calls) == before == 3


@pytest.mark.parametrize(
    ("header", "expected_code"),
    [
        ("abc", "INVALID_TRACE_CURSOR"),
        ("-1", "INVALID_TRACE_CURSOR"),
        ("999", "TRACE_CURSOR_IN_FUTURE"),
    ],
)
def test_trace_rejects_invalid_or_future_last_event_id(
    trace_runtime: Path,
    header: str,
    expected_code: str,
) -> None:
    with TestClient(app) as client:
        analysis_id, _ = completed_analysis(client)
        response = client.get(
            f"/api/analyses/{analysis_id}/trace/events",
            headers={"Last-Event-ID": header},
        )

    assert response.status_code == (
        400 if expected_code == "INVALID_TRACE_CURSOR" else 409
    )
    assert response.json()["error"]["code"] == expected_code


def test_trace_and_sse_report_missing_run_explicitly(trace_runtime: Path) -> None:
    missing_id = "00000000-0000-0000-0000-000000000000"
    with TestClient(app) as client:
        trace_response = client.get(f"/api/analyses/{missing_id}/trace")
        stream_response = client.get(f"/api/analyses/{missing_id}/trace/events")

    assert trace_response.status_code == 404
    assert stream_response.status_code == 404
    assert trace_response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"
    assert stream_response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"


def test_trace_events_are_read_from_audit_rows_without_invented_items(
    trace_runtime: Path,
) -> None:
    with TestClient(app) as client:
        analysis_id, _ = completed_analysis(client)
        response = client.get(f"/api/analyses/{analysis_id}/trace")

    returned = response.json()["events"]
    with sqlite3.connect(trace_runtime) as connection:
        stored = [
            json.loads(row[0])
            for row in connection.execute(
                "SELECT event_json FROM analysis_events "
                "WHERE analysis_id = ? ORDER BY sequence",
                (analysis_id,),
            )
        ]
    assert [event["sequence"] for event in returned] == [
        event["sequence"] for event in stored
    ]
    assert [event["event_type"] for event in returned] == [
        event["event_type"] for event in stored
    ]


def test_terminal_analysis_with_no_durable_events_reports_trace_unavailable(
    trace_runtime: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(app) as client:
        analysis_id, _ = completed_analysis(client)
        store = app.state.audit_store
        original_events = store.events
        monkeypatch.setattr(
            store,
            "events",
            lambda requested_id: (
                [] if str(requested_id) == analysis_id else original_events(requested_id)
            ),
        )
        response = client.get(f"/api/analyses/{analysis_id}/trace")

    assert response.status_code == 200
    assert response.json()["run_state"] == "completed"
    assert response.json()["trace_status"] == "unavailable"
    assert response.json()["events"] == []


def test_agent_failure_preserves_fwi_and_exposes_partial_trace(
    trace_runtime: Path,
) -> None:
    with TestClient(app) as client:
        analysis_id, provider = completed_analysis(client, fail_role="explainer")
        result = client.get(f"/api/analyses/{analysis_id}").json()
        trace = client.get(f"/api/analyses/{analysis_id}/trace").json()

    assert result["state"] == "partial"
    assert result["result"]["fwi"]["value"] is not None
    assert result["explanation"] is None
    assert result["affected_outputs"]
    assert trace["trace_status"] == "incomplete"
    failed_explainer = [
        event
        for event in trace["events"]
        if event["event_type"] == "intervention_failed"
        and event["agent_role"] == "explainer"
    ]
    assert len(failed_explainer) == 1
    assert failed_explainer[0]["task"]
    assert failed_explainer[0]["affected_outputs"]
    assert provider.calls == ["contextualizer", "validator", "explainer"]
