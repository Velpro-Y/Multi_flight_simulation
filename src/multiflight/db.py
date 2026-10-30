"""Small SQLite job store for local demo persistence."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .settings import DB_FILE


class JobStore:
    def __init__(self, db_file: Path = DB_FILE) -> None:
        self.db_file = db_file
        self.db_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_file, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL,
                    message TEXT NOT NULL,
                    payload_json TEXT,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def create(
        self, job_id: str, kind: str, payload: dict[str, Any], message: str
    ) -> dict[str, Any]:
        now = _utc_now()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs
                (id, kind, status, progress, message, payload_json, created_at, updated_at)
                VALUES (?, ?, 'queued', 0.0, ?, ?, ?, ?)
                """,
                (job_id, kind, message, _dump(payload), now, now),
            )
        return self.get(job_id)

    def update(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        result: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> dict[str, Any]:
        assignments: list[str] = ["updated_at = ?"]
        values: list[Any] = [_utc_now()]
        for column, value in (
            ("status", status),
            ("progress", progress),
            ("message", message),
            ("result_json", _dump(result) if result is not None else None),
            ("error", error),
        ):
            if value is not None:
                assignments.append(f"{column} = ?")
                values.append(value)
        values.append(job_id)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE jobs SET {', '.join(assignments)} WHERE id = ?", values
            )
            if cursor.rowcount == 0:
                raise KeyError(f"Unknown job: {job_id}")
        return self.get(job_id)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown job: {job_id}")
        return _row_to_dict(row)

    def latest(self, kind: Optional[str] = None, limit: int = 20) -> list[dict[str, Any]]:
        query = "SELECT * FROM jobs"
        params: list[Any] = []
        if kind:
            query += " WHERE kind = ?"
            params.append(kind)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_row_to_dict(row) for row in rows]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "kind": row["kind"],
        "status": row["status"],
        "progress": row["progress"],
        "message": row["message"],
        "payload": _load(row["payload_json"]),
        "result": _load(row["result_json"]),
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load(value: Optional[str]) -> Any:
    return json.loads(value) if value else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

