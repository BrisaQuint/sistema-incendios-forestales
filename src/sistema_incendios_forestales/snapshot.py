from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from shapely.geometry import Point, shape

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_SCHEMA_PATH = (
    PROJECT_ROOT
    / "contracts"
    / "schemas"
    / "scientific-snapshot-manifest.v1.json"
)
SUPPORTED_BUNDLE_VERSION = "1.0.0"
SUPPORTED_SCHEMA_VERSION = "firewatch.scientific-snapshot.v1"
SUPPORTED_DATABASE_USER_VERSION = 1
EXPECTED_WEATHER_LOCATION_COUNT = 169
ANALYSIS_START = date(2021, 1, 1)
ANALYSIS_END = date(2025, 12, 31)
SPIN_UP_START = date(2020, 1, 1)
SPIN_UP_END = date(2020, 12, 31)
EXPECTED_PAYLOADS = {
    "data/scientific.sqlite": "application/vnd.sqlite3",
    "coverage/province.geojson": "application/geo+json",
    "coverage/weather-grid.geojson": "application/geo+json",
}
DAILY_COLUMNS = {
    "weather_id",
    "date",
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "rain_24h",
    "ffmc",
    "dmc",
    "dc",
    "isi",
    "bui",
    "fwi",
    "firms_count",
}
DATABASE_COLUMNS = {
    "snapshot_metadata": (
        ("key", "TEXT", 1, 1),
        ("value", "TEXT", 1, 0),
    ),
    "weather_locations": (
        ("weather_id", "TEXT", 1, 1),
        ("cell_id", "TEXT", 1, 0),
        ("weather_lat", "REAL", 1, 0),
        ("weather_lon", "REAL", 1, 0),
        ("center_lat", "REAL", 1, 0),
        ("center_lon", "REAL", 1, 0),
        ("center_inside", "INTEGER", 1, 0),
        ("intersects", "INTEGER", 1, 0),
    ),
    "weather_daily": (
        ("weather_id", "TEXT", 1, 1),
        ("date", "TEXT", 1, 2),
        ("temperature_2m", "REAL", 1, 0),
        ("relative_humidity_2m", "REAL", 1, 0),
        ("wind_speed_10m", "REAL", 1, 0),
        ("rain_24h", "REAL", 1, 0),
        ("ffmc", "REAL", 1, 0),
        ("dmc", "REAL", 1, 0),
        ("dc", "REAL", 1, 0),
        ("isi", "REAL", 1, 0),
        ("bui", "REAL", 1, 0),
        ("fwi", "REAL", 1, 0),
        ("firms_count", "INTEGER", 1, 0),
    ),
    "monthly_fwi_reference": (
        ("weather_id", "TEXT", 1, 1),
        ("month", "INTEGER", 1, 2),
        ("median_fwi", "REAL", 1, 0),
    ),
}


class SnapshotValidationError(RuntimeError):
    """Raised when a provisioned scientific snapshot fails closed validation."""


@dataclass
class ValidatedSnapshot:
    directory: Path
    manifest: dict[str, Any]
    province: dict[str, Any]
    coverage: dict[str, Any]
    connection: sqlite3.Connection

    @property
    def release_id(self) -> str:
        return self.manifest["release_id"]

    def close(self) -> None:
        self.connection.close()


