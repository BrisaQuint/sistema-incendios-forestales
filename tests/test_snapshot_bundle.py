from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import create_valid_snapshot, seal_manifest, write_json
from sistema_incendios_forestales.api.app import app
from sistema_incendios_forestales.snapshot import (
    SnapshotValidationError,
    validate_snapshot,
)


def test_valid_bundle_is_verified_and_opened_read_only(tmp_path: Path) -> None:
    digest = create_valid_snapshot(tmp_path)

    snapshot = validate_snapshot(tmp_path, "1.0.0", digest)
    try:
        assert snapshot.release_id == "test-release"
        assert len(snapshot.coverage["features"]) == 169
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            snapshot.connection.execute(
                "INSERT INTO snapshot_metadata (key, value) VALUES ('unexpected', 'write')"
            )
    finally:
        snapshot.close()


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        ("payload", "payload size|payload SHA-256"),
        ("version", "bundle_version"),
        ("database_schema", "user_version"),
        ("database_extra_column", "weather_daily schema mismatch"),
        ("coverage_ids", "weather_id sets differ"),
        ("availability", "unsupported available dates"),
        ("manifest_schema", "manifest schema validation failed"),
        ("manifest_missing", "manifest.json is missing"),
    ],
)
def test_invalid_bundles_fail_closed(
    tmp_path: Path,
    tamper: str,
    message: str,
) -> None:
    digest = create_valid_snapshot(tmp_path)
    manifest_path = tmp_path / "manifest.json"

    if tamper == "payload":
        with (tmp_path / "coverage" / "province.geojson").open("a", encoding="utf-8") as target:
            target.write(" ")
    elif tamper == "version":
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["bundle_version"] = "9.0.0"
        write_json(manifest_path, manifest)
        digest = seal_manifest(tmp_path)
    elif tamper == "database_schema":
        connection = sqlite3.connect(tmp_path / "data" / "scientific.sqlite")
        connection.execute("PRAGMA user_version = 2")
        connection.close()
        digest = seal_manifest(tmp_path)
    elif tamper == "database_extra_column":
        connection = sqlite3.connect(tmp_path / "data" / "scientific.sqlite")
        connection.execute("ALTER TABLE weather_daily ADD COLUMN unexpected TEXT")
        connection.close()
        digest = seal_manifest(tmp_path)
    elif tamper == "coverage_ids":
        coverage_path = tmp_path / "coverage" / "weather-grid.geojson"
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
        coverage["features"][0]["properties"]["weather_id"] = "not-a-database-id"
        write_json(coverage_path, coverage)
        digest = seal_manifest(tmp_path)
    elif tamper == "availability":
        coverage_path = tmp_path / "coverage" / "weather-grid.geojson"
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
        coverage["features"][0]["properties"]["available_dates"] = ["2021-01-02"]
        write_json(coverage_path, coverage)
        digest = seal_manifest(tmp_path)
    elif tamper == "manifest_schema":
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["unexpected"] = True
        write_json(manifest_path, manifest)
        digest = seal_manifest(tmp_path)
    elif tamper == "manifest_missing":
        manifest_path.unlink()

    with pytest.raises(SnapshotValidationError, match=message):
        validate_snapshot(tmp_path, "1.0.0", digest)


def test_wrong_configured_manifest_digest_fails_closed(tmp_path: Path) -> None:
    create_valid_snapshot(tmp_path)

    with pytest.raises(SnapshotValidationError, match="manifest SHA-256"):
        validate_snapshot(tmp_path, "1.0.0", "0" * 64)


def test_invalid_bundle_prevents_application_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digest = create_valid_snapshot(tmp_path)
    for key, value in {
        "FIREWATCH_SNAPSHOT_DIR": str(tmp_path),
        "FIREWATCH_SNAPSHOT_VERSION": "1.0.0",
        "FIREWATCH_SNAPSHOT_MANIFEST_SHA256": digest,
        "FIREWATCH_LLM_PROVIDER": "mock",
    }.items():
        monkeypatch.setenv(key, value)

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    manifest["bundle_version"] = "2.0.0"
    write_json(tmp_path / "manifest.json", manifest)
    digest = seal_manifest(tmp_path)
    monkeypatch.setenv("FIREWATCH_SNAPSHOT_MANIFEST_SHA256", digest)

    with pytest.raises(RuntimeError, match="bundle_version does not match"):
        with TestClient(app):
            pass
