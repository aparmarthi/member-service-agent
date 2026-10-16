"""Postgres persistence. Runs only when DATABASE_URL is set (CI provides a Postgres service)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.serving import app as app_module
from src.serving import store

pytestmark = pytest.mark.skipif(not store.enabled(), reason="DATABASE_URL not set")
client = TestClient(app_module.app)


def test_session_survives_api_restart():
    sid = client.post("/sessions", json={}).json()["session_id"]
    assert client.post(f"/sessions/{sid}/messages", json={"text": "where is my order"}).json()[
        "has_more"]
    app_module._sessions.clear()  # what a restart loses; Postgres keeps the rest
    second = client.post(f"/sessions/{sid}/messages", json={"text": "see more"}).json()
    assert "next 2" in second["reply"]
    assert [t["user"] for t in client.get(f"/sessions/{sid}").json()["turns"]] == [
        "where is my order", "see more"]


def test_turn_audit_is_queryable_in_sql():
    sid = client.post("/sessions", json={}).json()["session_id"]
    client.post(f"/sessions/{sid}/messages", json={"text": "I want to end my life"})
    with store.pool().connection() as conn:
        row = conn.execute("SELECT intent, escalated, crisis FROM turns WHERE session_id = %s",
                           (sid,)).fetchone()
    assert row == {"intent": "escalation", "escalated": True, "crisis": True}


def test_unknown_session_is_still_404():
    assert client.get("/sessions/does-not-exist").status_code == 404
