# PRD: Member Service Agent (pharmacy benefits, LangGraph)

## Problem
Members contacting a pharmacy benefit manager want fast, accurate answers about
their prescription orders — where an order is, why it's delayed, how to resolve a
hold — across chat and voice. Managed low-code agent platforms can ship this
capability quickly, but they concentrate control flow, safety, and grounding inside
an opaque runtime. This project builds it on an open stack to expose and own those
layers.

## Users
- **Members** checking their own order status (primary).
- **Caregivers** on a family plan viewing dependents' orders (permissioned).
- **Care specialists** receiving warm handoffs on escalation.

## North Star metric
**Contained resolution rate** — share of turns that answer the member's question
correctly from grounded system data without unnecessary escalation.

## Guardrail metrics
1. **Escalation recall on crisis/complex intent** — must approach 100%. A missed
   self-harm escalation is the highest-severity failure.
2. **Groundedness** — 0% of surfaced order facts fabricated (enforced structurally).
3. **Routing accuracy** — correct intent selection, especially escalation.

## Scope (this build)
- Order Status read path, both channels, with lookback windows enforced (chat 45 days
  with a 6-month offer; voice 10 days, 30 for future fills) and pagination follow-ups.
- Refill eligibility (condition-code engine) and drug price (coverage, prior auth,
  generic alternative), each with deterministic follow-ups ("yes", "see more").
- Multi-turn sessions on a LangGraph checkpointer; follow-ups resolved in code from
  the offer the agent made, not re-classified by the LLM.
- Step-up auth across turns (member ID / Rx number → DOB → replay of the original
  request); identity tokens are matched in code and never sent to the LLM.
- Crisis-safe escalation with 988 + human handoff, including mid-authentication.
- Serving: FastAPI (sessions, transcript, eval endpoints), Postgres persistence
  (checkpoints, sessions, turn audit log), Dockerfile + compose, GitHub Actions CI.
  Next.js operator console + eval dashboard in `web/`; AWS layout in `docs/DEPLOY.md`.
- Eval harness (`evals/`) for every metric above, with timestamped results.
- Stubs (real interfaces): order-action execution (deep-link only).

## Out of scope (next passes)
- Deep order-action execution (voice inline execute + confirmation).
- An independently written red-team set (the injection suite was written alongside the defenses).
- Idle-session expiry and a retention window for conversation data.
- RAG for benefit inquiry.

## Success criteria (acceptance)
- Statuses presented in priority order: self-serve holds → ready → other → delivered.
- Chat states "last 45 days"; voice states "last 10 days"; voice reads 3 at a time.
- `PROFILE_HOLD` and API errors transfer to a human.
- Prescriber Outreach suppressed on voice.
- No orders → offer help / refill check, never a dead end.
- A held prescription is never offered for refill; a profile hold hands off without "anything else?".
- Failed verification (2 bad tokens, or DOB retries exhausted) transfers to a human.

## Current results
Scorecards are in the [README](../README.md#evaluation) and [`evals/README.md`](../evals/README.md).
On the mock provider, groundedness, task completion (18/18), dev crisis recall and
injection resistance (25/25 attacks, 5/5 controls) hold, and CI blocks merges on them.
**On the independent held-out set the lexicon alone reaches 0.13.** On Claude Haiku 5.5,
the default live router (ADR-015), every gate passes, including held-out crisis recall
1.00 and routing 1.00.
Indirect crisis language still rests on the LLM flag, so held-out recall stays the ship
gate for any model or prompt change.

## Trade-offs
- **Determinism over LLM freedom** for status derivation: sacrifices conversational
  flourish for faithfulness and testability. Correct for a regulated domain.
- **Mock-first LLM**: zero-cost, hermetic evals; live providers swap in via one env var.
