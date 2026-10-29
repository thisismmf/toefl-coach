"""Tiny SQLite layer. One row per run; results stored as JSON."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,          -- grade | model | lesson
    task        TEXT NOT NULL,          -- email | discussion | speaking
    title       TEXT,
    parent_id   TEXT,                   -- grade run a model/lesson run derives from
    provider    TEXT, model TEXT,
    status      TEXT NOT NULL,          -- running | done | error
    stage       TEXT,
    progress    REAL DEFAULT 0,
    payload     TEXT,
    result      TEXT,
    error       TEXT,
    created_at  REAL, updated_at REAL
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init() -> None:
    with _conn() as c:
        c.executescript(SCHEMA)
        # A restart orphans anything mid-flight; do not leave it spinning.
        c.execute("UPDATE runs SET status='error', stage='Interrupted', "
                  "error='The server restarted while this run was in progress.' "
                  "WHERE status='running'")


def create_run(kind: str, task: str, payload: dict, provider: str, model: str,
               title: str = "", parent_id: str | None = None) -> str:
    rid = uuid.uuid4().hex[:12]
    now = time.time()
    with _conn() as c:
        c.execute(
            "INSERT INTO runs (id,kind,task,title,parent_id,provider,model,status,"
            "stage,progress,payload,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,'running','queued',0,?,?,?)",
            (rid, kind, task, title, parent_id, provider, model,
             json.dumps(payload, ensure_ascii=False), now, now))
    return rid


def update_run(rid: str, **fields: Any) -> None:
    if not fields:
        return
    for k in ("result", "payload"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = json.dumps(fields[k], ensure_ascii=False)
    fields["updated_at"] = time.time()
    sets = ", ".join(f"{k}=?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE runs SET {sets} WHERE id=?", (*fields.values(), rid))


def get_run(rid: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
    if not row:
        return None
    d = dict(row)
    for k in ("payload", "result"):
        if d.get(k):
            try:
                d[k] = json.loads(d[k])
            except json.JSONDecodeError:
                pass
    return d


def list_runs(limit: int = 60, kind: str | None = None) -> list[dict]:
    q = "SELECT id,kind,task,title,parent_id,provider,model,status,stage,progress,created_at FROM runs"
    args: tuple = ()
    if kind:
        q += " WHERE kind=?"
        args = (kind,)
    q += " ORDER BY created_at DESC LIMIT ?"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, (*args, limit)).fetchall()]


def delete_run(rid: str) -> None:
    with _conn() as c:
        c.execute("DELETE FROM runs WHERE id=? OR parent_id=?", (rid, rid))
