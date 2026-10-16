"""Anthropic provider request shape and refusal handling, with the SDK client faked."""

from __future__ import annotations

import json
from types import SimpleNamespace

from src.graph.nodes.router import _ROUTER_SCHEMA, _classify
from src.models.schemas import Intent
from src.utils.llm import AnthropicProvider


class _FakeMessages:
    def __init__(self, stop_reason: str, text: str) -> None:
        self.stop_reason, self.text, self.kwargs = stop_reason, text, {}

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(stop_reason=self.stop_reason,
                               content=[SimpleNamespace(type="text", text=self.text)])


def _provider(stop_reason: str = "end_turn", text: str = "") -> AnthropicProvider:
    p = AnthropicProvider.__new__(AnthropicProvider)
    p.model = "claude-opus-5"
    p.client = SimpleNamespace(beta=SimpleNamespace(messages=_FakeMessages(stop_reason, text)))
    return p


def test_router_schema_is_enforced_via_structured_outputs():
    p = _provider(text=json.dumps({"intent": "refill", "crisis": False}))
    assert _classify("refill my lisinopril", p) == (Intent.REFILL, False)
    sent = p.client.beta.messages.kwargs
    assert sent["output_config"]["format"] == {"type": "json_schema", "schema": _ROUTER_SCHEMA}
    assert sent["model"] == "claude-opus-5" and sent["fallbacks"] == "default"


def test_refusal_hands_off_to_a_human():
    assert _classify("anything", _provider(stop_reason="refusal")) == (Intent.ESCALATION, False)
