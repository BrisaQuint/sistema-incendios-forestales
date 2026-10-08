from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from pyogrio import set_gdal_config_options
from shapely.geometry import mapping

from sistema_incendios_forestales.snapshot import (
    EXPECTED_WEATHER_LOCATION_COUNT,
    SUPPORTED_BUNDLE_VERSION,
    SUPPORTED_SCHEMA_VERSION,
    validate_snapshot,
)

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
SNAPSHOTS = ROOT / "data" / "snapshots"
SQL_SCHEMA_PATH = ROOT / "contracts" / "schemas" / "scientific-snapshot.v1.sql"
ANALYSIS_START = date(2021, 1, 1)
ANALYSIS_END = date(2025, 12, 31)
SPIN_UP_START = date(2020, 1, 1)
SPIN_UP_END = date(2020, 12, 31)
ANALYSIS_YEARS = range(2021, 2026)
ALL_YEARS = range(2020, 2026)
FWI_COLUMNS = ("ffmc", "dmc", "dc", "isi", "bui", "fwi")
WEATHER_COLUMNS = (
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "rain_24h",
)
DAILY_COLUMNS = ("weather_id", "date", *WEATHER_COLUMNS, *FWI_COLUMNS, "firms_count")
RELEASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class SnapshotBuildError(RuntimeError):
    """Raised when an offline source artifact cannot produce a valid snapshot."""


def _require_columns(frame: pd.DataFrame, required: set[str], source: Path) -> None:
    missing = sorted(required - set(frame.columns))
    if missing:
        raise SnapshotBuildError(f"{source}: required columns are missing: {missing}")


def _read_csv(path: Path, required: set[str]) -> pd.DataFrame:
    if not path.is_file():
        raise SnapshotBuildError(f"Required offline input is missing: {path}")
    frame = pd.read_csv(path, dtype={"weather_id": str})
    _require_columns(frame, required, path)
    return frame


def _normalise_dates(frame: pd.DataFrame, source: Path) -> pd.DataFrame:
    try:
        dates = pd.to_datetime(frame["date"], errors="raise")
    except (TypeError, ValueError) as error:
        raise SnapshotBuildError(f"{source}: invalid date values: {error}") from error
    if dates.dt.tz is not None:
        raise SnapshotBuildError(f"{source}: local date column must not contain a timezone")
    normalised = frame.copy()
    normalised["date"] = dates.dt.strftime("%Y-%m-%d")
    return normalised


def _validate_daily_frame(
    frame: pd.DataFrame,
    source: Path,
    expected_weather_ids: set[str],
    expected_dates: list[str],
    columns: tuple[str, ...],
    *,
    validate_weather_values: bool = False,
) -> pd.DataFrame:
    _require_columns(frame, {"weather_id", "date", *columns}, source)
    frame = _normalise_dates(frame, source)
    if frame.empty:
        raise SnapshotBuildError(f"{source}: dataset is empty")
    if frame["weather_id"].isna().any() or (frame["weather_id"].str.strip() == "").any():
        raise SnapshotBuildError(f"{source}: weather_id contains missing or blank values")
    if frame.duplicated(["weather_id", "date"]).any():
        raise SnapshotBuildError(f"{source}: duplicate weather_id/date records")
    if set(frame["weather_id"]) != expected_weather_ids:
        raise SnapshotBuildError(f"{source}: weather_id set does not match the 169-point grid")
    if sorted(frame["date"].unique()) != expected_dates:
        raise SnapshotBuildError(f"{source}: date coverage is incomplete or outside its year")

    numeric_columns = list(columns)
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    values = frame[numeric_columns].to_numpy(dtype=np.float64)
    if not np.isfinite(values).all():
        raise SnapshotBuildError(f"{source}: scientific values contain null or infinite values")
    if len(frame) != EXPECTED_WEATHER_LOCATION_COUNT * len(expected_dates):
        raise SnapshotBuildError(f"{source}: expected one row per weather_id/date")

    if validate_weather_values:
        if not frame["relative_humidity_2m"].between(0, 100).all():
            raise SnapshotBuildError(f"{source}: relative_humidity_2m is outside 0–100")
        if (frame[["wind_speed_10m", "rain_24h"]] < 0).any().any():
            raise SnapshotBuildError(f"{source}: wind or precipitation values are negative")
    elif (frame[list(FWI_COLUMNS)] < 0).any().any():
        raise SnapshotBuildError(f"{source}: FWI components contain negative values")

    return frame


