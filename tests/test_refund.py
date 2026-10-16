"""Refunds: amounts come from order data, small ones process on "yes", large ones
wait for a specialist's plain-text decision, and the member can never approve."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.config.refunds import find_refunds, parse_decision
from src.data import synthetic
from src.serving.app import app
from src.serving.session import AgentSession

client = TestClient(app)


def test_amounts_and_reasons_come_from_order_data():
    small = {line.reason: line.amount for line in find_refunds(synthetic.build("refund_small"))}
    assert small == {"duplicate": 18.75, "cancelled": 12.40}
    [large] = find_refunds(synthetic.build("refund_large"))
    assert (large.reason, large.amount) == ("overcharge", 87.60)


def test_uncharged_orders_are_never_refundable():
    for name in synthetic.SCENARIOS:
        if not name.startswith("refund_"):
            assert find_refunds(synthetic.build(name)) == [], name


@pytest.mark.parametrize("text, expected", [
    ("approved", (True, None)),
    ("Approve", (True, None)),
    ("ok", (True, None)),
    ("approved - verified against the claim", (True, "verified against the claim")),
    ("denied", (False, None)),
    ("Denied: already reversed by the bank.", (False, "already reversed by the bank")),
    ("reject", (False, None)),
    ("looks good", (True, None)),
    ("declined, duplicate already refunded", (False, "duplicate already refunded")),
    ("Decline", (False, None)),
    ("not approved", (False, None)),
])
def test_plain_text_decisions(text, expected):
    assert parse_decision(text) == expected


@pytest.mark.parametrize("text", ["maybe", "{\"approved\": true}", "check with finance"])
def test_unclear_decisions_are_rejected(text):
    with pytest.raises(ValueError):
        parse_decision(text)


def test_small_refund_processes_on_yes():
    s = AgentSession("refund_small")
    offer = s.send("I want a refund")
    assert offer.offer == "refund" and offer.refund.status == "offered"
    assert offer.refund.total == 31.15
    done = s.send("yes")
    assert done.refund.status == "approved" and offer.refund.reference in done.reply
    assert s.send("I want a refund").refund is None  # already refunded, not offered twice


@pytest.mark.parametrize("reply", ["approved", "Approve it", "do it", "sounds good", "process it"])
def test_small_refund_processes_on_plain_consent(reply):
    s = AgentSession("refund_small")
    s.send("I was charged twice, I want a refund")
    assert s.send(reply).refund.status == "approved"


@pytest.mark.parametrize("reply", ["approved", "do it"])
def test_member_consent_never_skips_the_specialist(reply):
    s = AgentSession("refund_large")
    s.send("I want my money back")
    assert s.send(reply).refund.status == "pending_approval"


def test_large_refund_waits_for_specialist_and_member_cannot_approve():
    s = AgentSession("refund_large")
    s.send("I was overcharged on my copay")
    assert s.send("yes").refund.status == "pending_approval"
    member_says = s.send("approved")
    assert member_says.refund.status == "pending_approval" and "with a specialist" in member_says.reply
    s.send("I approve my refund")
    assert s.send("refund status?").refund.status == "pending_approval"

    turn = s.review_refund("approved")
    assert turn.refund.status == "approved" and "approved your refund of $87.60" in turn.reply
    with pytest.raises(LookupError):
        s.review_refund("approved")


def test_lost_or_damaged_goes_to_a_specialist():
    turn = AgentSession("refund_small").send("my package was damaged, I want a refund")
    assert turn.escalated and turn.handoff_target == "live_agent"


def test_unverified_member_steps_up_before_refund_details():
    turn = AgentSession("refund_large", verified=False).send("I want a refund")
    assert turn.handoff_target == "pending_auth" and "$" not in turn.reply


def test_approval_endpoint_takes_plain_text():
    sid = client.post("/sessions", json={"scenario": "refund_large"}).json()["session_id"]
    assert client.post(f"/sessions/{sid}/approval", json={"text": "approved"}).status_code == 409
    client.post(f"/sessions/{sid}/messages", json={"text": "I want a refund"})
    client.post(f"/sessions/{sid}/messages", json={"text": "yes"})
    assert client.post(f"/sessions/{sid}/approval", json={"text": "maybe"}).status_code == 422

    body = client.post(f"/sessions/{sid}/approval",
                       json={"text": "denied - duplicate already reversed"}).json()
    assert body["refund"]["status"] == "denied" and body["offer"] == "connect_agent"
    assert "reversed" not in body["reply"]  # approver notes stay internal
    turns = client.get(f"/sessions/{sid}").json()["turns"]
    assert turns[-1]["user"] == "[approver] denied - duplicate already reversed"
