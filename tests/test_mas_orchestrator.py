from __future__ import annotations

import json
import sqlite3
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from conftest import create_valid_snapshot
from sistema_incendios_forestales.api.app import app
from sistema_incendios_forestales.llm import (
    LLMOutputError,
    LLMRequest,
    LLMResponse,
)
from sistema_incendios_forestales.mas import DeterministicMASOrchestrator


class ScriptedProvider:
    def __init__(
        self,
        decisions: list[str] | None = None,
        *,
        fail_role: str | None = None,
        contextualizer_refs: list[str] | None = None,
        explainer_refs: list[str] | None = None,
        contextualizer_text: str = "The record provides descriptive daily context.",
    ) -> None:
        self.decisions = list(decisions or ["approved"])
        self.fail_role = fail_role
        self.contextualizer_refs = contextualizer_refs
        self.explainer_refs = explainer_refs
        self.contextualizer_text = contextualizer_text
        self.calls: list[str] = []
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest, _budget: Any) -> LLMResponse:
        self.calls.append(request.role)
        self.requests.append(request)
        if request.role == self.fail_role:
            raise LLMOutputError("provider output failed")

        payload = json.loads(request.user_prompt)
        evidence = payload["evidence_bundle"]["evidence"]
        deterministic_refs = [record["evidence_id"] for record in evidence]
        if request.role == "contextualizer":
            refs = self.contextualizer_refs or deterministic_refs[:1]
            output = {
                "schema_version": "contextualizer-output.v1",
                "summary": self.contextualizer_text,
                "claims": [
                    {
                        "claim_id": "daily-context",
                        "text": "The available record supports a descriptive comparison.",
                        "evidence_refs": refs,
                    }
                ],
            }
        elif request.role == "validator":
            decision = self.decisions.pop(0)
            issues = (
                [
                    {
                        "issue_code": "NEEDS_CLEARER_SCOPE",
                        "claim_id": "daily-context",
                        "evidence_refs": deterministic_refs[:1],
                    }
                ]
                if decision == "revision_requested"
                else []
            )
            output = {
                "schema_version": "validator-output.v1",
                "decision": decision,
                "issues": issues,
            }
        else:
            contextualization_ref = next(
                record["evidence_id"]
                for record in evidence
                if record["evidence_type"] == "contextualization"
            )
            output = {
                "schema_version": "explainer-output.v1",
                "explanation": "This interpretation is descriptive and bounded by the cited records.",
                "evidence_refs": self.explainer_refs
                or [contextualization_ref, deterministic_refs[0]],
            }
        return LLMResponse(
            output=output,
            provider="mock",
            model="test-scripted",
            metadata={
                "provider": "mock",
                "model": "test-scripted",
                "request_id": f"test-request-{len(self.calls)}",
                "prompt_version": request.prompt_version,
                "schema_version": request.schema_version,
            },
        )


@pytest.fixture
def mas_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
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


def run_analysis(database_path: Path, provider: ScriptedProvider) -> tuple[dict, list[dict]]:
    with TestClient(app) as client:
        app.state.llm_provider = provider
        weather_id = client.get("/api/coverage").json()["features"][0]["properties"][
            "weather_id"
        ]
        accepted = client.post(
            "/api/analyses",
            json={"weather_id": weather_id, "date": "2021-01-01"},
        )
        assert accepted.status_code == 202
        analysis_id = accepted.json()["analysis_id"]
        response = client.get(f"/api/analyses/{analysis_id}")
        assert response.status_code == 200
        analysis = response.json()

    with sqlite3.connect(database_path) as connection:
        events = [
            json.loads(row[0])
            for row in connection.execute(
                "SELECT event_json FROM analysis_events "
                "WHERE analysis_id = ? ORDER BY sequence",
                (analysis_id,),
            )
        ]
    return analysis, events


def test_orchestrator_executes_three_roles_and_persists_real_interventions(
    mas_runtime: Path,
) -> None:
    provider = ScriptedProvider()
    analysis, events = run_analysis(mas_runtime, provider)

    assert analysis["state"] == "completed"
    assert analysis["result"]["fwi"]["value"] == 3
    assert analysis["explanation"].startswith("This interpretation")
    assert analysis["explanation_evidence_refs"]
    assert [event["event_type"] for event in events] == [
        "run_queued",
        "run_started",
        "analysis_core_result_persisted",
        "intervention_started",
        "intervention_completed",
        "intervention_started",
        "intervention_completed",
        "review_approved",
        "intervention_started",
        "intervention_completed",
        "run_completed",
    ]
    roles = [
        event["agent_role"]
        for event in events
        if event["event_type"] == "intervention_started"
    ]
    assert roles == ["contextualizer", "validator", "explainer"]
    interventions = {}
    for event in events:
        if event["event_type"].startswith("intervention_"):
            interventions.setdefault(event["intervention_id"], []).append(
                event["event_type"]
            )
            assert event["task"]
            assert event["input_evidence_refs"]
            assert all(
                reference.startswith(f"analysis:{analysis['analysis_id']}:")
                for reference in event["input_evidence_refs"]
            )
    assert all(
        states == ["intervention_started", "intervention_completed"]
        for states in interventions.values()
    )
    assert analysis["provider_metadata"][0]["model"] == "test-scripted"