def _fail(message: str) -> SnapshotValidationError:
    return SnapshotValidationError(f"Scientific snapshot validation failed: {message}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_geojson(path: Path, label: str) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _fail(f"{label} is not readable valid GeoJSON: {error}") from error
    if not isinstance(document, dict):
        raise _fail(f"{label} must contain a GeoJSON object")
    if document.get("type") != "FeatureCollection":
        raise _fail(f"{label} must be a GeoJSON FeatureCollection")
    if not isinstance(document.get("features"), list) or not document["features"]:
        raise _fail(f"{label} must contain features")
    return document


def _date_sequence(start: date, end: date) -> list[str]:
    return [
        (start + timedelta(days=offset)).isoformat()
        for offset in range((end - start).days + 1)
    ]


def _check_geometry(geometry: Any, label: str) -> None:
    if geometry.is_empty or not geometry.is_valid:
        raise _fail(f"{label} geometry is empty or invalid")
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise _fail(f"{label} geometry must be Polygon or MultiPolygon")


def _check_database(
    connection: sqlite3.Connection,
    analysis_dates: list[str],
    spin_up_dates: list[str],
    expected_release_id: str,
) -> set[str]:
    try:
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if user_version != SUPPORTED_DATABASE_USER_VERSION:
            raise _fail(f"unsupported SQLite user_version: {user_version}")

        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise _fail(f"SQLite integrity_check returned {integrity}")

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        expected_tables = {
            "snapshot_metadata",
            "weather_locations",
            "weather_daily",
            "monthly_fwi_reference",
        }
        if tables != expected_tables:
            raise _fail(
                f"SQLite table set mismatch; missing={sorted(expected_tables - tables)}, "
                f"unexpected={sorted(tables - expected_tables)}"
            )
        for table, expected_columns in DATABASE_COLUMNS.items():
            actual_columns = tuple(
                (row[1], row[2].upper(), row[3], row[5])
                for row in connection.execute(f"PRAGMA table_info({table})")
            )
            if actual_columns != expected_columns:
                raise _fail(f"SQLite {table} schema mismatch")

        metadata = dict(connection.execute("SELECT key, value FROM snapshot_metadata"))
        if metadata.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
            raise _fail("SQLite snapshot schema version is unsupported")
        if metadata.get("release_id") != expected_release_id:
            raise _fail("SQLite release_id does not match the manifest")

        ids = {
            row[0]
            for row in connection.execute(
                "SELECT weather_id FROM weather_locations"
            )
        }
        if len(ids) != EXPECTED_WEATHER_LOCATION_COUNT:
            raise _fail(
                f"SQLite must contain exactly {EXPECTED_WEATHER_LOCATION_COUNT} weather_id values"
            )
        daily_ids = {
            row[0]
            for row in connection.execute("SELECT DISTINCT weather_id FROM weather_daily")
        }
        if daily_ids != ids:
            raise _fail("weather_daily IDs do not match the canonical weather_locations table")

        expected_dates = spin_up_dates + analysis_dates
        summary = connection.execute(
            "SELECT COUNT(*), MIN(date), MAX(date) FROM weather_daily"
        ).fetchone()
        if summary != (len(ids) * len(expected_dates), expected_dates[0], expected_dates[-1]):
            raise _fail("SQLite daily rows do not cover every configured location and date")

        incomplete_dates = connection.execute(
            "SELECT date FROM weather_daily GROUP BY date HAVING COUNT(*) != ? LIMIT 1",
            (len(ids),),
        ).fetchone()
        if incomplete_dates is not None:
            raise _fail(f"SQLite has incomplete weather_id coverage on {incomplete_dates[0]}")

        analysis_count = connection.execute(
            "SELECT COUNT(*) FROM weather_daily WHERE date BETWEEN ? AND ?",
            (analysis_dates[0], analysis_dates[-1]),
        ).fetchone()[0]
        if analysis_count != len(ids) * len(analysis_dates):
            raise _fail("SQLite analysis period does not contain complete daily coverage")
        distinct_dates = connection.execute(
            "SELECT COUNT(DISTINCT date) FROM weather_daily"
        ).fetchone()[0]
        if distinct_dates != len(expected_dates):
            raise _fail("SQLite has unsupported or missing daily dates")

        references = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT weather_id), MIN(month), MAX(month) "
            "FROM monthly_fwi_reference"
        ).fetchone()
        if references != (len(ids) * 12, len(ids), 1, 12):
            raise _fail("SQLite monthly FWI reference must contain every location and month")
        incomplete_references = connection.execute(
            "SELECT weather_id FROM monthly_fwi_reference "
            "GROUP BY weather_id HAVING COUNT(DISTINCT month) != 12 LIMIT 1"
        ).fetchone()
        if incomplete_references is not None:
            raise _fail(
                f"SQLite monthly reference is incomplete for {incomplete_references[0]}"
            )

        invalid_values = connection.execute(
            "SELECT weather_id, date FROM weather_daily "
            "WHERE temperature_2m != temperature_2m OR abs(temperature_2m) > 1e308 "
            "OR relative_humidity_2m NOT BETWEEN 0 AND 100 "
            "OR wind_speed_10m < 0 OR rain_24h < 0 "
            "OR abs(wind_speed_10m) > 1e308 OR abs(rain_24h) > 1e308 "
            "OR ffmc < 0 OR abs(ffmc) > 1e308 OR dmc < 0 OR abs(dmc) > 1e308 "
            "OR dc < 0 OR abs(dc) > 1e308 OR isi < 0 OR abs(isi) > 1e308 "
            "OR bui < 0 OR abs(bui) > 1e308 OR fwi < 0 OR abs(fwi) > 1e308 "
            "OR firms_count < 0 LIMIT 1"
        ).fetchone()
        if invalid_values is not None:
            raise _fail(
                f"SQLite contains invalid scientific values at {invalid_values[0]} {invalid_values[1]}"
            )
        return ids
    except sqlite3.DatabaseError as error:
        raise _fail(f"SQLite schema or integrity check failed: {error}") from error


