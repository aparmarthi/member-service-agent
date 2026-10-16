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
                               content=[SimpleNamespace(type="text", text=self.text)],
                               usage=SimpleNamespace(input_tokens=580, output_tokens=19))


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
    assert (p.calls, p.tokens_in, p.tokens_out, p.cost_usd) == (1, 580, 19, None)  # no $ from the SDK


def test_refusal_hands_off_to_a_human():
    assert _classify("anything", _provider(stop_reason="refusal")) == (Intent.ESCALATION, False)


def test_openrouter_prefers_anthropic_and_enforces_the_schema(monkeypatch):
    import httpx

    from src.utils.llm import OpenRouterProvider

    sent = {}

    def fake_post(url, *, headers, json, timeout):
        sent.update(json)
        body = {"choices": [{"message": {"content": '{"intent": "refill", "crisis": false}'}}],
                "usage": {"prompt_tokens": 580, "completion_tokens": 19, "cost": 6.75e-05}}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setattr(httpx, "post", fake_post)
    p = OpenRouterProvider()
    assert _classify("refill my lisinopril", p) == (Intent.REFILL, False)
    assert (p.calls, p.tokens_in, p.tokens_out, p.cost_usd) == (1, 580, 19, 6.75e-05)
    assert sent["model"] == "anthropic/claude-haiku-5.5"
    assert sent["provider"] == {"order": ["anthropic"], "require_parameters": True}
    assert sent["response_format"]["json_schema"]["schema"] == _ROUTER_SCHEMA
    assert "temperature" not in sent  # Claude 5.5 rejects sampling params


def test_usage_metrics_are_per_turn_and_skip_unknown_cost():
    from src.evaluation.harness import _usage_metrics
    from src.utils.llm import MockProvider

    assert _usage_metrics(MockProvider(), turns=10) == {}  # mock counts nothing
    p = MockProvider()
    p._record(500, 20, 0.0001)
    p._record(500, 20, 0.0001)
    assert _usage_metrics(p, turns=4) == {"tokens_per_turn": 260, "cost_per_1k_turns_usd": 0.05,
                                          "eval_cost_usd": 0.0002}
    p._record(500, 20, None)
    assert "eval_cost_usd" not in _usage_metrics(p, turns=4)