def _load_location_index() -> tuple[pd.DataFrame, set[str]]:
    path = PROCESSED / "weather_locations_larioja.csv"
    locations = _read_csv(
        path,
        {
            "cell_id",
            "center_inside",
            "weather_lat",
            "weather_lon",
            "weather_id",
        },
    )
    if len(locations) != EXPECTED_WEATHER_LOCATION_COUNT:
        raise SnapshotBuildError(f"{path}: expected exactly 169 location mappings")
    if locations["cell_id"].duplicated().any() or locations["weather_id"].duplicated().any():
        raise SnapshotBuildError(f"{path}: cell_id and weather_id mappings must be one-to-one")
    for row in locations.itertuples(index=False):
        canonical_id = f"{float(row.weather_lat):.5f}_{float(row.weather_lon):.5f}"
        if row.weather_id != canonical_id:
            raise SnapshotBuildError(
                f"{path}: weather_id {row.weather_id!r} is not the canonical coordinate ID"
            )
    return locations, set(locations["weather_id"])


def _load_coverage(
    locations: pd.DataFrame,
) -> tuple[dict[str, Any], int, list[tuple[Any, ...]]]:
    grid_path = PROCESSED / "weather_grid_larioja.geojson"
    if not grid_path.is_file():
        raise SnapshotBuildError(f"Required offline coverage is missing: {grid_path}")
    try:
        set_gdal_config_options({"OGR_GEOJSON_MAX_OBJ_SIZE": "0"})
        grid = gpd.read_file(grid_path)
    except Exception as error:
        raise SnapshotBuildError(f"{grid_path}: unable to read coverage GeoJSON: {error}") from error
    if grid.crs is None:
        raise SnapshotBuildError(f"{grid_path}: source CRS is missing")
    grid = grid.to_crs("EPSG:4326")
    _require_columns(grid, {"cell_id", "center_lat", "center_lon", "center_inside"}, grid_path)
    if len(grid) != EXPECTED_WEATHER_LOCATION_COUNT or grid["cell_id"].duplicated().any():
        raise SnapshotBuildError(f"{grid_path}: expected 169 unique coverage cells")

    locations = locations.copy()
    locations["center_inside"] = locations["center_inside"].astype(bool)
    grid["center_inside"] = grid["center_inside"].astype(bool)
    if set(grid["cell_id"]) != set(locations["cell_id"]):
        raise SnapshotBuildError(f"{grid_path}: cell IDs do not match the weather location mapping")
    joined = grid.merge(
        locations[
            ["cell_id", "weather_id", "weather_lat", "weather_lon", "center_inside"]
        ],
        on="cell_id",
        how="inner",
        validate="one_to_one",
        suffixes=("_grid", "_location"),
    )
    if not (
        joined["center_inside_grid"] == joined["center_inside_location"]
    ).all():
        raise SnapshotBuildError(f"{grid_path}: center_inside differs from the source location map")

    available_dates = pd.date_range(ANALYSIS_START, ANALYSIS_END, freq="D").strftime(
        "%Y-%m-%d"
    ).tolist()
    features: list[dict[str, Any]] = []
    location_rows: list[tuple[Any, ...]] = []
    for row in joined.itertuples():
        geometry = row.geometry
        if geometry.is_empty or not geometry.is_valid:
            raise SnapshotBuildError(f"{grid_path}: invalid geometry for {row.weather_id}")
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise SnapshotBuildError(f"{grid_path}: unsupported geometry for {row.weather_id}")
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(geometry),
                "properties": {
                    "weather_id": row.weather_id,
                    "center": {
                        "latitude": float(row.center_lat),
                        "longitude": float(row.center_lon),
                    },
                    "center_inside": bool(row.center_inside_grid),
                    "intersects": True,
                    "available_dates": available_dates,
                },
            }
        )
        location_rows.append(
            (
                str(row.weather_id),
                str(row.cell_id),
                float(row.weather_lat),
                float(row.weather_lon),
                float(row.center_lat),
                float(row.center_lon),
                int(bool(row.center_inside_grid)),
                1,
            )
        )
    features.sort(key=lambda feature: feature["properties"]["weather_id"])
    location_rows.sort(key=lambda record: record[0])
    return (
        {"type": "FeatureCollection", "features": features},
        int(joined["center_inside_grid"].sum()),
        location_rows,
    )


