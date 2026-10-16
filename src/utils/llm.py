"""Pluggable LLM provider abstraction.

One interface, four backends selected by the ``LLM_PROVIDER`` env var:

* ``mock``      — deterministic, zero-cost, no network. Default; lets the repo
                  clone-and-run and keeps evals hermetic.
* ``anthropic`` — Claude via the official Anthropic SDK, with structured outputs
                  when the caller passes a JSON schema. Uses ``ANTHROPIC_API_KEY``.
* ``openrouter``— routes to Claude (default) or any OpenRouter model. Uses
                  ``OPENROUTER_API_KEY``. Honors the "default to Claude" rule.
* ``gemini``    — Google GenAI, uses ``GOOGLE_API_KEY`` (GCP credits).

Nodes depend only on :class:`LLMProvider`, never on a concrete SDK — the
provider-agnostic seam is intentional and swappable in one line.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any

# Default Claude model when routing through OpenRouter (per project convention).
DEFAULT_CLAUDE_MODEL = "anthropic/claude-opus-5.5"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


class LLMProvider(ABC):
    """Minimal chat interface every backend implements."""

    @abstractmethod
    def complete(self, system: str, user: str, *, json_mode: bool = False,
                 schema: dict | None = None) -> str:
        """Return a single completion string.

        Args:
            system: System prompt.
            user: User message.
            json_mode: Hint that the caller expects a JSON object back.
            schema: Optional JSON Schema for that object. Backends with
                structured outputs enforce it; the others ignore it.

        Returns:
            The model's text response.
        """
        raise NotImplementedError


class MockProvider(LLMProvider):
    """Deterministic stand-in used for offline runs and hermetic evals.

    Intent classification is keyword-driven so tests are stable; narration
    echoes a compact deterministic summary. This is intentionally dumb — the
    graph's *control flow* and deterministic resolution are what we test, not
    the mock's prose.
    """

    def complete(self, system: str, user: str, *, json_mode: bool = False,
                 schema: dict | None = None) -> str:
        text = user.lower()
        if json_mode:
            intent = self._classify(text)
            if intent == "crisis":
                return json.dumps({"intent": "escalation", "crisis": True})
            return json.dumps({"intent": intent, "crisis": False})
        return "OK"

    @staticmethod
    def _classify(text: str) -> str:
        rules = [
            (("suicide", "kill myself", "self harm", "self-harm", "hurt myself",
              "end my life"), "crisis"),
            (("agent", "representative", "human", "supervisor", "person",
              "useless", "ridiculous"), "escalation"),
            (("refund", "money back", "charged twice", "double charged", "overcharged", "charged for",
              "charged me"), "refund"),
            (("refill", "reorder", "renew"), "refill"),
            (("price", "cost", "how much", "copay"), "drug_price"),
            (("cancel", "update address", "change address", "expedite",
              "payment method", "approve"), "order_action"),
            (("thank", "goodbye", "bye", "all set", "that's all", "done"), "closing"),
            (("order", "prescription", "rx", "status", "where is", "shipped",
              "delivery", "arrive", "medication", "meds"), "order_status"),
        ]
        for needles, intent in rules:
            if any(n in text for n in needles):
                return intent
        return "off_topic"


class AnthropicProvider(LLMProvider):
    """Claude through the Anthropic Python SDK.

    Routing is a short classification, so effort is ``low``. Server-side
    fallbacks re-run a safety-declined request on another model. A refusal that
    survives them hands the member to a human instead of guessing an intent.
    """

    _REFUSED = json.dumps({"intent": "escalation", "crisis": False})

    def __init__(self, model: str | None = None) -> None:
        import anthropic  # local import keeps mock path dependency-free

        self.model = model or os.getenv("LLM_MODEL", DEFAULT_ANTHROPIC_MODEL)
        self.client = anthropic.Anthropic()

    def complete(self, system: str, user: str, *, json_mode: bool = False,
                 schema: dict | None = None) -> str:
        output_config: dict[str, Any] = {"effort": "low"}
        if schema:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        resp = self.client.beta.messages.create(
            model=self.model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config=output_config,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if resp.stop_reason == "refusal":
            return self._REFUSED
        return next(b.text for b in resp.content if b.type == "text")


class OpenRouterProvider(LLMProvider):
    """OpenRouter backend (reaches Claude, GPT, Gemini via one API).

    Prefers Anthropic's own endpoint and falls back only to hosts that support
    every parameter sent, so the schema is never silently dropped. Effort is
    ``low`` for the same reason as :class:`AnthropicProvider`.
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_CLAUDE_MODEL)
        self.api_key = os.environ["OPENROUTER_API_KEY"]

    def complete(self, system: str, user: str, *, json_mode: bool = False,
                 schema: dict | None = None) -> str:
        import httpx  # local import keeps mock path dependency-free

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "reasoning": {"effort": "low"},
            "provider": {"order": ["anthropic"], "require_parameters": True},
        }
        if schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "strict": True, "schema": schema},
            }
        elif json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


class GeminiProvider(LLMProvider):
    """Google GenAI backend (uses GCP credits)."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_GEMINI_MODEL)
        self.api_key = os.environ["GOOGLE_API_KEY"]

    def complete(self, system: str, user: str, *, json_mode: bool = False,
                 schema: dict | None = None) -> str:
        import httpx

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        gen_config: dict[str, Any] = {"temperature": 0}
        if json_mode:
            gen_config["responseMimeType"] = "application/json"
        resp = httpx.post(
            url,
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": gen_config,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def get_provider() -> LLMProvider:
    """Instantiate the provider named by ``LLM_PROVIDER`` (default ``mock``).

    Returns:
        A ready-to-use :class:`LLMProvider`.

    Raises:
        ValueError: If ``LLM_PROVIDER`` names an unknown backend.
    """
    name = os.getenv("LLM_PROVIDER", "mock").lower()
    if name == "mock":
        return MockProvider()
    if name == "anthropic":
        return AnthropicProvider()
    if name == "openrouter":
        return OpenRouterProvider()
    if name == "gemini":
        return GeminiProvider()
    raise ValueError(f"Unknown LLM_PROVIDER: {name!r} (expected mock|anthropic|openrouter|gemini)")
