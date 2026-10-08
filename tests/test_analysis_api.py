from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from conftest import create_valid_snapshot
from sistema_incendios_forestales.analysis import build_deterministic_result
from sistema_incendios_forestales.api.app import app
from sistema_incendios_forestales.api.contracts import AnalysisRequest, DataValue


@pytest.fixture
def configured_analysis_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    manifest_sha256 = create_valid_snapshot(tmp_path / "snapshot")
    monkeypatch.setenv("FIREWATCH_SNAPSHOT_DIR", str(tmp_path / "snapshot"))
    monkeypatch.setenv("FIREWATCH_SNAPSHOT_VERSION", "1.0.0")
    monkeypatch.setenv("FIREWATCH_SNAPSHOT_MANIFEST_SHA256", manifest_sha256)
    monkeypatch.setenv("FIREWATCH_AUDIT_DB", str(tmp_path / "audit.sqlite"))
    monkeypatch.setenv("FIREWATCH_LLM_PROVIDER", "mock")
    return tmp_path / "audit.sqlite"


def test_coverage_exposes_all_canonical_features_and_snapshot_provenance(
    configured_analysis_runtime: Path,
) -> None:
    with TestClient(app) as client:
        response = client.get("/api/coverage")

    assert response.status_code == 200
    coverage = response.json()
    assert coverage["type"] == "FeatureCollection"
    assert coverage["release_id"] == "test-release"
    assert len(coverage["features"]) == 169
    assert coverage["source_references"]
    assert coverage["date_coverage"]["analysis"] == {
        "start": "2021-01-01",
        "end": "2021-01-01",
    }
    assert len(
        {feature["properties"]["weather_id"] for feature in coverage["features"]}
    ) == 169
    feature = coverage["features"][0]
    assert feature["properties"]["center"]
    assert "center_inside" in feature["properties"]
    assert "intersects" in feature["properties"]
    assert feature["properties"]["available_dates"] == ["2021-01-01"]


def test_deterministic_analysis_is_accepted_and_result_and_events_persist_atomically(
    configured_analysis_runtime: Path,
) -> None:
    with TestClient(app) as client:
        coverage = client.get("/api/coverage").json()
        weather_id = coverage["features"][0]["properties"]["weather_id"]
        accepted = client.post(
            "/api/analyses",
            json={"weather_id": weather_id, "date": "2021-01-01"},
        )
        assert accepted.status_code == 202
        analysis_id = accepted.json()["analysis_id"]

        response = client.get(f"/api/analyses/{analysis_id}")

    assert response.status_code == 200
    analysis = response.json()
    assert analysis["state"] == "completed"
    assert analysis["weather_id"] == weather_id
    assert analysis["date"] == "2021-01-01"
    result = analysis["result"]
    assert result["fwi"]["value"] == 3
    assert result["historical_reference_fwi"]["value"] == 3
    assert result["difference_from_reference"]["value"] == 0
    assert result["reference_month"] == 1
    assert set(result["components"]) == {"ffmc", "dmc", "dc", "isi", "bui"}
    assert result["meteorology"]["temperature_2m"]["unit"] == "°C"
    assert result["firms_count"]["value"] == 0
    assert "no demuestra ausencia de incendio" in result["firms_interpretation"]
    assert f"snapshot:test-release:weather_daily:{weather_id}:2021-01-01" in result[
        "evidence_refs"
    ]
    assert any("monthly_fwi_reference" in ref for ref in result["evidence_refs"])
    assert result["provenance"]["release_id"] == "test-release"
    assert result["provenance"]["source_references"]

    with sqlite3.connect(configured_analysis_runtime) as connection:
        run = connection.execute(
            "SELECT state, result_json FROM analysis_runs WHERE analysis_id = ?",
            (analysis_id,),
        ).fetchone()
        events = connection.execute(
            "SELECT sequence, event_type, event_json FROM analysis_events "
            "WHERE analysis_id = ? ORDER BY sequence",
            (analysis_id,),
        ).fetchall()
    assert run[0] == "completed"
    assert json.loads(run[1]) == analysis
    assert [row[1] for row in events] == [
        "run_queued",
        "run_started",
        "analysis_core_result_persisted",
        "run_completed",
    ]
    assert [row[0] for row in events] == [1, 2, 3, 4]
    assert all(json.loads(row[2])["analysis_id"] == analysis_id for row in events)


@pytest.mark.parametrize(
    ("weather_id", "day", "expected_code"),
    [
        ("unknown-weather-id", "2021-01-01", "UNKNOWN_WEATHER_ID"),
        ("-30.00000_-70.00000", "2021-01-02", "DATE_NOT_AVAILABLE"),
    ],
)
def test_analysis_rejects_unknown_or_unavailable_context_without_creating_run(
    configured_analysis_runtime: Path,
    weather_id: str,
    day: str,
    expected_code: str,
) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/analyses", json={"weather_id": weather_id, "date": day}
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == expected_code
    with sqlite3.connect(configured_analysis_runtime) as connection:
        assert connection.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0] == 0


def test_missing_values_are_null_with_an_explicit_reason() -> None:
    value = DataValue(
        value=None,
        unit="índice FWI (sin unidad)",
        missing_reason="not_available_in_snapshot",
    )
    assert value.model_dump() == {
        "value": None,
        "unit": "índice FWI (sin unidad)",
        "missing_reason": "not_available_in_snapshot",
    }

    with pytest.raises(ValueError, match="missing_reason is required"):
        DataValue(value=None, unit="índice FWI (sin unidad)", missing_reason=None)


def test_missing_snapshot_values_remain_null_in_the_deterministic_result() -> None:
    class QueryResult:
        def __init__(self, row):
            self.row = row

        def fetchone(self):
            return self.row

    class MissingDataConnection:
        def execute(self, query: str, _parameters: tuple):
            if "weather_daily" in query:
                return QueryResult((None,) * 11)
            return QueryResult(None)

    snapshot = SimpleNamespace(
        release_id="missing-data-release",
        connection=MissingDataConnection(),
        coverage={
            "features": [
                {
                    "properties": {
                        "weather_id": "weather-001",
                        "available_dates": ["2021-01-01"],
                    }
                }
            ]
        },
        manifest={
            "bundle_version": "1.0.0",
            "schema_version": "firewatch.scientific-snapshot.v1",
            "source_references": [],
            "date_coverage": {
                "spin_up": {"start": "2020-01-01", "end": "2020-01-01"},
                "analysis": {"start": "2021-01-01", "end": "2021-01-01"},
            },
            "quality_checks": {},
        },
    )
    result = build_deterministic_result(
        snapshot,
        AnalysisRequest(weather_id="weather-001", date="2021-01-01"),
        uuid4(),
        "0" * 64,
    ).result

    assert result is not None
    for data_value in (
        result.fwi,
        result.historical_reference_fwi,
        result.difference_from_reference,
        result.firms_count,
    ):
        assert data_value.value is None
        assert data_value.missing_reason == "not_available_in_snapshot"
    assert "monthly_fwi_reference" not in " ".join(result.evidence_refs)


def test_unknown_analysis_id_is_an_explicit_not_found_error(
    configured_analysis_runtime: Path,
) -> None:
    with TestClient(app) as client:
        response = client.get("/api/analyses/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANALYSIS_NOT_FOUND"
