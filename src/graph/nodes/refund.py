"""Refund node: offer what the member is owed, process it on "yes", and apply
an approver's decision.

Flow:
    "I was charged for a cancelled order"  → offer the computed refund
    member: "yes"  → total ≤ limit: approved now, with a reference number
                   → total > limit: pending a specialist's approval
    approver: "approved" / "denied"  → ``review`` tells the member the outcome

The member's "yes" can only accept the agent's offer. Nothing the member types
approves a refund above the limit; only ``review`` does, and it is reached
through a separate approver endpoint, not the chat.
"""

from __future__ import annotations

from src.config.refunds import (
    AUTO_APPROVE_LIMIT,
    LOST_OR_DAMAGED,
    find_refunds,
    needs_approval,
    new_request,
)
from src.graph.state import AgentState
from src.models.schemas import RefundRequest

_REASONS = {
    "cancelled": "the order was cancelled after you were charged",
    "duplicate": "you were charged twice",
    "overcharge": "you paid more than your plan's price",
}
_TIMING = "It goes back to your original payment method in 3–5 business days."


def refund(state: AgentState) -> AgentState:
    """Handle a refund request or the member's answer to a refund offer.

    Args:
        state: Current agent state (carries ``member`` and any prior ``refund``).

    Returns:
        State updates with the reply, the refund, and a follow-up offer.
    """
    current = state.get("refund")
    if state.get("followup") == "refund" and current and current.status == "offered":
        return _process(state, current)

    if LOST_OR_DAMAGED.search(state.get("user_input") or ""):
        return {"escalated": True, "handoff_target": "live_agent", "messages": [(
            "ai", "I'm sorry that happened. I'm connecting you with a Member Support Specialist "
                  "who can arrange a replacement or a refund.")]}

    if current and current.status == "pending_approval":
        return {"refund": current, "messages": [(
            "ai", f"Your refund of ${current.total:.2f} ({current.reference}) is with a "
                  "specialist for approval. I'll update you here as soon as it's decided.")]}

    lines = find_refunds(state["member"], exclude=set(state.get("refund_handled") or []))
    if not lines:
        return {"refund": None, "offer": "connect_agent", "messages": [(
            "ai", "I don't see any charges on your account that qualify for a refund. If an "
                  "order arrived lost or damaged, or a charge looks wrong, I can connect you "
                  "with a specialist. Would you like that?")]}

    offer = new_request(lines)
    bullets = "\n".join(f"• ${line.amount:.2f}: {line.drug_name} for {line.patient_name} "
                        f"({_REASONS[line.reason]})" for line in lines)
    header = ("I found a refund you're owed:" if len(lines) == 1
              else f"I found {len(lines)} refunds you're owed, ${offer.total:.2f} in total:")
    return {"refund": offer, "offer": "refund",
            "messages": [("ai", f"{header}\n{bullets}\nWant me to process it?")]}


def _process(state: AgentState, offer: RefundRequest) -> AgentState:
    """Approve the accepted offer, or park it for a specialist above the limit."""
    handled = (state.get("refund_handled") or []) + [line.order_number for line in offer.lines]
    if needs_approval(offer):
        pending = offer.model_copy(update={"status": "pending_approval"})
        reply = (f"Refunds over ${AUTO_APPROVE_LIMIT:.0f} need a quick specialist approval. "
                 f"I've submitted ${offer.total:.2f} (reference {offer.reference}), and I'll "
                 "update you here as soon as it's approved.")
        return {"refund": pending, "refund_handled": handled, "messages": [("ai", reply)]}
    approved = offer.model_copy(update={"status": "approved"})
    reply = f"Done. Your refund of ${offer.total:.2f} is approved (reference {offer.reference}). {_TIMING}"
    return {"refund": approved, "refund_handled": handled, "messages": [("ai", reply)]}


def review(pending: RefundRequest, approved: bool, note: str | None) -> AgentState:
    """Apply a specialist's decision and tell the member.

    The approver's note is kept on the refund for the audit trail but never
    shown to the member: it may hold internal reasoning such as a fraud flag.

    Args:
        pending: The refund awaiting approval.
        approved: The approver's decision.
        note: Optional approver note.

    Returns:
        State updates: the decided refund and the member-facing message.
    """
    decided = pending.model_copy(update={"status": "approved" if approved else "denied",
                                         "note": note})
    if approved:
        reply = (f"Good news: a specialist approved your refund of ${pending.total:.2f} "
                 f"({pending.reference}). {_TIMING}")
        return {"refund": decided, "offer": None, "messages": [("ai", reply)]}
    reply = (f"A specialist reviewed your refund request ({pending.reference}) and couldn't "
             "approve it. Would you like me to connect you with a Member Support Specialist "
             "to talk it through?")
    return {"refund": decided, "offer": "connect_agent", "messages": [("ai", reply)]}
