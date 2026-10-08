from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from fastapi.testclient import TestClient

from conftest import create_valid_snapshot
from sistema_incendios_forestales.analysis import build_deterministic_result
from sistema_incendios_forestales.api.contracts import AnalysisRequest, TraceEvent
from sistema_incendios_forestales.api.app import app
from sistema_incendios_forestales.audit import AUDIT_SCHEMA_VERSION, AuditStore
from sistema_incendios_forestales.snapshot import validate_snapshot

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def make_run_context(tmp_path: Path):
    snapshot_dir = tmp_path / "snapshot"
    manifest_digest = create_valid_snapshot(snapshot_dir)
    snapshot = validate_snapshot(snapshot_dir, "1.0.0", manifest_digest)
    weather_id = snapshot.coverage["features"][0]["properties"]["weather_id"]
    request = AnalysisRequest(weather_id=weather_id, date="2021-01-01")
    analysis_id = uuid4()
    result = build_deterministic_result(
        snapshot, request, analysis_id, manifest_digest
    )
    snapshot.close()
    return analysis_id, request, result


def test_initial_migration_and_v1_upgrade_are_ordered_and_versioned(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "audit.sqlite"
    store = AuditStore.open(database_path)
    assert store.connection.execute("PRAGMA user_version").fetchone()[0] == 2
    store.close()

    with sqlite3.connect(database_path) as connection:
        connection.execute("DROP INDEX analysis_runs_state_idx")
        connection.execute("DROP TRIGGER analysis_events_sequence")
        connection.execute("DROP TRIGGER analysis_runs_state_transition")
        connection.execute("PRAGMA user_version = 1")

    upgraded = AuditStore.open(database_path)
    try:
        assert (
            upgraded.connection.execute("PRAGMA user_version").fetchone()[0]
            == AUDIT_SCHEMA_VERSION
        )
        assert upgraded.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'trigger' "
            "AND name = 'analysis_events_sequence'"
        ).fetchone()
    finally:
        upgraded.close()


def test_unsupported_future_audit_schema_fails_startup(tmp_path: Path) -> None:
    database_path = tmp_path / "audit.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.execute(f"PRAGMA user_version = {AUDIT_SCHEMA_VERSION + 1}")

    with pytest.raises(RuntimeError, match="newer than supported"):
        AuditStore.open(database_path)


