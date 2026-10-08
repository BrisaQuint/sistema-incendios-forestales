from __future__ import annotations

import sqlite3
from typing import Any
from uuid import UUID

from sistema_incendios_forestales.api.contracts import (
    AnalysisRequest,
    AnalysisResult,
    DataValue,
    DeterministicResult,
)
from sistema_incendios_forestales.snapshot import ValidatedSnapshot


class AnalysisContextError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _data_value(value: Any, unit: str) -> DataValue:
    if value is None:
        return DataValue(value=None, unit=unit, missing_reason="not_available_in_snapshot")
    return DataValue(value=float(value), unit=unit, missing_reason=None)


def _require_analysis_context(
    snapshot: ValidatedSnapshot, request: AnalysisRequest
) -> None:
    feature_by_id = {
        feature["properties"]["weather_id"]: feature
        for feature in snapshot.coverage["features"]
    }
    feature = feature_by_id.get(request.weather_id)
    if feature is None:
        raise AnalysisContextError(
            "UNKNOWN_WEATHER_ID", "weather_id is not part of the validated coverage."
        )
    available_dates = feature["properties"]["available_dates"]
    if request.date.isoformat() not in available_dates:
        raise AnalysisContextError(
            "DATE_NOT_AVAILABLE",
            "The requested local date is not available for this weather_id.",
        )


def build_deterministic_result(
    snapshot: ValidatedSnapshot,
    request: AnalysisRequest,
    analysis_id: UUID,
    manifest_sha256: str,
) -> AnalysisResult:
    _require_analysis_context(snapshot, request)
    day = request.date.isoformat()
    weather = snapshot.connection.execute(
        "SELECT temperature_2m, relative_humidity_2m, wind_speed_10m, rain_24h, "
        "ffmc, dmc, dc, isi, bui, fwi, firms_count "
        "FROM weather_daily WHERE weather_id = ? AND date = ?",
        (request.weather_id, day),
    ).fetchone()
    if weather is None:
        raise AnalysisContextError(
            "DATA_NOT_AVAILABLE", "No daily scientific row exists for this context."
        )

    reference = snapshot.connection.execute(
        "SELECT median_fwi FROM monthly_fwi_reference "
        "WHERE weather_id = ? AND month = ?",
        (request.weather_id, request.date.month),
    ).fetchone()
    historical_fwi = None if reference is None else reference[0]
    fwi = weather[9]
    difference = None if fwi is None or historical_fwi is None else fwi - historical_fwi
    manifest = snapshot.manifest
    result_refs = [
        f"snapshot:{snapshot.release_id}:weather_daily:{request.weather_id}:{day}",
    ]
    if reference is not None:
        result_refs.append(
            f"snapshot:{snapshot.release_id}:monthly_fwi_reference:"
            f"{request.weather_id}:{request.date.month:02d}"
        )
    result_refs.append(f"snapshot:{snapshot.release_id}:manifest")

    source_references = manifest["source_references"]
    provenance = {
        "release_id": snapshot.release_id,
        "bundle_version": manifest["bundle_version"],
        "schema_version": manifest["schema_version"],
        "manifest_sha256": manifest_sha256,
        "source_references": source_references,
        "date_coverage": manifest["date_coverage"],
        "quality_checks": manifest["quality_checks"],
    }
    scientific_result = DeterministicResult(
        fwi=_data_value(fwi, "índice FWI (sin unidad)"),
        historical_reference_fwi=_data_value(
            historical_fwi, "índice FWI (sin unidad)"
        ),
        difference_from_reference=_data_value(
            difference, "puntos FWI (diferencia descriptiva)"
        ),
        components={
            "ffmc": _data_value(weather[4], "índice FWI (sin unidad)"),
            "dmc": _data_value(weather[5], "índice FWI (sin unidad)"),
            "dc": _data_value(weather[6], "índice FWI (sin unidad)"),
            "isi": _data_value(weather[7], "índice FWI (sin unidad)"),
            "bui": _data_value(weather[8], "índice FWI (sin unidad)"),
        },
        meteorology={
            "temperature_2m": _data_value(weather[0], "°C"),
            "relative_humidity_2m": _data_value(weather[1], "%"),
            "wind_speed_10m": _data_value(weather[2], "km/h"),
            "rain_24h": _data_value(weather[3], "mm"),
        },
        reference_month=request.date.month,
        firms_count=_data_value(weather[10], "detecciones FIRMS asociadas"),
        firms_interpretation=(
            "La cantidad indica detecciones FIRMS asociadas; cero no demuestra "
            "ausencia de incendio."
        ),
        evidence_refs=result_refs,
        provenance=provenance,
    )
    return AnalysisResult(
        analysis_id=analysis_id,
        weather_id=request.weather_id,
        date=request.date,
        state="completed",
        result=scientific_result,
        error_code=None,
        error_message=None,
    )


def validate_analysis_request(
    snapshot: ValidatedSnapshot, request: AnalysisRequest
) -> None:
    _require_analysis_context(snapshot, request)
