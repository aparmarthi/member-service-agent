"""Multi-turn session wrapper shared by the CLI, API, demo script, and evals.

One compiled graph with a checkpointer serves every session; each session is a
``thread_id``. State (pending offers, pagination, auth progress) survives
between turns, which is what makes "yes, show me the rest" and token → DOB
authentication work.

The checkpointer is Postgres when ``DATABASE_URL`` is set (see ``store.py``)
and ``MemorySaver`` otherwise.
"""

from __future__ import annotations

from functools import lru_cache
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from src.config.channels import for_channel
from src.config.refunds import parse_decision
from src.data import synthetic
from src.graph.build import build_graph
from src.graph.nodes import refund as refund_node
from src.models.schemas import AgentTurnResult, Channel, Intent
from src.serving import store
from src.utils.llm import LLMProvider

# Marks approver decisions in the transcript and turn log, so they are never
# mistaken for something the member typed.
APPROVER_PREFIX = "[approver] "

# Domain types the checkpointer may rebuild from saved state. LangGraph is moving
# to block unregistered types on deserialization, so the allowlist is explicit.
_CHECKPOINT_TYPES = [
    ("src.models.schemas", name)
    for name in ("Channel", "Intent", "Member", "ResolvedStatus", "RefillCandidate", "PriceQuote",
                 "RefundLine", "RefundRequest")
] + [("src.config.auth", name) for name in ("AuthState", "AuthLevel", "CallerType")]


def _saver() -> BaseCheckpointSaver:
    serde = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_TYPES)
    return store.checkpointer(serde) if store.enabled() else MemorySaver(serde=serde)


@lru_cache(maxsize=1)
def default_graph():
    """Return the process-wide checkpointed graph (env-selected LLM provider)."""
    return build_graph(checkpointer=_saver())


class AgentSession:
    """One member conversation on one channel.

    Args:
        scenario: Synthetic member scenario name (see ``synthetic.SCENARIOS``).
        channel: Delivery channel.
        verified: Whether the session starts authenticated (chat behind a web
            login). ``False`` exercises step-up auth (token → DOB).
        provider: Optional LLM override; builds a dedicated graph when given.
        thread_id: Resume an existing checkpointed thread instead of starting one.
    """

    def __init__(
        self,
        scenario: str,
        channel: Channel = Channel.CHAT,
        verified: bool = True,
        provider: LLMProvider | None = None,
        thread_id: str | None = None,
    ) -> None:
        self.scenario = scenario
        self.member = synthetic.build(scenario)
        self.channel = channel
        self.verified = verified
        self.thread_id = thread_id or uuid4().hex
        self.turns: list[tuple[str, AgentTurnResult]] = []
        self._graph = (build_graph(provider, checkpointer=_saver())
                       if provider else default_graph())

    def send(self, text: str) -> AgentTurnResult:
        """Run one member utterance through the graph.

        Args:
            text: The member's message.

        Returns:
            The agent's reply plus the decisions the graph made this turn.
        """
        result = self._graph.invoke(
            {
                "user_input": text,
                "channel": self.channel,
                "member": self.member,
                "is_verified": self.verified,
                "messages": [("user", text)],
            },
            {"configurable": {"thread_id": self.thread_id}},
        )
        intent = result.get("intent") or Intent.OFF_TOPIC
        shown = []
        if intent is Intent.ORDER_STATUS and result.get("resolved"):
            size = for_channel(self.channel).page_size
            start = (result.get("page", 1) - 1) * size
            shown = result["resolved"][start:start + size]
        turn = AgentTurnResult(
            reply=result["messages"][-1].content,
            intent=intent,
            escalated=bool(result.get("escalated")),
            handoff_target=result.get("handoff_target"),
            shown=shown,
            has_more=bool(result.get("has_more")) and intent is Intent.ORDER_STATUS,
            crisis=bool(result.get("crisis")),
            offer=result.get("offer"),
            refund=result.get("refund") if intent is Intent.REFUND else None,
        )
        self.turns.append((text, turn))
        return turn

    def state(self) -> dict:
        """Return this thread's checkpointed state (refund, auth progress, offer)."""
        return self._graph.get_state({"configurable": {"thread_id": self.thread_id}}).values

    def review_refund(self, text: str) -> AgentTurnResult:
        """Apply a specialist's plain-text decision ("approved", "denied - reason").

        This writes to the thread directly instead of running the graph: the
        decision comes from staff, not the member, so it must never pass
        through the router, where a member's "approved" would land.

        Args:
            text: The approver's message.

        Returns:
            The member-facing update, as a turn.

        Raises:
            ValueError: If the text is neither an approval nor a denial.
            LookupError: If no refund on this session is awaiting approval.
        """
        approved, note = parse_decision(text)
        config = {"configurable": {"thread_id": self.thread_id}}
        pending = self.state().get("refund")
        if pending is None or pending.status != "pending_approval":
            raise LookupError("No refund on this session is awaiting approval.")
        update = refund_node.review(pending, approved, note)
        self._graph.update_state(config, update, as_node="refund")
        turn = AgentTurnResult(reply=update["messages"][0][1], intent=Intent.REFUND,
                               offer=update["offer"], refund=update["refund"])
        self.turns.append((APPROVER_PREFIX + text, turn))
        return turn