def _load_province() -> dict[str, Any]:
    path = ROOT / "data" / "raw" / "boundaries" / "provincia.geojson"
    if not path.is_file():
        raise SnapshotBuildError(f"Required IGN provincial boundary is missing: {path}")
    try:
        set_gdal_config_options({"OGR_GEOJSON_MAX_OBJ_SIZE": "0"})
        provinces = gpd.read_file(path, where="nam = 'La Rioja'")
    except Exception as error:
        raise SnapshotBuildError(f"{path}: unable to read La Rioja boundary: {error}") from error
    _require_columns(provinces, {"nam"}, path)
    province = provinces[provinces["nam"] == "La Rioja"]
    if len(province) != 1:
        raise SnapshotBuildError(f"{path}: expected exactly one IGN feature named La Rioja")
    province = province.to_crs("EPSG:4326")
    geometry = province.geometry.iloc[0]
    if geometry.is_empty or not geometry.is_valid:
        raise SnapshotBuildError(f"{path}: La Rioja geometry is empty or invalid")
    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise SnapshotBuildError(f"{path}: La Rioja geometry must be Polygon or MultiPolygon")
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": mapping(geometry),
                "properties": {
                    "name": "La Rioja",
                    "source": "Instituto Geográfico Nacional de Argentina",
                },
            }
        ],
    }


