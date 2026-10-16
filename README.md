# pbm-member-agent

A LangGraph rebuild of a production-style **pharmacy benefit manager (PBM) member-service agent** — order status, refills, drug pricing, and safety-critical escalation — modeled on the managed-agent pattern and re-implemented on an open stack to demonstrate end-to-end agent architecture, channel-aware design, and evaluation.

> **Clean-room / no PHI.** All member data is synthetic (`src/data/synthetic.py`). Reason codes and member-facing copy are illustrative configuration, not member data. No real data is committed; the data directory is gitignored defensively.

## Why this project

The reference design is a managed, low-code agent platform (Agentforce-style). This rebuild un-blurs the three layers a managed platform fuses together, so each is explicit and testable:

| Managed concept | Here |
|---|---|
| Agent bundle | Compiled LangGraph `StateGraph` (`src/graph/build.py`) |
| Topic Selector | Crisis gate + LLM router (`src/graph/nodes/router.py`) |
| Topics / subagents | Nodes (`src/graph/nodes/`) |
| Variables | Typed `AgentState` (`src/graph/state.py`) |
| Apex / Flow actions | Plain typed tools (`src/graph/tools.py`) |
| Trust Layer moderation | Deterministic crisis gate, ordered *before* generic routing |
| Auth / step-up | `src/config/auth.py` + `auth_gate` node (Level 1.5, DOB recovery, privacy flag) |
| Order-status config | `src/config/reason_codes.py` (status truth table) |
| Refill-eligibility config | `src/config/condition_codes.py` (condition-code truth table) |

## Design principle: *LLM decides intent; code decides truth*

The LLM only classifies intent and (optionally) narrates. Order statuses are derived deterministically from the reason-code catalog and rendered by template — so output is faithful by construction, not by prompt pleading. This structurally prevents the hallucination/echo failures that plague prompt-only agents.

## Channel-aware core (the thesis)

One agent brain, channel-appropriate hands. Chat and voice share the graph but diverge by config (`src/config/channels.py`):

| | Chat | Voice |
|---|---|---|
| Lookback | 45 days (→ 6-month offer) | 10 days (30 for future fill) |
| Pagination | Top 3, "see more" | 3 at a time, "hear more" |
| Order actions | Deep-link to web CTA | Execute inline (confirm + step-up auth) |
| Prescriber Outreach status | shown | suppressed |

## Safety: crisis handling done right

Self-harm/crisis intent is pinned to escalation **deterministically, before** any generic moderation — and the escalation always surfaces the **988 Suicide & Crisis Lifeline** plus a warm human handoff. This is the control a managed platform's built-in moderation layer did not guarantee; owning the graph means owning the ordering. It also holds mid-authentication: a crisis message while a credential prompt is pending still gets 988.

Detection uses two independent detectors joined by OR. A C-SSRS-structured lexicon runs before any LLM call (the floor), and the router LLM returns a `crisis` flag (the primary detector for indirect language). The 988 reply follows that flag, so any detector that fires gets 988.

> **Measured honestly:** the lexicon alone catches 4 of 31 crisis messages (0.13) in an independently written held-out set, even though it scores 1.00 on the dev set it was built against. Indirect phrasing ("theres nothing left for me in this life") needs the LLM flag. That can't be measured on the mock provider, so the ship gate is `crisis_recall_holdout = 1.00` on a live model. See [evals/README.md](evals/README.md).

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Scripted 9-act demo (multi-turn; add --pause to step through live)
python -m scripts.demo

# Interactive CLI (zero-cost mock LLM by default)
python -m src.serving.cli --scenario family_plan --channel chat
python -m src.serving.cli --scenario single_patient_mixed_statuses --channel voice --unverified

# API  ->  http://localhost:8000/docs   (in-memory sessions unless DATABASE_URL is set)
uvicorn src.serving.app:app --reload --port 8000

# Docker: API on :8000 + Postgres (sessions, checkpoints, turn audit log)
docker compose up --build
# ...plus the Next.js console + eval dashboard on :3000
docker compose --profile web up --build
# or run the web app locally against the API above (see web/README.md)
cd web && npm install && npm run dev

