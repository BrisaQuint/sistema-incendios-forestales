from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import UUID

from pydantic import ValidationError

from sistema_incendios_forestales.analysis import AnalysisContextError
from sistema_incendios_forestales.api.contracts import AnalysisRequest, AnalysisResult, TraceEvent

AUDIT_SCHEMA_VERSION = 2

_MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        """
        CREATE TABLE analysis_runs (
            analysis_id TEXT PRIMARY KEY,
            weather_id TEXT NOT NULL,
            analysis_date TEXT NOT NULL,
            state TEXT NOT NULL CHECK (
                state IN ('queued', 'running', 'completed', 'partial', 'failed')
            ),
            result_json TEXT,
            error_code TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """,
        """
        CREATE TABLE analysis_events (
            analysis_id TEXT NOT NULL REFERENCES analysis_runs(analysis_id),
            sequence INTEGER NOT NULL CHECK (sequence >= 1),
            event_type TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            idempotency_key TEXT NOT NULL,
            event_json TEXT NOT NULL,
            PRIMARY KEY (analysis_id, sequence),
            UNIQUE (analysis_id, idempotency_key)
        );
        """,
        """
        CREATE TRIGGER analysis_events_no_update
        BEFORE UPDATE ON analysis_events BEGIN
            SELECT RAISE(ABORT, 'analysis events are immutable');
        END;
        """,
        """
        CREATE TRIGGER analysis_events_no_delete
        BEFORE DELETE ON analysis_events BEGIN
            SELECT RAISE(ABORT, 'analysis events are immutable');
        END
        """,
    ),
    2: (
        "CREATE INDEX analysis_runs_state_idx ON analysis_runs (state)",
        """
        CREATE TRIGGER analysis_events_sequence
        BEFORE INSERT ON analysis_events
        WHEN NEW.sequence != (
            SELECT COALESCE(MAX(sequence), 0) + 1
            FROM analysis_events
            WHERE analysis_id = NEW.analysis_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'analysis event sequence must be contiguous');
        END
        """,
        """
        CREATE TRIGGER analysis_runs_state_transition
        BEFORE UPDATE OF state ON analysis_runs
        WHEN NOT (
            (OLD.state = 'queued' AND NEW.state IN ('queued', 'running', 'failed'))
            OR (OLD.state = 'running' AND NEW.state IN (
                'running', 'completed', 'partial', 'failed'
            ))
        )
        BEGIN
            SELECT RAISE(ABORT, 'invalid or terminal analysis state transition');
        END
        """,
    ),
}


class AuditStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    @classmethod
    def open(cls, path: Path) -> AuditStore:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=5)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            store = cls(connection)
            store._migrate()
            store.recover_interrupted_runs()
        except BaseException:
            connection.close()
            raise
        return store

    def _migrate(self) -> None:
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version > AUDIT_SCHEMA_VERSION:
            raise RuntimeError(
                f"Audit database schema version {version} is newer than supported "
                f"version {AUDIT_SCHEMA_VERSION}."
            )
        if version < 0:
            raise RuntimeError(f"Invalid audit database schema version: {version}")

        for migration_version in range(version + 1, AUDIT_SCHEMA_VERSION + 1):
            self.connection.execute("BEGIN IMMEDIATE")
            try:
                for statement in _MIGRATIONS[migration_version]:
                    self.connection.execute(statement)
                self.connection.execute(f"PRAGMA user_version = {migration_version}")
                self.connection.commit()
            except BaseException:
                self.connection.rollback()
                raise
            version = migration_version

    def close(self) -> None:
        self.connection.close()

    def _next_sequence(self, analysis_id: UUID) -> int:
        return self.connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM analysis_events "
            "WHERE analysis_id = ?",
            (str(analysis_id),),
        ).fetchone()[0]

    def _append_event(
        self,
        analysis_id: UUID,
        event_type: str,
        *,
        result_ref: str | None = None,
        error_code: str | None = None,
        affected_outputs: list[str] | None = None,
        tool_name: str | None = None,
        task: str | None = None,
    ) -> TraceEvent:
        occurred_at = datetime.now(timezone.utc)
        sequence = self._next_sequence(analysis_id)
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
                "tool_name": tool_name,
                "task": task,
            }
        )
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
                event.model_dump_json(),
            ),
        )
        return event

    def _transaction(self, operation: Callable[[], None]) -> None:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            operation()
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def record_activity_event(self, event: TraceEvent) -> TraceEvent:
        validated_event = TraceEvent.model_validate(event.model_dump(mode="python"))
        if validated_event.event_type in {
            "run_queued",
            "run_started",
            "analysis_core_result_persisted",
            "run_interrupted",
            "run_completed",
            "run_partial",
            "run_failed",
        }:
            raise ValueError("Run transition events must use their atomic transition method.")

        recorded: list[TraceEvent] = []

        def persist() -> None:
            analysis_id = validated_event.analysis_id
            existing = self.connection.execute(
                "SELECT event_json FROM analysis_events "
                "WHERE analysis_id = ? AND idempotency_key = ?",
                (str(analysis_id), validated_event.idempotency_key),
            ).fetchone()
            if existing is not None:
                previous = TraceEvent.model_validate_json(existing[0])
                if previous != validated_event:
                    raise ValueError(
                        "An idempotency key cannot be reused with different event content."
                    )
                recorded.append(previous)
                return

            run = self.connection.execute(
                "SELECT state FROM analysis_runs WHERE analysis_id = ?",
                (str(analysis_id),),
            ).fetchone()
            if run is None or run[0] != "running":
                raise RuntimeError("Activity events can only be recorded for a running analysis.")
            expected_sequence = self._next_sequence(analysis_id)
            if validated_event.sequence != expected_sequence:
                raise ValueError(
                    f"Expected activity event sequence {expected_sequence}, "
                    f"received {validated_event.sequence}."
                )
            self.connection.execute(
                "INSERT INTO analysis_events "
                "(analysis_id, sequence, event_type, occurred_at, idempotency_key, event_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    str(analysis_id),
                    validated_event.sequence,
                    validated_event.event_type,
                    validated_event.occurred_at.isoformat(),
                    validated_event.idempotency_key,
                    validated_event.model_dump_json(),
                ),
            )
            recorded.append(validated_event)

        self._transaction(persist)
        return recorded[0]

    def create_queued(self, analysis_id: UUID, request: AnalysisRequest) -> None:
        now = datetime.now(timezone.utc).isoformat()

        def persist() -> None:
            self.connection.execute(
                "INSERT INTO analysis_runs "
                "(analysis_id, weather_id, analysis_date, state, created_at, updated_at) "
                "VALUES (?, ?, ?, 'queued', ?, ?)",
                (str(analysis_id), request.weather_id, request.date.isoformat(), now, now),
            )
            self._append_event(analysis_id, "run_queued")

        self._transaction(persist)

    def _mark_started(self, analysis_id: UUID) -> None:
        def persist() -> None:
            run = self.connection.execute(
                "SELECT state FROM analysis_runs WHERE analysis_id = ?",
                (str(analysis_id),),
            ).fetchone()
            if run is None or run[0] != "queued":
                raise RuntimeError("Only queued analyses may enter deterministic execution.")
            self._append_event(analysis_id, "run_started")
            self.connection.execute(
                "UPDATE analysis_runs SET state = 'running', updated_at = ? "
                "WHERE analysis_id = ?",
                (datetime.now(timezone.utc).isoformat(), str(analysis_id)),
            )

        self._transaction(persist)

    def _persist_core_result(self, analysis_id: UUID, result: AnalysisResult) -> None:
        result_ref = f"analysis:{analysis_id}:deterministic-result"

        def persist() -> None:
            run = self.connection.execute(
                "SELECT state FROM analysis_runs WHERE analysis_id = ?",
                (str(analysis_id),),
            ).fetchone()
            if run is None or run[0] != "running":
                raise RuntimeError("Only running analyses may persist a core result.")
            self._append_event(
                analysis_id,
                "analysis_core_result_persisted",
                result_ref=result_ref,
            )
            self.connection.execute(
                "UPDATE analysis_runs SET result_json = ?, updated_at = ? "
                "WHERE analysis_id = ?",
                (
                    result.model_dump_json(),
                    datetime.now(timezone.utc).isoformat(),
                    str(analysis_id),
                ),
            )

        self._transaction(persist)

    def _finish(
        self,
        analysis_id: UUID,
        state: str,
        *,
        result: AnalysisResult | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        interrupted: bool = False,
    ) -> None:
        result_ref = f"analysis:{analysis_id}:deterministic-result"
        event_type = {
            "completed": "run_completed",
            "partial": "run_partial",
            "failed": "run_failed",
        }[state]

        def persist() -> None:
            row = self.connection.execute(
                "SELECT state, result_json FROM analysis_runs WHERE analysis_id = ?",
                (str(analysis_id),),
            ).fetchone()
            valid_states = {"running"}
            if interrupted:
                valid_states.add("queued")
            if row is None or row[0] not in valid_states:
                raise RuntimeError(
                    "Only active analyses may enter a terminal state."
                )
            if interrupted:
                self._append_event(
                    analysis_id,
                    "run_interrupted",
                    affected_outputs=["incomplete_run"],
                    error_code="PROCESS_INTERRUPTED",
                )
            if result is not None:
                persisted_result = result.model_copy(update={"state": state})
                result_json = persisted_result.model_dump_json()
            elif state == "failed":
                result_json = None
            else:
                result_json = row[1]
            self._append_event(
                analysis_id,
                event_type,
                result_ref=result_ref if state in {"completed", "partial"} else None,
                error_code=error_code,
                affected_outputs=["deterministic_result"]
                if state in {"completed", "partial"}
                else ["deterministic_result", "analysis"],
            )
            self.connection.execute(
                "UPDATE analysis_runs SET state = ?, result_json = ?, error_code = ?, "
                "error_message = ?, updated_at = ? WHERE analysis_id = ?",
                (
                    state,
                    result_json,
                    error_code,
                    error_message,
                    datetime.now(timezone.utc).isoformat(),
                    str(analysis_id),
                ),
            )

        self._transaction(persist)

    def _fail_tool(
        self, analysis_id: UUID, error_code: str, error_message: str
    ) -> None:
        def persist() -> None:
            self._append_event(
                analysis_id,
                "tool_failed",
                error_code=error_code,
                affected_outputs=["deterministic_result"],
                tool_name="scientific_snapshot",
                task="load_deterministic_analysis",
            )

        self._transaction(persist)
        self._finish(
            analysis_id,
            "failed",
            error_code=error_code,
            error_message=error_message,
        )

    def execute(
        self,
        analysis_id: UUID,
        build_result: Callable[[], AnalysisResult],
    ) -> None:
        self._mark_started(analysis_id)
        try:
            result = build_result()
        except AnalysisContextError as error:
            self._fail_tool(analysis_id, error.code, str(error))
            return
        except sqlite3.DatabaseError as error:
            self._fail_tool(
                analysis_id, "SCIENTIFIC_DATA_QUERY_FAILED", str(error)
            )
            return
        except ValidationError as error:
            self._fail_tool(
                analysis_id, "DETERMINISTIC_RESULT_INVALID", str(error)
            )
            return

        if result.result is None or result.result.fwi.value is None:
            self._fail_tool(
                analysis_id,
                "FWI_CORE_RESULT_UNAVAILABLE",
                "The deterministic result did not contain a usable FWI value.",
            )
            return
        self._persist_core_result(analysis_id, result)
        self._finish(analysis_id, "completed", result=result)

    def recover_interrupted_runs(self) -> None:
        rows = self.connection.execute(
            "SELECT analysis_id, state, result_json FROM analysis_runs "
            "WHERE state IN ('queued', 'running') ORDER BY created_at, analysis_id"
        ).fetchall()
        for raw_analysis_id, state, result_json in rows:
            analysis_id = UUID(raw_analysis_id)
            terminal = self.connection.execute(
                "SELECT event_type FROM analysis_events "
                "WHERE analysis_id = ? AND event_type IN "
                "('run_completed', 'run_partial', 'run_failed')",
                (raw_analysis_id,),
            ).fetchone()
            if terminal is not None:
                raise RuntimeError(
                    f"Audit projection for {analysis_id} is non-terminal despite "
                    f"terminal event {terminal[0]}."
                )
            result = (
                None
                if result_json is None
                else AnalysisResult.model_validate_json(result_json)
            )
            core_persisted = self.connection.execute(
                "SELECT 1 FROM analysis_events WHERE analysis_id = ? "
                "AND event_type = 'analysis_core_result_persisted'",
                (raw_analysis_id,),
            ).fetchone()
            has_usable_fwi = (
                state == "running"
                and result is not None
                and result.result is not None
                and result.result.fwi.value is not None
                and core_persisted is not None
            )
            if has_usable_fwi:
                self._finish(
                    analysis_id,
                    "partial",
                    result=result,
                    error_code="PROCESS_INTERRUPTED",
                    error_message="The process stopped after persisting the deterministic result.",
                    interrupted=True,
                )
            else:
                self._finish(
                    analysis_id,
                    "failed",
                    error_code="PROCESS_INTERRUPTED",
                    error_message=(
                        "The process stopped before a usable deterministic result was committed."
                    ),
                    interrupted=True,
                )

    def get(self, analysis_id: UUID) -> AnalysisResult | None:
        row = self.connection.execute(
            "SELECT analysis_id, weather_id, analysis_date, state, result_json, "
            "error_code, error_message FROM analysis_runs WHERE analysis_id = ?",
            (str(analysis_id),),
        ).fetchone()
        if row is None:
            return None
        if row[4] is not None:
            result = AnalysisResult.model_validate_json(row[4])
            return result.model_copy(
                update={
                    "state": row[3],
                    "error_code": row[5],
                    "error_message": row[6],
                }
            )
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

    def events(self, analysis_id: UUID) -> list[TraceEvent]:
        return [
            TraceEvent.model_validate_json(row[0])
            for row in self.connection.execute(
                "SELECT event_json FROM analysis_events "
                "WHERE analysis_id = ? ORDER BY sequence",
                (str(analysis_id),),
            )
        ]
