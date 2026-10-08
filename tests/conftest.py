from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from shapely.geometry import box, mapping

from sistema_incendios_forestales.snapshot import (
    EXPECTED_WEATHER_LOCATION_COUNT,
    SUPPORTED_BUNDLE_VERSION,
    SUPPORTED_SCHEMA_VERSION,
    PROJECT_ROOT,
)


SQL_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "schemas" / "scientific-snapshot.v1.sql"


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def seal_manifest(snapshot_dir: Path) -> str:
    manifest_path = snapshot_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for payload in manifest["payloads"]:
        path = snapshot_dir / payload["path"]
        payload["size_bytes"] = path.stat().st_size
        payload["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(manifest_path, manifest)
    return hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def create_valid_snapshot(snapshot_dir: Path) -> str:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "data").mkdir(exist_ok=True)
    (snapshot_dir / "coverage").mkdir(exist_ok=True)
    database_path = snapshot_dir / "data" / "scientific.sqlite"
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(SQL_SCHEMA_PATH.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO snapshot_metadata (key, value) VALUES (?, ?)",
            ("schema_version", SUPPORTED_SCHEMA_VERSION),
        )
        connection.execute(
            "INSERT INTO snapshot_metadata (key, value) VALUES (?, ?)",
            ("release_id", "test-release"),
        )
        daily_rows = []
        features = []
        reference_rows = []
        for index in range(EXPECTED_WEATHER_LOCATION_COUNT):
            row = index // 13
            column = index % 13
            latitude = -30 + row * 0.05
            longitude = -70 + column * 0.05
            weather_id = f"{latitude:.5f}_{longitude:.5f}"
            geometry = box(
                longitude - 0.02,
                latitude - 0.02,
                longitude + 0.02,
                latitude + 0.02,
            )
            features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(geometry),
                    "properties": {
                        "weather_id": weather_id,
                        "center": {
                            "latitude": latitude,
                            "longitude": longitude,
                        },
                        "center_inside": True,
                        "intersects": True,
                        "available_dates": ["2021-01-01"],
                    },
                }
            )
            connection.execute(
                "INSERT INTO weather_locations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    weather_id,
                    f"grid-{index}",
                    latitude,
                    longitude,
                    latitude,
                    longitude,
                    1,
                    1,
                ),
            )
            for day in ("2020-01-01", "2021-01-01"):
                daily_rows.append(
                    (
                        weather_id,
                        day,
                        20.0,
                        45.0,
                        12.0,
                        0.0,
                        85.0,
                        6.0,
                        15.0,
                        1.0,
                        2.0,
                        3.0,
                        0,
                    )
                )
            reference_rows.extend(
                (weather_id, month, 3.0) for month in range(1, 13)
            )
        connection.executemany(
            "INSERT INTO weather_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            daily_rows,
        )
        connection.executemany(
            "INSERT INTO monthly_fwi_reference VALUES (?, ?, ?)",
            reference_rows,
        )
        connection.commit()
    finally:
        connection.close()

    province_geometry = box(-71, -31, -68, -28)
    write_json(
        snapshot_dir / "coverage" / "province.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": mapping(province_geometry),
                    "properties": {"name": "La Rioja"},
                }
            ],
        },
    )
    write_json(
        snapshot_dir / "coverage" / "weather-grid.geojson",
        {"type": "FeatureCollection", "features": features},
    )

    manifest = {
        "bundle_version": SUPPORTED_BUNDLE_VERSION,
        "schema_version": SUPPORTED_SCHEMA_VERSION,
        "release_id": "test-release",
        "provenance": "Synthetic local bundle for focused snapshot validation tests.",
        "source_references": [
            {
                "source_id": f"source-{index}",
                "name": f"Test source {index}",
                "reference": f"offline/test-{index}",
            }
            for index in range(4)
        ],
        "date_coverage": {
            "spin_up": {"start": "2020-01-01", "end": "2020-01-01"},
            "analysis": {"start": "2021-01-01", "end": "2021-01-01"},
        },
        "spatial_coverage": {
            "province": "La Rioja, Argentina",
            "crs": "EPSG:4326",
            "weather_location_count": EXPECTED_WEATHER_LOCATION_COUNT,
            "center_inside_count": EXPECTED_WEATHER_LOCATION_COUNT,
        },
        "quality_checks": {
            "test_source_records": {
                "status": "passed",
                "observed": EXPECTED_WEATHER_LOCATION_COUNT * 2,
                "expected": EXPECTED_WEATHER_LOCATION_COUNT * 2,
            }
        },
        "payloads": [
            {
                "path": "data/scientific.sqlite",
                "media_type": "application/vnd.sqlite3",
                "size_bytes": 1,
                "sha256": "0" * 64,
            },
            {
                "path": "coverage/province.geojson",
                "media_type": "application/geo+json",
                "size_bytes": 1,
                "sha256": "0" * 64,
            },
            {
                "path": "coverage/weather-grid.geojson",
                "media_type": "application/geo+json",
                "size_bytes": 1,
                "sha256": "0" * 64,
            },
        ],
    }
    write_json(snapshot_dir / "manifest.json", manifest)
    return seal_manifest(snapshot_dir)
