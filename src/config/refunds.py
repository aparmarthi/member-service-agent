"""Refund rules: what the member is owed, when a human must approve it, and how
an approver's plain-text decision is read.

The amount is always computed from order data. The LLM only recognizes that
the member is asking for a refund; it never proposes, edits, or approves an
amount.

    owed = sum(charges) - expected cost
    expected cost = 0 if nothing was filled, else the plan price of each Rx

Lost or damaged shipments are not computed here. Reship versus refund, fraud
checks, and controlled-drug rules need a specialist's judgment.
"""

from __future__ import annotations

import re

from src.config.reason_codes import ParentStatus, lookup
from src.models.schemas import Member, RefundLine, RefundRequest

# At or below this the member's "yes" processes the refund; above it a
# specialist approves. Configurable per client; $50 covers most copay errors.
AUTO_APPROVE_LIMIT = 50.00

LOST_OR_DAMAGED = re.compile(
    r"\b(lost|damaged|broken|stolen|missing|never (arrived|came|got here))\b", re.I)

_APPROVE = re.compile(r"^\s*(approved?|yes|ok(ay)?|lgtm)\b", re.I)
_DENY = re.compile(r"^\s*(den(y|ied)|reject(ed)?|no)\b", re.I)


def find_refunds(member: Member, exclude: set[str] | frozenset[str] = frozenset()) -> list[RefundLine]:
    """Return every refundable charge on the account, one line per order.

    Args:
        member: The member whose orders to check.
        exclude: Order numbers already refunded or awaiting approval.

    Returns:
        Refund lines, largest first.
    """
    lines = []
    for patient in member.patients:
        for order in patient.orders:
            if not order.charges or order.order_number in exclude:
                continue
            filled = [rx for rx in order.prescriptions
                      if (rc := lookup(rx.status_code)) is None
                      or rc.parent_status is not ParentStatus.NOT_FILLED]
            expected = sum(rx.price or 0 for rx in filled)
            owed = round(sum(order.charges) - expected, 2)
            if owed <= 0:
                continue
            reason = ("cancelled" if not filled
                      else "duplicate" if len(order.charges) > 1 else "overcharge")
            lines.append(RefundLine(
                order_number=order.order_number,
                patient_name=f"{patient.first_name} {patient.last_name}",
                drug_name=order.prescriptions[0].drug_name if order.prescriptions else "your order",
                reason=reason, amount=owed))
    return sorted(lines, key=lambda line: -line.amount)


def new_request(lines: list[RefundLine]) -> RefundRequest:
    """Bundle refund lines into one offer with a stable reference number."""
    return RefundRequest(reference=f"RF-{lines[0].order_number[-6:]}", lines=lines,
                         total=round(sum(line.amount for line in lines), 2), status="offered")


def needs_approval(request: RefundRequest) -> bool:
    """Whether a specialist must approve before money moves."""
    return request.total > AUTO_APPROVE_LIMIT


def parse_decision(text: str) -> tuple[bool, str | None]:
    """Read an approver's plain-text decision.

    Accepts what a person would actually type: "approved", "ok", "denied -
    already reversed by the bank". Anything after the first word is kept as a
    note.

    Args:
        text: The approver's message.

    Returns:
        ``(approved, note)``.

    Raises:
        ValueError: If the text is neither an approval nor a denial.
    """
    for pattern, approved in ((_APPROVE, True), (_DENY, False)):
        match = pattern.match(text)
        if match:
            note = text[match.end():].strip(" \t-—:,.") or None
            return approved, note
    raise ValueError('Reply "approved" or "denied" (a short note after it is fine).')