def test_one_revision_is_allowed_and_second_validation_approval_explains(
    mas_runtime: Path,
) -> None:
    provider = ScriptedProvider(["revision_requested", "approved"])
    analysis, events = run_analysis(mas_runtime, provider)

    assert analysis["state"] == "completed"
    assert provider.calls == [
        "contextualizer",
        "validator",
        "contextualizer",
        "validator",
        "explainer",
    ]
    assert sum(
        event["event_type"] == "intervention_started"
        and event["agent_role"] == "contextualizer"
        for event in events
    ) == 2
    assert [event["event_type"] for event in events].count(
        "review_revision_requested"
    ) == 1
    review_event = next(
        event for event in events if event["event_type"] == "review_revision_requested"
    )
    assert any(reference.startswith("analysis:") for reference in review_event["issue_refs"])
    assert any(":evidence:" in reference for reference in review_event["issue_refs"])
    second_context_input = json.loads(provider.requests[2].user_prompt)
    assert second_context_input["revision_number"] == 1
    assert second_context_input["previous_contextualization"]["claims"][0][
        "claim_id"
    ] == "daily-context"
    assert second_context_input["revision_feedback"] == [
        "NEEDS_CLEARER_SCOPE: daily-context"
    ]


def test_second_validation_rejection_is_partial_without_explanation(
    mas_runtime: Path,
) -> None:
    provider = ScriptedProvider(["revision_requested", "revision_requested"])
    analysis, events = run_analysis(mas_runtime, provider)

    assert analysis["state"] == "partial"
    assert analysis["error_code"] == "MAS_VALIDATION_NOT_APPROVED"
    assert analysis["result"]["fwi"]["value"] == 3
    assert analysis["explanation"] is None
    assert analysis["affected_outputs"] == ["contextualization", "explanation"]
    assert "explainer" not in provider.calls
    assert [event["event_type"] for event in events].count(
        "review_revision_requested"
    ) == 2
    assert events[-1]["event_type"] == "run_partial"
    assert events[-1]["affected_outputs"] == ["contextualization", "explanation"]


def test_provider_failure_records_failed_intervention_and_preserves_fwi(
    mas_runtime: Path,
) -> None:
    provider = ScriptedProvider(fail_role="validator")
    analysis, events = run_analysis(mas_runtime, provider)

    assert analysis["state"] == "partial"
    assert analysis["error_code"] == "llm_invalid_output"
    assert analysis["result"]["fwi"]["value"] == 3
    assert analysis["explanation"] is None
    assert analysis["affected_outputs"] == ["validation", "explanation"]
    assert events[-2]["event_type"] == "intervention_failed"
    assert events[-2]["agent_role"] == "validator"
    assert events[-2]["error_code"] == "llm_invalid_output"
    assert events[-1]["event_type"] == "run_partial"
    assert events[-1]["affected_outputs"] == ["validation", "explanation"]


@pytest.mark.parametrize("reference_kind", ["missing", "foreign"])
def test_contextualizer_cannot_cite_unknown_or_other_run_evidence(
    mas_runtime: Path,
    reference_kind: str,
) -> None:
    reference = (
        "analysis:00000000-0000-0000-0000-000000000000:evidence:001"
        if reference_kind == "foreign"
        else "analysis:11111111-1111-1111-1111-111111111111:missing"
    )
    provider = ScriptedProvider(contextualizer_refs=[reference])
    analysis, events = run_analysis(mas_runtime, provider)

    assert analysis["state"] == "partial"
    assert analysis["error_code"] == "MAS_INVALID_EVIDENCE_REFERENCE"
    assert analysis["result"]["fwi"]["value"] == 3
    assert analysis["explanation"] is None
    assert analysis["affected_outputs"] == ["contextualization", "validation", "explanation"]
    assert events[-2]["event_type"] == "intervention_failed"
    assert events[-2]["error_code"] == "MAS_INVALID_EVIDENCE_REFERENCE"


def test_explainer_cannot_cite_a_reference_from_another_analysis(
    mas_runtime: Path,
) -> None:
    provider = ScriptedProvider(
        explainer_refs=["analysis:00000000-0000-0000-0000-000000000000:evidence:001"]
    )
    analysis, events = run_analysis(mas_runtime, provider)

    assert analysis["state"] == "partial"
    assert analysis["error_code"] == "MAS_INVALID_EVIDENCE_REFERENCE"
    assert analysis["result"]["fwi"]["value"] == 3
    assert analysis["explanation"] is None
    assert events[-2]["event_type"] == "intervention_failed"
    assert events[-2]["agent_role"] == "explainer"
    assert analysis["affected_outputs"] == ["explanation"]


@pytest.mark.parametrize(
    "claim",
    ["FWI is 999.", "There are three categories.", "Hay tres categorías."],
)
def test_numeric_claim_in_agent_prose_is_rejected_without_changing_science(
    mas_runtime: Path,
    claim: str,
) -> None:
    provider = ScriptedProvider(contextualizer_text=claim)
    analysis, events = run_analysis(mas_runtime, provider)

    assert analysis["state"] == "partial"
    assert analysis["error_code"] == "MAS_UNSUPPORTED_NUMERIC_CLAIM"
    assert analysis["result"]["fwi"]["value"] == 3
    assert analysis["explanation"] is None
    assert events[-2]["event_type"] == "intervention_failed"


def test_all_authoritative_mas_schemas_are_valid_and_versioned() -> None:
    schema_names = (
        "evidence-bundle.v1.json",
        "contextualizer-input.v1.json",
        "contextualizer-output.v1.json",
        "validator-input.v1.json",
        "validator-output.v1.json",
        "explainer-input.v1.json",
        "explainer-output.v1.json",
    )

    for schema_name in schema_names:
        schema = DeterministicMASOrchestrator._load_contract(schema_name)
        Draft202012Validator.check_schema(schema)


def test_llm_role_request_has_no_arbitrary_tool_or_data_access_surface() -> None:
    request_fields = {field.name for field in fields(LLMRequest)}
    assert request_fields == {
        "analysis_id",
        "role",
        "system_prompt",
        "user_prompt",
        "schema_name",
        "schema_version",
        "json_schema",
        "prompt_version",
        "max_output_tokens",
    }
