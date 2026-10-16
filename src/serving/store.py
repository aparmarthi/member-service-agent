"""PostgreSQL persistence: graph checkpoints, sessions, and the turn audit log.

Enabled when ``DATABASE_URL`` is set. Without it the API keeps everything in
process memory, which is fine for local dev and the test suite.

Three things live in Postgres:

* LangGraph checkpoints (``PostgresSaver``): workflow state per ``thread_id``,
  such as pending offers, pagination and auth progress. A restarted API
  resumes a conversation mid-flow.
* ``sessions``: which synthetic member and channel a thread belongs to.
* ``turns``: one row per member turn. The decision columns (intent,
  escalated, crisis, offer, latency) make escalation and containment
  queryable in plain SQL. ``result`` holds the full response for transcript
  replay.

Checkpoints and ``user_text`` hold conversation content. With real members
that is PHI: encrypt at rest (RDS + KMS) and set a retention window.
"""

from __future__ import annotations

import os
from functools import lru_cache

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.base import SerializerProtocol
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from src.models.schemas import AgentTurnResult

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        scenario   TEXT NOT NULL,
        channel    TEXT NOT NULL,
        verified   BOOLEAN NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS turns (
        session_id TEXT NOT NULL REFERENCES sessions ON DELETE CASCADE,
        turn_index INT NOT NULL,
        user_text  TEXT NOT NULL,
        result     JSONB NOT NULL,
        intent     TEXT NOT NULL,
        escalated  BOOLEAN NOT NULL,
        crisis     BOOLEAN NOT NULL,
        offer      TEXT,
        latency_ms REAL NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (session_id, turn_index))""",
)


def enabled() -> bool:
    """Whether a database is configured."""
    return bool(os.getenv("DATABASE_URL"))


@lru_cache(maxsize=1)
def pool() -> ConnectionPool:
    """Open the process-wide connection pool and create the app tables."""
    p = ConnectionPool(
        os.environ["DATABASE_URL"],
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )
    with p.connection() as conn:
        for ddl in _SCHEMA:
            conn.execute(ddl)
    return p


def checkpointer(serde: SerializerProtocol) -> PostgresSaver:
    """Return a Postgres-backed LangGraph checkpointer (tables created on first use)."""
    saver = PostgresSaver(pool(), serde=serde)
    saver.setup()
    return saver


def save_session(session_id: str, scenario: str, channel: str, verified: bool) -> None:
    """Record a new conversation."""
    with pool().connection() as conn:
        conn.execute(
            "INSERT INTO sessions (session_id, scenario, channel, verified) VALUES (%s, %s, %s, %s)",
            (session_id, scenario, channel, verified))


def record_turn(session_id: str, index: int, user_text: str, result: AgentTurnResult,
                latency_ms: float) -> None:
    """Append one turn to the audit log."""
    with pool().connection() as conn:
        conn.execute(
            """INSERT INTO turns (session_id, turn_index, user_text, result, intent,
                                  escalated, crisis, offer, latency_ms)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (session_id, index, user_text, Jsonb(result.model_dump(mode="json")),
             result.intent.value, result.escalated, result.crisis, result.offer, latency_ms))


def load_session(session_id: str) -> tuple[dict, list[tuple[str, AgentTurnResult]]] | None:
    """Return a session's row and transcript, or ``None`` if it doesn't exist."""
    with pool().connection() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE session_id = %s",
                           (session_id,)).fetchone()
        if row is None:
            return None
        turns = conn.execute(
            "SELECT user_text, result FROM turns WHERE session_id = %s ORDER BY turn_index",
            (session_id,)).fetchall()
    return row, [(t["user_text"], AgentTurnResult.model_validate(t["result"])) for t in turns]
