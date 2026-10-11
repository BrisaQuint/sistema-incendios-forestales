"""Read-only geographic resources; no provider calls or persisted analysis."""
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sistema_incendios_forestales.api.app import app
from sistema_incendios_forestales.api.contracts import ProvinceBoundaryResponse
from test_analysis_api import configured_analysis_runtime  # noqa: F401


def test_province_resource_is_fixed_and_independent(configured_analysis_runtime):
    with TestClient(app) as client:
        class ForbiddenProvider:
            def __getattr__(self, name):
                raise AssertionError("Map must not access provider")
        app.state.llm_provider = ForbiddenProvider()
        expected = app.state.snapshot.province["features"]
        province = client.get("/api/coverage/province")
        coverage = client.get("/api/coverage").json()
        assert province.status_code == 200
        assert province.json()["features"] == expected
        assert province.json()["release_id"] == coverage["release_id"]
        assert len(coverage["features"]) == 169
        assert client.get("/api/coverage/province/../../.env").status_code == 404
    with sqlite3.connect(configured_analysis_runtime) as connection:
        assert connection.execute("SELECT count(*) FROM analysis_runs").fetchone()[0] == 0


def test_validated_snapshot_cells_match_weather_ids_read_only():
    root = Path(__file__).resolve().parents[1] / "data/snapshots/2026-10-08-2"
    if not root.exists():
        pytest.skip("Local validated snapshot not distributed with repository")
    grid = json.loads((root / "coverage/weather-grid.geojson").read_text(encoding="utf-8"))
    province = json.loads((root / "coverage/province.geojson").read_text(encoding="utf-8"))
    boundary = ProvinceBoundaryResponse(type="FeatureCollection", release_id="2026-10-08-2", features=province["features"])
    assert boundary.features
    features = grid["features"]
    assert len(features) == 169
    ids = {f["properties"]["weather_id"] for f in features}
    assert len(ids) == 169
    assert all(f["properties"]["intersects"] for f in features)
    assert sum(not f["properties"]["center_inside"] for f in features) == 30
    # Canonical IDs are used unchanged, including all exterior-center cells.
    database = next(root.rglob("*.sqlite"), None)
    assert database is not None
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        actual = {row[0] for row in connection.execute("SELECT DISTINCT weather_id FROM weather_daily")}
        assert ids == actual