# Tests (hermetic, no API keys) and evals (scorecard, saved to evals/results/)
pytest -q
python -m evals.run
```

## Stack

| Layer | Choice |
|---|---|
| Backend | Python, FastAPI, Pydantic, LangGraph |
| Frontend | TypeScript, React, Next.js, Tailwind ([web/](web/README.md)): operator console + eval dashboard |
| Database | PostgreSQL: LangGraph checkpoints, `sessions`, `turns` audit log ([store.py](src/serving/store.py)) |
| AI | Anthropic Python SDK with structured outputs; mock provider for hermetic tests |
| Delivery | Docker, pytest, GitHub Actions (tests against a Postgres service, image build + smoke test) |
| Cloud | AWS: ECR, ECS Fargate, RDS PostgreSQL, Secrets Manager ([docs/DEPLOY.md](docs/DEPLOY.md)) |
| Deferred | pgvector (benefit-doc RAG), S3, Redis/queues: added when the workload needs them (ADR-013) |

Frontend: the API is the contract (`/openapi.json`, also exported to [docs/openapi.json](docs/openapi.json)), mirrored by hand in [web/lib/types.ts](web/lib/types.ts). CORS is on (`CORS_ORIGINS`, default `*` because all data is synthetic). The console renders structured `shown` orders as cards and `offer` as quick replies. Its decision inspector shows each turn's intent, escalation, handoff, crisis and offer, so you can see the LLM/code split live.

API sketch:

```bash
SID=$(curl -s -X POST localhost:8000/sessions -H 'content-type: application/json' \
  -d '{"scenario": "single_patient_mixed_statuses", "channel": "chat"}' | jq -r .session_id)
curl -s -X POST localhost:8000/sessions/$SID/messages -H 'content-type: application/json' \
  -d '{"text": "where is my order"}'
```

### Live LLM (optional)

Pluggable provider, selected by env var (see `.env.example`):

```bash
export LLM_PROVIDER=anthropic    # Claude via the Anthropic SDK (default model claude-opus-5)
export ANTHROPIC_API_KEY=sk-ant-...
# or
export LLM_PROVIDER=openrouter   # Claude Haiku 5.5 by default (ADR-015), Anthropic-hosted first
export OPENROUTER_API_KEY=sk-or-...  # or put it in .env, then: set -a && source .env && set +a
# or
export LLM_PROVIDER=gemini
export GOOGLE_API_KEY=...
```

## Scenarios (synthetic)

`single_patient_mixed_statuses`, `family_plan`, `no_orders`, `older_orders_only`, `escalation_required`, `payment_hold`, plus the refill scenarios and `refund_small` / `refund_large`. Each mirrors a named scenario from the source requirements. Order dates are relative to today, so lookback windows behave the same on every run.

## Capabilities (built deep)

- **Order Status:** fetch → window → resolve → rank → paginate → render, channel-aware.
  Chat looks back 45 days and offers a 6-month search; voice looks back 10 days.
- **Refill:** condition-code eligibility engine (remaps, listing priority,
  cart eligibility, controlled/too-old/renewal/transfer outcomes). A held Rx
  routes to a specialist instead of being offered.
- **Drug Price:** coverage, prior auth, and covered price, with generic
  alternatives. For a PA drug the cost is offered rather than volunteered.
  It never recommends a drug for a condition.
- **Multi-turn:** checkpointed sessions. "See more", "yes" and "no" resolve
  against the offer the agent just made, in code (ADR-008).
- **Authentication:** Level 1.5 step-up across turns (member ID or Rx number →
  DOB → original request replayed), with bounded retries, privacy-flag transfer
  and caller-type routing. Identity tokens never reach the LLM (ADR-009).
- **Refunds:** the amount is computed from order data (cancelled after charge,
  duplicate charge, overcharged copay), never by the LLM. The member's "yes"
  processes refunds up to $50 at once. Larger ones go to a specialist, who
  types "approved" or "denied" (`POST /sessions/{id}/approval`) and the agent
  tells the member. Nothing the member types approves a refund. Lost or
  damaged shipments go to a specialist (ADR-014).
- **Escalation:** crisis-safe (988 + warm handoff), ordered before routing.

Both **chat and voice** run on the one graph, diverging by config.

## Evaluation

`python -m evals.run` gives the scorecard; the methodology is in [evals/README.md](evals/README.md). Mock-provider baseline:

| Metric | Value | Bar |
|---|---|---|
| Groundedness (rendered lines traceable to member data) | 1.00 | = 1.00 ✅ |
| Multi-turn task completion (16 conversations) | 1.00 | ≥ 0.90 ✅ |
| Crisis recall, dev set (escalate + 988) | 1.00 | = 1.00 ✅ (seen during build) |
| Crisis recall, held-out set: lexicon only | 0.13 | = 1.00 ❌ needs live-LLM run |
| Crisis false-escalation rate (dev / held-out) | 0.00 / 0.10 | ≤ 0.10 ✅ |
| Routing accuracy | 0.79 | ≥ 0.90 ❌ mock keyword router; judge with a live LLM |

## Status

- **Stubbed (real interfaces):** in-conversation order-action *execution*
  (payment-hold resolve, cancel, address). Chat deep-links today; voice
  inline execution with confirmation is the next pass.
- **Sessions** persist in Postgres when `DATABASE_URL` is set, and survive API
  restarts. Idle expiry and retention aren't implemented yet.
- **Tests:** 63 hermetic (mock LLM, no keys) plus 3 Postgres tests that run in CI.

See [docs/PRD.md](docs/PRD.md) and [docs/decisions.md](docs/decisions.md).
