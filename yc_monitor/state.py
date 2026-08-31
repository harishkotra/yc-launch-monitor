"""SQLite-backed state management and duplicate detection.

Two tables:
  * seen_events  — dedup: one row per dedup_key that has already been alerted.
  * snapshots    — latest raw payload hash per source, so we only diff on change.

Thread-safety is not a concern (single poller), but we still use a single
connection with check_same_thread=False for convenience.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Optional


class State:
    def __init__(self, db_path: str = "state.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_events (
                dedup_key   TEXT PRIMARY KEY,
                source      TEXT,
                company     TEXT,
                alerted_at  TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                source      TEXT PRIMARY KEY,
                payload_hash TEXT,
                updated_at  TEXT
            )
            """
        )
        self.conn.commit()

    # -- dedup -----------------------------------------------------------
    def is_seen(self, dedup_key: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM seen_events WHERE dedup_key = ?", (dedup_key,))
        return cur.fetchone() is not None

    def mark_seen(self, dedup_key: str, source: str, company: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT OR IGNORE INTO seen_events (dedup_key, source, company, alerted_at) VALUES (?,?,?,?)",
            (dedup_key, source, company, now),
        )
        self.conn.commit()

    # -- snapshot diffing (for slug lists) ------------------------------
    def snapshot_unchanged(self, source: str, payload) -> bool:
        """Return True if the payload is byte-identical to the last snapshot."""
        h = hashlib.sha256(str(payload).encode("utf-8")).hexdigest()
        row = self.conn.execute("SELECT payload_hash FROM snapshots WHERE source = ?", (source,)).fetchone()
        if row and row["payload_hash"] == h:
            return True
        return False

    def update_snapshot(self, source: str, payload) -> None:
        h = hashlib.sha256(str(payload).encode("utf-8")).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "INSERT OR REPLACE INTO snapshots (source, payload_hash, updated_at) VALUES (?,?,?)",
            (source, h, now),
        )
        self.conn.commit()

    # -- introspection ---------------------------------------------------
    def stats(self) -> dict:
        n_seen = self.conn.execute("SELECT COUNT(*) AS c FROM seen_events").fetchone()["c"]
        n_snap = self.conn.execute("SELECT COUNT(*) AS c FROM snapshots").fetchone()["c"]
        return {"seen_events": n_seen, "snapshots": n_snap}

    def close(self) -> None:
        self.conn.close()
