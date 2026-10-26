"""Transactional local workspace metadata; connections never cross threads.

Callers pass configuration and run metadata only. DataFrames and raw table data
are deliberately outside this storage contract.
"""

import json
import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dataflow.core.errors import DataFlowError

_MAX_BYTES = 1_048_576
_MAX_ITEMS = 20_000
_SCHEMA_VERSION = 1
_TABLE_KEYS = {"data", "dataframe", "table_data", "cells", "records", "raw_data"}
_STATUSES = {
    "pending",
    "queued",
    "running",
    "cancel_requested",
    "interrupted",
    "completed",
    "failed",
    "cancelled",
}


def _now():
    return datetime.now(UTC).isoformat()


def workspace_directory(directory: Path | None = None) -> Path:
    """Resolve the shared metadata/lease directory without creating any files."""
    if directory is not None:
        return Path(directory)
    override = os.environ.get("DATAFLOW_WORKSPACE_DIR")
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA")
    return (
        Path(local) / "DataFlowStudio"
        if local
        else Path.home() / ".local" / "share" / "DataFlowStudio"
    )


def _encode(value, *, require_dict=True):
    if require_dict and not isinstance(value, dict):
        raise DataFlowError("Workspace metadata must be a JSON object.")
    remaining = _MAX_ITEMS

    def check(item, depth=0):
        nonlocal remaining
        remaining -= 1
        if depth > 24 or remaining < 0:
            raise DataFlowError("Workspace metadata exceeds safety limits.")
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str) or (depth == 0 and key.lower() in _TABLE_KEYS):
                    raise DataFlowError("Only configuration and run metadata may be stored.")
                check(child, depth + 1)
        elif isinstance(item, list):
            if any(isinstance(child, list) for child in item):
                raise DataFlowError("Raw table matrices cannot be stored as workspace metadata.")
            for child in item:
                check(child, depth + 1)
        elif item is None or isinstance(item, (str, bool, int)):
            return
        elif isinstance(item, float) and math.isfinite(item):
            return
        else:
            raise DataFlowError("Workspace metadata must contain valid JSON values.")

    check(value)
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > _MAX_BYTES:
            raise DataFlowError("Workspace metadata exceeds safety limits.")
        return encoded
    except (TypeError, OverflowError, UnicodeError, RecursionError) as exc:
        raise DataFlowError("Workspace metadata is invalid.") from exc