def test_analysis_events_are_sequenced_utc_idempotent_and_immutable(
    tmp_path: Path,
) -> None:
    analysis_id, request, result = make_run_context(tmp_path)
    store = AuditStore.open(tmp_path / "audit.sqlite")
    try:
        store.create_queued(analysis_id, request)
        store.execute(analysis_id, lambda: result)
        events = store.events(analysis_id)
        assert [event.sequence for event in events] == [1, 2, 3, 4]
        assert [event.event_type for event in events] == [
            "run_queued",
            "run_started",
            "analysis_core_result_persisted",
            "run_completed",
        ]
        assert len({event.idempotency_key for event in events}) == len(events)
        assert all(event.occurred_at.utcoffset().total_seconds() == 0 for event in events)

        schema = json.loads(
            (PROJECT_ROOT / "contracts" / "schemas" / "trace-event.v1.json").read_text(
                encoding="utf-8"
            )
        )
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for event in events:
            validator.validate(event.model_dump(mode="json", exclude_none=True))

        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            store.connection.execute(
                "UPDATE analysis_events SET event_type = 'run_failed' "
                "WHERE analysis_id = ? AND sequence = 1",
                (str(analysis_id),),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            store.connection.execute(
                "DELETE FROM analysis_events WHERE analysis_id = ? AND sequence = 1",
                (str(analysis_id),),
            )
        store.connection.rollback()

        with pytest.raises(sqlite3.IntegrityError, match="contiguous"):
            store.connection.execute(
                "INSERT INTO analysis_events "
                "(analysis_id, sequence, event_type, occurred_at, idempotency_key, event_json) "
                "VALUES (?, 6, 'run_partial', '2026-10-08T00:00:00+00:00', 'gap', '{}')",
                (str(analysis_id),),
            )
        store.connection.rollback()
    finally:
        store.close()


def test_real_intervention_events_require_and_persist_role_task_and_evidence(
    tmp_path: Path,
) -> None:
    analysis_id, request, _ = make_run_context(tmp_path)
    store = AuditStore.open(tmp_path / "audit.sqlite")
    try:
        store.create_queued(analysis_id, request)
        store._mark_started(analysis_id)
        intervention_id = uuid4()
        started = TraceEvent(
            schema_version="trace-event.v1",
            analysis_id=analysis_id,
            sequence=3,
            event_type="intervention_started",
            occurred_at=datetime.now(timezone.utc),
            idempotency_key=f"{analysis_id}:contextualizer:start",
            intervention_id=intervention_id,
            agent_role="contextualizer",
            task="contextualize verified evidence",
            input_evidence_refs=["evidence:weather"],
        )
        completed = TraceEvent(
            schema_version="trace-event.v1",
            analysis_id=analysis_id,
            sequence=4,
            event_type="intervention_completed",
            occurred_at=datetime.now(timezone.utc),
            idempotency_key=f"{analysis_id}:contextualizer:complete",
            intervention_id=intervention_id,
            agent_role="contextualizer",
            task="contextualize verified evidence",
            input_evidence_refs=["evidence:weather"],
            result_summary="Context prepared from supplied evidence.",
            evidence_refs=["evidence:weather"],
        )

        assert store.record_activity_event(started) == started
        assert store.record_activity_event(completed) == completed
        assert store.record_activity_event(completed) == completed
        assert store.event_types(analysis_id) == [
            "run_queued",
            "run_started",
            "intervention_started",
            "intervention_completed",
        ]
        persisted = store.events(analysis_id)
        assert persisted[2].agent_role == "contextualizer"
        assert persisted[2].task == "contextualize verified evidence"
        assert persisted[2].input_evidence_refs == ["evidence:weather"]
        assert persisted[3].evidence_refs == ["evidence:weather"]

        conflicting_retry = completed.model_copy(
            update={"result_summary": "Different content under the same key."}
        )
        with pytest.raises(ValueError, match="cannot be reused"):
            store.record_activity_event(conflicting_retry)
        transition_as_activity = completed.model_copy(
            update={
                "sequence": 5,
                "event_type": "run_completed",
                "result_ref": "analysis:result",
                "affected_outputs": ["deterministic_result"],
            }
        )
        with pytest.raises(ValueError, match="atomic transition"):
            store.record_activity_event(transition_as_activity)
    finally:
        store.close()


def test_failed_deterministic_tool_is_recorded_as_failed_without_success_result(
    tmp_path: Path,
) -> None:
    analysis_id, request, _ = make_run_context(tmp_path)
    store = AuditStore.open(tmp_path / "audit.sqlite")
    try:
        store.create_queued(analysis_id, request)
        store.execute(
            analysis_id,
            lambda: (_ for _ in ()).throw(
                sqlite3.OperationalError("scientific query failed")
            ),
        )

        analysis = store.get(analysis_id)
        assert analysis is not None
        assert analysis.state == "failed"
        assert analysis.error_code == "SCIENTIFIC_DATA_QUERY_FAILED"
        assert analysis.result is None
        events = store.events(analysis_id)
        assert [event.event_type for event in events] == [
            "run_queued",
            "run_started",
            "tool_failed",
            "run_failed",
        ]
        failed_tool = events[2]
        assert failed_tool.tool_name == "scientific_snapshot"
        assert failed_tool.task == "load_deterministic_analysis"
        assert failed_tool.error_code == "SCIENTIFIC_DATA_QUERY_FAILED"
        assert events[3].error_code == "SCIENTIFIC_DATA_QUERY_FAILED"
    finally:
        store.close()


def test_result_without_usable_fwi_is_failed_not_completed(tmp_path: Path) -> None:
    analysis_id, request, result = make_run_context(tmp_path)
    unavailable_fwi = result.result.fwi.model_copy(
        update={"value": None, "missing_reason": "not_available_in_snapshot"}
    )
    incomplete_result = result.model_copy(
        update={
            "result": result.result.model_copy(update={"fwi": unavailable_fwi})
        }
    )
    store = AuditStore.open(tmp_path / "audit.sqlite")
    try:
        store.create_queued(analysis_id, request)
        store.execute(analysis_id, lambda: incomplete_result)

        analysis = store.get(analysis_id)
        assert analysis is not None
        assert analysis.state == "failed"
        assert analysis.error_code == "FWI_CORE_RESULT_UNAVAILABLE"
        assert analysis.result is None
        assert store.event_types(analysis_id) == [
            "run_queued",
            "run_started",
            "tool_failed",
            "run_failed",
        ]
    finally:
        store.close()


def test_transition_rolls_back_event_projection_and_result_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_id, request, result = make_run_context(tmp_path)
    database_path = tmp_path / "audit.sqlite"
    store = AuditStore.open(database_path)
    store.create_queued(analysis_id, request)
    store._mark_started(analysis_id)
    append_event = store._append_event

    def append_then_fail(*args, **kwargs):
        event = append_event(*args, **kwargs)
        if event.event_type == "analysis_core_result_persisted":
            raise sqlite3.IntegrityError("injected transition failure")
        return event

    monkeypatch.setattr(store, "_append_event", append_then_fail)
    with pytest.raises(sqlite3.IntegrityError, match="injected"):
        store._persist_core_result(analysis_id, result)

    row = store.connection.execute(
        "SELECT state, result_json FROM analysis_runs WHERE analysis_id = ?",
        (str(analysis_id),),
    ).fetchone()
    assert row == ("running", None)
    assert store.event_types(analysis_id) == ["run_queued", "run_started"]
    store.close()


def test_terminal_transition_failure_rolls_back_and_startup_recovers_as_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_id, request, result = make_run_context(tmp_path)
    database_path = tmp_path / "audit.sqlite"
    store = AuditStore.open(database_path)
    store.create_queued(analysis_id, request)
    store._mark_started(analysis_id)
    store._persist_core_result(analysis_id, result)
    append_event = store._append_event

    def append_then_fail(*args, **kwargs):
        event = append_event(*args, **kwargs)
        if event.event_type == "run_completed":
            raise sqlite3.IntegrityError("injected terminal failure")
        return event

    monkeypatch.setattr(store, "_append_event", append_then_fail)
    with pytest.raises(sqlite3.IntegrityError, match="terminal"):
        store._finish(analysis_id, "completed", result=result)
    row = store.connection.execute(
        "SELECT state, result_json FROM analysis_runs WHERE analysis_id = ?",
        (str(analysis_id),),
    ).fetchone()
    assert row[0] == "running"
    assert json.loads(row[1])["result"]["fwi"]["value"] is not None
    assert store.event_types(analysis_id) == [
        "run_queued",
        "run_started",
        "analysis_core_result_persisted",
    ]
    store.close()

    recovered = AuditStore.open(database_path)
    try:
        analysis = recovered.get(analysis_id)
        assert analysis is not None
        assert analysis.state == "partial"
        assert analysis.error_code == "PROCESS_INTERRUPTED"
        assert analysis.result is not None
        assert analysis.result.fwi.value is not None
        assert recovered.event_types(analysis_id) == [
            "run_queued",
            "run_started",
            "analysis_core_result_persisted",
            "run_interrupted",
            "run_partial",
        ]
    finally:
        recovered.close()


def test_startup_recovers_queued_run_as_failed_without_restarting_it(
    tmp_path: Path,
) -> None:
    analysis_id, request, _ = make_run_context(tmp_path)
    database_path = tmp_path / "audit.sqlite"
    store = AuditStore.open(database_path)
    store.create_queued(analysis_id, request)
    store.close()

    recovered = AuditStore.open(database_path)
    try:
        analysis = recovered.get(analysis_id)
        assert analysis is not None
        assert analysis.state == "failed"
        assert analysis.error_code == "PROCESS_INTERRUPTED"
        assert analysis.result is None
        assert recovered.event_types(analysis_id) == [
            "run_queued",
            "run_interrupted",
            "run_failed",
        ]
        assert [event.sequence for event in recovered.events(analysis_id)] == [1, 2, 3]
    finally:
        recovered.close()


def test_startup_recovers_running_run_without_core_result_as_failed(
    tmp_path: Path,
) -> None:
    analysis_id, request, _ = make_run_context(tmp_path)
    database_path = tmp_path / "audit.sqlite"
    store = AuditStore.open(database_path)
    store.create_queued(analysis_id, request)
    store._mark_started(analysis_id)
    store.close()

    recovered = AuditStore.open(database_path)
    try:
        assert recovered.get(analysis_id).state == "failed"
        assert recovered.event_types(analysis_id) == [
            "run_queued",
            "run_started",
            "run_interrupted",
            "run_failed",
        ]
    finally:
        recovered.close()


def test_runtime_recovers_interrupted_runs_before_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    manifest_digest = create_valid_snapshot(snapshot_dir)
    database_path = tmp_path / "audit.sqlite"
    analysis_id, request, _ = make_run_context(tmp_path / "run-context")
    store = AuditStore.open(database_path)
    store.create_queued(analysis_id, request)
    store.close()
    for key, value in {
        "FIREWATCH_SNAPSHOT_DIR": str(snapshot_dir),
        "FIREWATCH_SNAPSHOT_VERSION": "1.0.0",
        "FIREWATCH_SNAPSHOT_MANIFEST_SHA256": manifest_digest,
        "FIREWATCH_AUDIT_DB": str(database_path),
        "FIREWATCH_LLM_PROVIDER": "mock",
    }.items():
        monkeypatch.setenv(key, value)

    with TestClient(app) as client:
        response = client.get("/api/health/ready")
        assert response.status_code == 200

    recovered = AuditStore.open(database_path)
    try:
        analysis = recovered.get(analysis_id)
        assert analysis is not None
        assert analysis.state == "failed"
        assert recovered.event_types(analysis_id)[-2:] == [
            "run_interrupted",
            "run_failed",
        ]
    finally:
        recovered.close()
