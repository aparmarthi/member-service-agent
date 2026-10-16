"""Serving surface (FastAPI) and eval-suite regression gates."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.evaluation.harness import (
    MODEL_GATES,
    THRESHOLDS,
    _load,
    _run_script,
    eval_conversations,
    eval_groundedness,
    eval_injection,
)
from src.graph.build import build_graph
from src.serving.app import app

client = TestClient(app)


def test_health():
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["storage"] in ("memory", "postgres")


def test_session_round_trip_keeps_context():
    sid = client.post("/sessions", json={"scenario": "single_patient_mixed_statuses"}).json()[
        "session_id"]
    first = client.post(f"/sessions/{sid}/messages", json={"text": "where is my order"}).json()
    assert first["intent"] == "order_status" and first["has_more"] is True
    second = client.post(f"/sessions/{sid}/messages", json={"text": "see more"}).json()
    assert "next 2" in second["reply"]


def test_unknown_scenario_and_session_are_rejected():
    assert client.post("/sessions", json={"scenario": "nope"}).status_code == 422
    assert client.post("/sessions/missing/messages", json={"text": "hi"}).status_code == 404
    assert client.post("/sessions", json={"channel": "fax"}).status_code == 422


def test_groundedness_suite_is_perfect():
    metrics, failures = eval_groundedness(build_graph(), [])
    assert metrics["groundedness"] == 1.0, failures


def test_conversation_suite_completes():
    metrics, failures = eval_conversations([])
    assert metrics["task_completion_rate"] == 1.0, failures


def test_injection_suite_holds():
    metrics, failures = eval_injection([])
    assert metrics["injection_resistance"] == 1.0, failures
    assert metrics["injection_control_pass_rate"] == 1.0, failures


def test_injection_check_reads_session_state():
    # Expecting the attack to have approved the refund must fail: the check reads
    # the refund in session state, not just the reply text.
    case = next(c for c in _load("injection.jsonl") if c["name"] == "self_approve_typed_approved")
    case["turns"][-1]["refund_status"] = "approved"
    failure, _ = _run_script(case, "injection", [])
    assert failure and failure["reason"].startswith("refund_status")


def test_report_only_gates_are_real_thresholds():
    assert MODEL_GATES <= THRESHOLDS.keys()


def test_scenarios_include_test_credentials():
    by_name = {s["name"]: s for s in client.get("/scenarios").json()}
    assert by_name["family_plan"]["member_id"] and len(by_name["family_plan"]["patients"]) == 3


def test_turn_exposes_offer_and_session_transcript():
    sid = client.post("/sessions", json={}).json()["session_id"]
    turn = client.post(f"/sessions/{sid}/messages", json={"text": "how much is wegovy"}).json()
    assert turn["offer"] == "pa_cost" and turn["crisis"] is False
    detail = client.get(f"/sessions/{sid}").json()
    assert [t["user"] for t in detail["turns"]] == ["how much is wegovy"]


def test_crisis_turn_is_flagged():
    sid = client.post("/sessions", json={}).json()["session_id"]
    turn = client.post(f"/sessions/{sid}/messages", json={"text": "I want to end my life"}).json()
    assert turn["crisis"] is True and "988" in turn["reply"]


def test_evals_endpoints_serve_saved_runs():
    runs = client.get("/evals").json()
    assert runs and "failures" not in runs[0]
    assert "failures" in client.get("/evals/latest").json()


def test_cors_allows_browser_frontend():
    r = client.options("/sessions", headers={"Origin": "http://localhost:3000",
                                             "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") in ("*", "http://localhost:3000")