def validate_snapshot(
    directory: Path,
    expected_version: str,
    expected_manifest_sha256: str,
) -> ValidatedSnapshot:
    snapshot_dir = directory.expanduser().resolve()
    manifest_path = snapshot_dir / "manifest.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as error:
        raise _fail(f"manifest.json is missing or unreadable: {error}") from error

    actual_manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if actual_manifest_sha256.lower() != expected_manifest_sha256.lower():
        raise _fail("manifest SHA-256 does not match FIREWATCH_SNAPSHOT_MANIFEST_SHA256")

    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _fail(f"manifest.json is invalid JSON: {error}") from error

    try:
        schema = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).validate(manifest)
    except OSError as error:
        raise _fail(f"manifest schema is unavailable: {error}") from error
    except (json.JSONDecodeError, ValidationError) as error:
        raise _fail(f"manifest schema validation failed: {error}") from error

    if manifest["bundle_version"] != expected_version:
        raise _fail("bundle_version does not match FIREWATCH_SNAPSHOT_VERSION")
    if manifest["bundle_version"] != SUPPORTED_BUNDLE_VERSION:
        raise _fail(f"unsupported bundle_version: {manifest['bundle_version']}")
    if manifest["schema_version"] != SUPPORTED_SCHEMA_VERSION:
        raise _fail(f"unsupported schema_version: {manifest['schema_version']}")

    payloads = {payload["path"]: payload for payload in manifest["payloads"]}
    if set(payloads) != set(EXPECTED_PAYLOADS):
        raise _fail("manifest must declare exactly the three supported payloads")

    for relative_path, expected_media_type in EXPECTED_PAYLOADS.items():
        entry = payloads[relative_path]
        if entry["media_type"] != expected_media_type:
            raise _fail(f"unexpected media type for {relative_path}")
        path = (snapshot_dir / relative_path).resolve()
        if not path.is_relative_to(snapshot_dir):
            raise _fail(f"payload path escapes snapshot directory: {relative_path}")
        try:
            size_bytes = path.stat().st_size
        except OSError as error:
            raise _fail(f"payload is missing or unreadable: {relative_path}") from error
        if not path.is_file():
            raise _fail(f"payload is not a regular file: {relative_path}")
        if size_bytes != entry["size_bytes"]:
            raise _fail(f"payload size does not match manifest: {relative_path}")
        if _sha256(path) != entry["sha256"]:
            raise _fail(f"payload SHA-256 does not match manifest: {relative_path}")

    analysis_range = manifest["date_coverage"]["analysis"]
    spin_up_range = manifest["date_coverage"]["spin_up"]
    try:
        analysis_start, analysis_end = date.fromisoformat(analysis_range["start"]), date.fromisoformat(
            analysis_range["end"]
        )
        spin_up_start, spin_up_end = date.fromisoformat(spin_up_range["start"]), date.fromisoformat(
            spin_up_range["end"]
        )
    except ValueError as error:
        raise _fail(f"date coverage is invalid: {error}") from error
    if analysis_start > analysis_end or spin_up_start > spin_up_end:
        raise _fail("date coverage ranges are reversed")
    analysis_dates = _date_sequence(analysis_start, analysis_end)
    spin_up_dates = _date_sequence(spin_up_start, spin_up_end)

    province = _read_geojson(snapshot_dir / "coverage/province.geojson", "province.geojson")
    coverage = _read_geojson(
        snapshot_dir / "coverage/weather-grid.geojson", "weather-grid.geojson"
    )
    province_features = province["features"]
    if len(province_features) != 1:
        raise _fail("province.geojson must contain exactly one provincial feature")
    try:
        province_geometry = shape(province_features[0]["geometry"])
        _check_geometry(province_geometry, "province")
        coverage_features: dict[str, dict[str, Any]] = {}
        for feature in coverage["features"]:
            properties = feature["properties"]
            weather_id = properties["weather_id"]
            if not isinstance(weather_id, str) or not weather_id.strip():
                raise _fail("coverage features must have a canonical weather_id")
            if weather_id in coverage_features:
                raise _fail(f"coverage contains duplicate weather_id {weather_id}")
            coverage_features[weather_id] = feature
            geometry = shape(feature["geometry"])
            _check_geometry(geometry, f"coverage {weather_id}")
            if not geometry.intersects(province_geometry):
                raise _fail(f"coverage feature {weather_id} does not intersect La Rioja")
            if not properties.get("intersects"):
                raise _fail(f"coverage feature {weather_id} has an inconsistent intersects flag")
            center = properties["center"]
            if not (-90 <= center["latitude"] <= 90 and -180 <= center["longitude"] <= 180):
                raise _fail(f"coverage feature {weather_id} has invalid center coordinates")
            if properties["available_dates"] != analysis_dates:
                raise _fail(f"coverage feature {weather_id} has unsupported available dates")
    except (KeyError, TypeError, ValueError) as error:
        raise _fail(f"GeoJSON coverage is invalid: {error}") from error

    database_path = snapshot_dir / "data/scientific.sqlite"
    database_uri_path = quote(str(database_path).replace("\\", "/"), safe="/:")
    uri = f"file:{database_uri_path}?mode=ro&immutable=1"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.DatabaseError as error:
        raise _fail(f"SQLite could not be opened read-only: {error}") from error
    try:
        database_ids = _check_database(
            connection,
            analysis_dates,
            spin_up_dates,
            expected_release_id=manifest["release_id"],
        )
        if set(coverage_features) != database_ids:
            missing_features = sorted(database_ids - set(coverage_features))
            missing_rows = sorted(set(coverage_features) - database_ids)
            raise _fail(
                "database and GeoJSON weather_id sets differ; "
                f"database_without_feature={missing_features[:3]}, "
                f"feature_without_database={missing_rows[:3]}"
            )
        locations = {
            row[0]: row[1:]
            for row in connection.execute(
                "SELECT weather_id, weather_lat, weather_lon, center_lat, center_lon, "
                "center_inside, intersects FROM weather_locations"
            )
        }
        for weather_id, feature in coverage_features.items():
            weather_lat, weather_lon, center_lat, center_lon, center_inside, intersects = locations[
                weather_id
            ]
            properties = feature["properties"]
            center = properties["center"]
            if weather_id != f"{weather_lat:.5f}_{weather_lon:.5f}":
                raise _fail(f"SQLite weather_id {weather_id} is not canonical for its coordinates")
            if not (-90 <= weather_lat <= 90 and -180 <= weather_lon <= 180):
                raise _fail(f"SQLite weather location {weather_id} has invalid coordinates")
            if not (-90 <= center_lat <= 90 and -180 <= center_lon <= 180):
                raise _fail(f"SQLite grid center {weather_id} has invalid coordinates")
            if (
                abs(center["latitude"] - center_lat) > 1e-8
                or abs(center["longitude"] - center_lon) > 1e-8
            ):
                raise _fail(f"coverage feature {weather_id} has mismatched grid center coordinates")
            if bool(properties["center_inside"]) != bool(center_inside):
                raise _fail(f"coverage feature {weather_id} has an inconsistent center_inside flag")
            if bool(properties["intersects"]) != bool(intersects):
                raise _fail(f"coverage feature {weather_id} has an inconsistent intersects flag")
            actual_center_inside = province_geometry.covers(
                Point(center["longitude"], center["latitude"])
            )
            if actual_center_inside != bool(center_inside):
                raise _fail(
                    f"coverage feature {weather_id} center_inside disagrees with province geometry"
                )
        center_inside_count = sum(
            feature["properties"]["center_inside"] for feature in coverage["features"]
        )
        if center_inside_count != manifest["spatial_coverage"]["center_inside_count"]:
            raise _fail("manifest center_inside_count does not match the coverage features")
        return ValidatedSnapshot(
            directory=snapshot_dir,
            manifest=manifest,
            province=province,
            coverage=coverage,
            connection=connection,
        )
    except Exception:
        connection.close()
        raise
