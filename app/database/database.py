import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    meeting_date TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',   -- queued|processing|done|failed
    stage TEXT DEFAULT '',
    error TEXT DEFAULT '',
    transcript TEXT DEFAULT '',
    minutes_json TEXT DEFAULT '',
    audio_path TEXT DEFAULT '',
    created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = str(path)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def create(self, meeting_id: str, filename: str, meeting_date: str, audio_path: str) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO meetings (id, filename, meeting_date, audio_path, created_at) VALUES (?,?,?,?,?)",
                (meeting_id, filename, meeting_date, audio_path,
                 datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )

    def update(self, meeting_id: str, **fields) -> None:
        if "minutes" in fields:
            m = fields.pop("minutes")
            fields["minutes_json"] = m.model_dump_json() if m is not None else ""
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._lock, self._conn() as c:
            c.execute(f"UPDATE meetings SET {cols} WHERE id=?", (*fields.values(), meeting_id))

    def get(self, meeting_id: str) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["minutes"] = json.loads(d["minutes_json"]) if d["minutes_json"] else None
        return d

    def list(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, filename, meeting_date, status, stage, created_at, minutes_json "
                "FROM meetings ORDER BY created_at DESC"
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            m = json.loads(d.pop("minutes_json")) if d["minutes_json"] else {}
            d["title"] = m.get("meeting_title") or d["filename"]
            out.append(d)
        return out

    def delete(self, meeting_id: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM meetings WHERE id=?", (meeting_id,))

    def reset_stuck(self) -> None:
        """Jobs left 'processing' by a crashed/stopped server can never finish."""
        with self._lock, self._conn() as c:
            c.execute(
                "UPDATE meetings SET status='failed', error='Interrupted by a server restart. Click Retry.' "
                "WHERE status IN ('queued','processing')"
            )