class WorkspaceStore:
    """Store settings, paths, history and resumable job checkpoints locally.

    An unsupported schema is left untouched and exposes empty fallback reads.
    Writes raise a sanitized DataFlowError so the UI can show a local warning.
    """

    def __init__(self, directory: Path | None = None):
        self.path = workspace_directory(directory) / "workspace.sqlite3"
        self.warning = ""
        self._available = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()
        except sqlite3.DatabaseError as exc:
            code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
            if code in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
                self._recover()
            else:
                self.warning = "Local workspace is unavailable; saved metadata was preserved."
        except OSError:
            self.warning = "Local workspace is unavailable; saved metadata was preserved."
        if self._available:
            try:
                self.mark_interrupted()
            except DataFlowError:
                self._available = False
                self.warning = "Local workspace is unavailable; saved metadata was preserved."

    @contextmanager
    def _connection(self):
        conn = None
        try:
            conn = sqlite3.connect(self.path, timeout=10)
            conn.row_factory = sqlite3.Row
            with conn:
                yield conn
        except (sqlite3.Error, OSError) as exc:
            raise DataFlowError("Local workspace operation failed.") from exc
        finally:
            if conn is not None:
                conn.close()

    def _initialize(self):
        # Keep raw SQLite errors here so only actual corruption triggers backup.
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, _SCHEMA_VERSION):
                self.warning = (
                    "Local workspace uses an unsupported version; saved metadata was preserved."
                )
                return
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                error = sqlite3.DatabaseError("Invalid workspace database")
                error.sqlite_errorcode = sqlite3.SQLITE_CORRUPT
                raise error
            expected = {
                "workspace": {"id", "payload"},
                "history": {"id", "time", "action", "detail"},
                "jobs": {
                    "id",
                    "kind",
                    "status",
                    "payload",
                    "checkpoint",
                    "error",
                    "created_at",
                    "updated_at",
                },
            }
            tables = {
                row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            for table, columns in expected.items():
                if table not in tables:
                    if version == 0:
                        continue
                    self.warning = (
                        "Local workspace schema is invalid; saved metadata was preserved."
                    )
                    return
                actual = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                if actual != columns:
                    self.warning = (
                        "Local workspace schema is invalid; saved metadata was preserved."
                    )
                    return
            with conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS workspace (id INTEGER PRIMARY KEY CHECK (id=1), payload TEXT NOT NULL)"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL)"
                )
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL, checkpoint TEXT, error TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
                )
                conn.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
            self._available = True
        finally:
            conn.close()

    def _recover(self):
        try:
            backup = self.path.with_name(f"workspace.corrupt-{uuid4().hex}.sqlite3")
            # Rename preserves bytes and avoids overwriting prior recovery files.
            self.path.rename(backup)
            for suffix in ("-wal", "-shm", "-journal"):
                sidecar = self.path.with_name(self.path.name + suffix)
                if sidecar.exists():
                    sidecar.rename(backup.with_name(backup.name + suffix))
            self._initialize()
            self.warning = (
                "Local workspace was damaged. A backup was preserved and a new workspace created."
            )
        except (OSError, sqlite3.Error):
            self._available = False
            self.warning = "Local workspace recovery failed; existing metadata was preserved."

    def _writable(self):
        if not self._available:
            raise DataFlowError("Local workspace is unavailable.")

    def _decode(self, text):
        try:
            if not isinstance(text, str) or len(text.encode("utf-8")) > _MAX_BYTES:
                raise ValueError
            value = json.loads(text)
            _encode(value)
            return value
        except (ValueError, TypeError, UnicodeError, RecursionError):
            self.warning = "Some saved workspace metadata was invalid and could not be restored."
            return None

    def load_workspace(self) -> dict:
        if not self._available:
            return {}
        with self._connection() as conn:
            row = conn.execute("SELECT payload FROM workspace WHERE id=1").fetchone()
        return (self._decode(row[0]) or {}) if row else {}

    def save_workspace(self, payload: dict):
        self._writable()
        encoded = _encode(payload)
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO workspace(id,payload) VALUES (1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (encoded,),
            )

    def append_history(self, action, detail, *, timestamp=None):
        self._writable()
        timestamp = _now() if timestamp is None else timestamp
        if not all(isinstance(x, str) for x in (action, detail, timestamp)):
            raise DataFlowError("History fields must be text.")
        _encode({"time": timestamp, "action": action, "detail": detail})
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO history(time,action,detail) VALUES (?,?,?)",
                (timestamp, action, detail),
            )

    @staticmethod
    def _limit(limit):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 0 <= limit <= 1000:
            raise DataFlowError("History or job limit must be between 0 and 1000.")
        return limit

    def history(self, limit=200) -> list[dict]:
        limit = self._limit(limit)
        if not self._available:
            return []
        with self._connection() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT time,action,detail FROM history ORDER BY id DESC LIMIT ?", (limit,)
                )
            ]

    def create_job(self, kind, payload) -> str:
        self._writable()
        if not isinstance(kind, str) or not kind or len(kind) > 100:
            raise DataFlowError("Job kind is invalid.")
        encoded = _encode(payload)
        job_id, stamp = uuid4().hex, _now()
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)",
                (job_id, kind, "pending", encoded, None, None, stamp, stamp),
            )
        return job_id

    def update_job(self, job_id, status, *, checkpoint=None, error=None):
        self._writable()
        if status not in _STATUSES:
            raise DataFlowError("Job status is invalid.")
        encoded = _encode(checkpoint) if checkpoint is not None else None
        if error is not None and (not isinstance(error, str) or len(error) > 4096):
            raise DataFlowError("Job error metadata is invalid.")
        with self._connection() as conn:
            cursor = conn.execute(
                "UPDATE jobs SET status=?,checkpoint=COALESCE(?,checkpoint),error=?,updated_at=? WHERE id=?",
                (status, encoded, error, _now(), job_id),
            )
            if cursor.rowcount != 1:
                raise DataFlowError("Saved job was not found.")

    def _job(self, row):
        result = dict(row)
        result["payload"] = self._decode(result["payload"])
        if result["payload"] is None:
            return None
        if result["checkpoint"] is not None:
            result["checkpoint"] = self._decode(result["checkpoint"])
            if result["checkpoint"] is None:
                return None
        if result["status"] not in _STATUSES:
            self.warning = "Some saved job metadata was invalid and could not be restored."
            return None
        return result

    def get_job(self, job_id) -> dict | None:
        if not self._available:
            return None
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._job(row) if row else None

    def list_jobs(self, limit=30) -> list[dict]:
        limit = self._limit(limit)
        if not self._available:
            return []
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [job for row in rows if (job := self._job(row)) is not None]

    def mark_interrupted(self) -> int:
        if not self._available:
            return 0
        with self._connection() as conn:
            return conn.execute(
                "UPDATE jobs SET status='interrupted',updated_at=? WHERE status IN ('running','cancel_requested')",
                (_now(),),
            ).rowcount
