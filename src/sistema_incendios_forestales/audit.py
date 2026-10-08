from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import UUID

from sistema_incendios_forestales.analysis import AnalysisContextError
from sistema_incendios_forestales.api.contracts import (
    AnalysisResult,
    TraceEvent,
)

AUDIT_SCHEMA_VERSION = 1

AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_runs (
    analysis_id TEXT PRIMARY KEY,
    weather_id TEXT NOT NULL,
    analysis_date TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('queued', 'running', 'completed', 'partial', 'failed')),
    result_json TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analysis_events (
    analysis_id TEXT NOT NULL REFERENCES analysis_runs(analysis_id),
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    event_json TEXT NOT NULL,
    PRIMARY KEY (analysis_id, sequence),
    UNIQUE (analysis_id, idempotency_key)
);
CREATE TRIGGER IF NOT EXISTS analysis_events_no_update
BEFORE UPDATE ON analysis_events BEGIN
    SELECT RAISE(ABORT, 'analysis events are immutable');
END;
CREATE TRIGGER IF NOT EXISTS analysis_events_no_delete
BEFORE DELETE ON analysis_events BEGIN
    SELECT RAISE(ABORT, 'analysis events are immutable');
END;
"""


class AuditStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    @classmethod
    def open(cls, path: Path) -> AuditStore:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=5)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        if user_version not in (0, AUDIT_SCHEMA_VERSION):
            connection.close()
            raise RuntimeError(f"Unsupported audit database schema version: {user_version}")
        try:
            connection.executescript(AUDIT_SCHEMA)
            connection.execute(f"PRAGMA user_version = {AUDIT_SCHEMA_VERSION}")
            connection.commit()
        except sqlite3.DatabaseError:
            connection.close()
            raise
        return cls(connection)

    def close(self) -> None:
        self.connection.close()

    def _append_event(
        self,
        analysis_id: UUID,
        event_type: str,
        sequence: int,
        *,
        result_ref: str | None = None,
        error_code: str | None = None,
        affected_outputs: list[str] | None = None,
    ) -> None:
        occurred_at = datetime.now(timezone.utc)
        event = TraceEvent.model_validate(
            {
                "schema_version": "trace-event.v1",
                "analysis_id": str(analysis_id),
                "sequence": sequence,
                "event_type": event_type,
                "occurred_at": occurred_at.isoformat(),
                "idempotency_key": f"{analysis_id}:{sequence}:{event_type}",
                "result_ref": result_ref,
                "error_code": error_code,
                "affected_outputs": affected_outputs,
            }
        )
        serialized = event.model_dump_json()
        self.connection.execute(
            "INSERT INTO analysis_events "
            "(analysis_id, sequence, event_type, occurred_at, idempotency_key, event_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                str(analysis_id),
                sequence,
                event_type,
                occurred_at.isoformat(),
                event.idempotency_key,
                serialized,
            ),
        )

    def create_queued(self, analysis_id: UUID, request: AnalysisRequest) -> None:
        now = datetime.now(timezone.utc).isoformat()
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                "INSERT INTO analysis_runs "
                "(analysis_id, weather_id, analysis_date, state, created_at, updated_at) "
                "VALUES (?, ?, ?, 'queued', ?, ?)",
                (str(analysis_id), request.weather_id, request.date.isoformat(), now, now),
            )
            self._append_event(analysis_id, "run_queued", 1)
            connection.commit()
        except sqlite3.DatabaseError:
            connection.rollback()
            raise

    def execute(
        self,
        analysis_id: UUID,
        build_result: Callable[[], AnalysisResult],
    ) -> None:
        connection = self.connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            run = connection.execute(
                "SELECT state FROM analysis_runs WHERE analysis_id = ?",
                (str(analysis_id),),
            ).fetchone()
            if run is None or run[0] != "queued":
                raise RuntimeError("Only queued analyses may enter deterministic execution.")
            now = datetime.now(timezone.utc).isoformat()
            self._append_event(analysis_id, "run_started", 2)
            connection.execute(
                "UPDATE analysis_runs SET state = 'running', updated_at = ? "
                "WHERE analysis_id = ?",
                (now, str(analysis_id)),
            )
            try:
                result = build_result()
            except AnalysisContextError as error:
                self._append_event(
                    analysis_id,
                    "run_failed",
                    3,
                    error_code=error.code,
                    affected_outputs=["deterministic_result"],
                )
                connection.execute(
                    "UPDATE analysis_runs SET state = 'failed', error_code = ?, "
                    "error_message = ?, updated_at = ? WHERE analysis_id = ?",
                    (error.code, str(error), datetime.now(timezone.utc).isoformat(), str(analysis_id)),
                )
            except sqlite3.DatabaseError as error:
                self._append_event(
                    analysis_id,
                    "run_failed",
                    3,
                    error_code="SCIENTIFIC_DATA_QUERY_FAILED",
                    affected_outputs=["deterministic_result"],
                )
                connection.execute(
                    "UPDATE analysis_runs SET state = 'failed', "
                    "error_code = 'SCIENTIFIC_DATA_QUERY_FAILED', error_message = ?, "
                    "updated_at = ? WHERE analysis_id = ?",
                    (str(error), datetime.now(timezone.utc).isoformat(), str(analysis_id)),
                )
            else:
                result_ref = f"analysis:{analysis_id}:deterministic-result"
                self._append_event(
                    analysis_id,
                    "analysis_core_result_persisted",
                    3,
                    result_ref=result_ref,
                )
                self._append_event(
                    analysis_id,
                    "run_completed",
                    4,
                    result_ref=result_ref,
                    affected_outputs=["deterministic_result"],
                )
                finished = datetime.now(timezone.utc).isoformat()
                connection.execute(
                    "UPDATE analysis_runs SET state = 'completed', result_json = ?, "
                    "updated_at = ? WHERE analysis_id = ?",
                    (result.model_dump_json(), finished, str(analysis_id)),
                )
            connection.commit()
        except sqlite3.DatabaseError:
            connection.rollback()
            raise

    def get(self, analysis_id: UUID) -> AnalysisResult | None:
        row = self.connection.execute(
            "SELECT analysis_id, weather_id, analysis_date, state, result_json, "
            "error_code, error_message FROM analysis_runs WHERE analysis_id = ?",
            (str(analysis_id),),
        ).fetchone()
        if row is None:
            return None
        if row[4] is not None:
            return AnalysisResult.model_validate_json(row[4])
        return AnalysisResult(
            analysis_id=UUID(row[0]),
            weather_id=row[1],
            date=row[2],
            state=row[3],
            result=None,
            error_code=row[5],
            error_message=row[6],
        )

    def event_types(self, analysis_id: UUID) -> list[str]:
        return [
            row[0]
            for row in self.connection.execute(
                "SELECT event_type FROM analysis_events WHERE analysis_id = ? ORDER BY sequence",
                (str(analysis_id),),
            )
        ]