def _load_scientific_rows(
    weather_ids: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, dict[str, Any]]]:
    weather_parts: list[pd.DataFrame] = []
    fwi_parts: list[pd.DataFrame] = []
    yearly_quality: dict[str, dict[str, Any]] = {}

    for year in ALL_YEARS:
        weather_path = PROCESSED / "weather" / f"weather_fwi_daily_{year}.csv.gz"
        fwi_path = PROCESSED / "fwi" / f"fwi_larioja_{year}.csv.gz"
        expected_dates = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D").strftime(
            "%Y-%m-%d"
        ).tolist()
        weather = _validate_daily_frame(
            _read_csv(weather_path, {"weather_id", "date", *WEATHER_COLUMNS}),
            weather_path,
            weather_ids,
            expected_dates,
            WEATHER_COLUMNS,
            validate_weather_values=True,
        )
        fwi = _validate_daily_frame(
            _read_csv(fwi_path, {"weather_id", "date", *FWI_COLUMNS}),
            fwi_path,
            weather_ids,
            expected_dates,
            FWI_COLUMNS,
        )
        weather_parts.append(weather)
        fwi_parts.append(fwi)
        yearly_quality[str(year)] = {
            "status": "passed",
            "observed": len(weather),
            "expected": EXPECTED_WEATHER_LOCATION_COUNT * len(expected_dates),
        }

    weather_daily = pd.concat(weather_parts, ignore_index=True)
    fwi_daily = pd.concat(fwi_parts, ignore_index=True)
    if weather_daily.duplicated(["weather_id", "date"]).any():
        raise SnapshotBuildError("Weather source files contain duplicate weather_id/date records")
    if fwi_daily.duplicated(["weather_id", "date"]).any():
        raise SnapshotBuildError("FWI source files contain duplicate weather_id/date records")

    analysis_path = PROCESSED / "analytical_larioja_2021_2025.csv.gz"
    analytical = _validate_daily_frame(
        _read_csv(analysis_path, {"weather_id", "date", *FWI_COLUMNS, "firms_count", "firms_detected"}),
        analysis_path,
        weather_ids,
        pd.date_range(ANALYSIS_START, ANALYSIS_END, freq="D").strftime("%Y-%m-%d").tolist(),
        (*FWI_COLUMNS, "firms_count", "firms_detected"),
    )
    if (analytical[["firms_count", "firms_detected"]] < 0).any().any():
        raise SnapshotBuildError(f"{analysis_path}: FIRMS counts cannot be negative")
    if not (analytical["firms_detected"] == (analytical["firms_count"] > 0).astype(int)).all():
        raise SnapshotBuildError(f"{analysis_path}: firms_detected disagrees with firms_count")
    if not np.equal(analytical["firms_count"], np.floor(analytical["firms_count"])).all():
        raise SnapshotBuildError(f"{analysis_path}: firms_count must contain integers")
    analytical["firms_count"] = analytical["firms_count"].astype("int64")

    analytical_comparison = analytical[
        ["weather_id", "date", *FWI_COLUMNS]
    ].merge(
        fwi_daily[fwi_daily["date"].between(ANALYSIS_START.isoformat(), ANALYSIS_END.isoformat())][
            ["weather_id", "date", *FWI_COLUMNS]
        ],
        on=["weather_id", "date"],
        suffixes=("_analytical", "_fwi"),
        validate="one_to_one",
    )
    for column in FWI_COLUMNS:
        if not np.allclose(
            analytical_comparison[f"{column}_analytical"],
            analytical_comparison[f"{column}_fwi"],
            rtol=0,
            atol=1e-12,
        ):
            raise SnapshotBuildError(
                f"{analysis_path}: {column} differs from the validated FWI source"
            )

    firms_detection_total = int(analytical["firms_count"].sum())
    detected_days = int(analytical["firms_detected"].sum())
    if firms_detection_total != 10956 or detected_days != 2286:
        raise SnapshotBuildError(
            f"{analysis_path}: expected 10,956 detections across 2,286 detected cell-days; "
            f"observed {firms_detection_total} and {detected_days}"
        )

    weather_daily = weather_daily.merge(
        fwi_daily, on=["weather_id", "date"], how="inner", validate="one_to_one"
    )
    weather_daily = weather_daily.merge(
        analytical[["weather_id", "date", "firms_count"]],
        on=["weather_id", "date"],
        how="left",
        validate="one_to_one",
    )
    weather_daily["firms_count"] = weather_daily["firms_count"].fillna(0).astype("int64")
    weather_daily = weather_daily[list(DAILY_COLUMNS)].sort_values(
        ["weather_id", "date"]
    )
    expected_daily_rows = EXPECTED_WEATHER_LOCATION_COUNT * sum(
        len(pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D"))
        for year in ALL_YEARS
    )
    if len(weather_daily) != expected_daily_rows:
        raise SnapshotBuildError(
            f"Combined daily dataset has {len(weather_daily)} rows; expected {expected_daily_rows}"
        )

    quality_checks = {
        "weather_daily_records": {
            "status": "passed",
            "observed": len(weather_daily),
            "expected": expected_daily_rows,
        },
        "weather_location_count": {
            "status": "passed",
            "observed": len(weather_ids),
            "expected": EXPECTED_WEATHER_LOCATION_COUNT,
        },
        "analysis_cell_days": {
            "status": "passed",
            "observed": len(analytical),
            "expected": EXPECTED_WEATHER_LOCATION_COUNT
            * len(pd.date_range(ANALYSIS_START, ANALYSIS_END, freq="D")),
        },
        "firms_detection_count": {
            "status": "passed",
            "observed": firms_detection_total,
            "expected": 10956,
        },
        "firms_detected_cell_days": {
            "status": "passed",
            "observed": detected_days,
            "expected": 2286,
        },
        "missing_values": {"status": "passed", "observed": 0, "expected": 0},
        "duplicate_weather_date_keys": {"status": "passed", "observed": 0, "expected": 0},
        "negative_fwi_components": {"status": "passed", "observed": 0, "expected": 0},
        "non_finite_scientific_values": {"status": "passed", "observed": 0, "expected": 0},
        **{
            f"weather_daily_records_{year}": check
            for year, check in yearly_quality.items()
        },
    }
    return weather_daily, analytical, quality_checks


def _write_database(
    path: Path,
    weather_daily: pd.DataFrame,
    analytical: pd.DataFrame,
    location_rows: list[tuple[Any, ...]],
    release_id: str,
) -> None:
    if not SQL_SCHEMA_PATH.is_file():
        raise SnapshotBuildError(f"SQLite schema is missing: {SQL_SCHEMA_PATH}")
    connection = sqlite3.connect(path)
    try:
        connection.executescript(SQL_SCHEMA_PATH.read_text(encoding="utf-8"))
        metadata = {
            "schema_version": SUPPORTED_SCHEMA_VERSION,
            "release_id": release_id,
            "analysis_start": ANALYSIS_START.isoformat(),
            "analysis_end": ANALYSIS_END.isoformat(),
            "spin_up_start": SPIN_UP_START.isoformat(),
            "spin_up_end": SPIN_UP_END.isoformat(),
            "source_references": json.dumps(
                [
                    "data/processed/weather/weather_fwi_daily_2020-2025.csv.gz",
                    "data/processed/fwi/fwi_larioja_2020-2025.csv.gz",
                    "data/processed/analytical_larioja_2021_2025.csv.gz",
                ]
            ),
        }
        connection.executemany(
            "INSERT INTO snapshot_metadata (key, value) VALUES (?, ?)",
            sorted(metadata.items()),
        )
        connection.executemany(
            "INSERT INTO weather_locations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            location_rows,
        )
        rows = (
            (
                str(row.weather_id),
                str(row.date),
                float(row.temperature_2m),
                float(row.relative_humidity_2m),
                float(row.wind_speed_10m),
                float(row.rain_24h),
                float(row.ffmc),
                float(row.dmc),
                float(row.dc),
                float(row.isi),
                float(row.bui),
                float(row.fwi),
                int(row.firms_count),
            )
            for row in weather_daily.itertuples(index=False)
        )
        connection.executemany(
            "INSERT INTO weather_daily VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

        reference = analytical[["weather_id", "date", "fwi"]].copy()
        reference["month"] = pd.to_datetime(reference["date"]).dt.month
        medians = (
            reference.groupby(["weather_id", "month"], as_index=False)["fwi"]
            .median()
            .rename(columns={"fwi": "median_fwi"})
        )
        if len(medians) != EXPECTED_WEATHER_LOCATION_COUNT * 12:
            raise SnapshotBuildError("Monthly FWI reference does not cover all locations and months")
        connection.executemany(
            "INSERT INTO monthly_fwi_reference VALUES (?, ?, ?)",
            (
                (str(row.weather_id), int(row.month), float(row.median_fwi))
                for row in medians.itertuples(index=False)
            ),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _payload_entry(directory: Path, relative_path: str, media_type: str) -> dict[str, Any]:
    path = directory / relative_path
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": relative_path,
        "media_type": media_type,
        "size_bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def _write_json(path: Path, document: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def build_snapshot(release_id: str, output: Path | None = None) -> tuple[Path, str]:
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        raise SnapshotBuildError("release_id must use 1–64 letters, digits, dots, underscores, or hyphens")

    destination = (output or SNAPSHOTS / release_id).expanduser().resolve()
    if destination.exists():
        raise SnapshotBuildError(f"Refusing to overwrite existing immutable snapshot: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    locations, weather_ids = _load_location_index()
    if len(weather_ids) != EXPECTED_WEATHER_LOCATION_COUNT:
        raise SnapshotBuildError("Location inventory must contain exactly 169 canonical weather_id values")

    weather_daily, analytical, quality_checks = _load_scientific_rows(weather_ids)
    coverage, center_inside_count, location_rows = _load_coverage(locations)
    province = _load_province()

    temporary_directory = tempfile.mkdtemp(
        prefix=f".{release_id}.", dir=destination.parent
    )
    temporary_path = Path(temporary_directory)
    manifest_hash = ""
    try:
        (temporary_path / "data").mkdir()
        (temporary_path / "coverage").mkdir()
        _write_database(
            temporary_path / "data" / "scientific.sqlite",
            weather_daily,
            analytical,
            location_rows,
            release_id,
        )
        _write_json(temporary_path / "coverage" / "province.geojson", province)
        _write_json(temporary_path / "coverage" / "weather-grid.geojson", coverage)

        source_references = [
            {
                "source_id": "ign-boundaries",
                "name": "Instituto Geográfico Nacional de Argentina",
                "reference": "data/raw/boundaries/provincia.geojson",
            },
            {
                "source_id": "open-meteo-era5",
                "name": "Open-Meteo Historical API, ERA5 processed offline",
                "reference": "data/processed/weather/weather_fwi_daily_2020-2025.csv.gz",
            },
            {
                "source_id": "cffdrs-fwi",
                "name": "Canadian Fire Weather Index System, classic method",
                "reference": "data/processed/fwi/fwi_larioja_2020-2025.csv.gz",
            },
            {
                "source_id": "nasa-firms-viirs-snpp",
                "name": "NASA FIRMS VIIRS S-NPP type=0 offline associations",
                "reference": "data/processed/analytical_larioja_2021_2025.csv.gz",
            },
        ]
        manifest = {
            "bundle_version": SUPPORTED_BUNDLE_VERSION,
            "schema_version": SUPPORTED_SCHEMA_VERSION,
            "release_id": release_id,
            "provenance": (
                "FireWatch La Rioja offline scientific snapshot. "
                "ERA5 weather, classic Canadian FWI and historical NASA FIRMS associations; "
                "2020 is spin-up and 2021–2025 is the analysis period."
            ),
            "source_references": source_references,
            "date_coverage": {
                "spin_up": {
                    "start": SPIN_UP_START.isoformat(),
                    "end": SPIN_UP_END.isoformat(),
                },
                "analysis": {
                    "start": ANALYSIS_START.isoformat(),
                    "end": ANALYSIS_END.isoformat(),
                },
            },
            "spatial_coverage": {
                "province": "La Rioja, Argentina",
                "crs": "EPSG:4326",
                "weather_location_count": EXPECTED_WEATHER_LOCATION_COUNT,
                "center_inside_count": center_inside_count,
            },
            "quality_checks": quality_checks,
            "payloads": [
                _payload_entry(
                    temporary_path,
                    "data/scientific.sqlite",
                    "application/vnd.sqlite3",
                ),
                _payload_entry(
                    temporary_path,
                    "coverage/province.geojson",
                    "application/geo+json",
                ),
                _payload_entry(
                    temporary_path,
                    "coverage/weather-grid.geojson",
                    "application/geo+json",
                ),
            ],
        }
        _write_json(temporary_path / "manifest.json", manifest)
        manifest_hash = hashlib.sha256(
            (temporary_path / "manifest.json").read_bytes()
        ).hexdigest()

        validated = validate_snapshot(
            temporary_path,
            expected_version=SUPPORTED_BUNDLE_VERSION,
            expected_manifest_sha256=manifest_hash,
        )
        validated.close()

        os.replace(temporary_path, destination)
    except Exception:
        if temporary_path.exists():
            shutil.rmtree(temporary_path)
        raise

    validated = validate_snapshot(
        destination,
        expected_version=SUPPORTED_BUNDLE_VERSION,
        expected_manifest_sha256=manifest_hash,
    )
    validated.close()
    return destination, manifest_hash


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build and validate an immutable local FireWatch scientific snapshot."
    )
    parser.add_argument(
        "--release-id",
        required=True,
        help="Stable release identifier used in the bundle manifest and output directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help=f"Destination directory (default: {SNAPSHOTS}\\<release-id>).",
    )
    arguments = parser.parse_args()
    snapshot_path, digest = build_snapshot(arguments.release_id, arguments.output)
    print(f"Snapshot ready: {snapshot_path}")
    print(f"FIREWATCH_SNAPSHOT_VERSION={SUPPORTED_BUNDLE_VERSION}")
    print(f"FIREWATCH_SNAPSHOT_MANIFEST_SHA256={digest}")


if __name__ == "__main__":
    main()
