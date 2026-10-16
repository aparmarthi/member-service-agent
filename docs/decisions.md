# Decision Log

## ADR-001: LangGraph over vanilla LangChain AgentExecutor
**Decision:** Model the agent as a compiled `StateGraph`, not a ReAct
`AgentExecutor`.
**Why:** The reference agent is a deterministic state machine with LLM steps
embedded (topics, guarded transitions, imperative "if X then call action"
blocks), not an open-ended tool-picking loop. LangGraph's nodes/edges map 1:1 to
topics/transitions and keep control flow in code where it's testable. A ReAct
loop would relocate that logic into fragile prose — the root cause of several
production defects.

## ADR-002: LLM decides intent; code decides truth
**Decision:** The LLM classifies intent and optionally narrates. Order-status
derivation is 100% deterministic (reason-code catalog + template render).
**Why:** Regulated healthcare context. Faithfulness must be structural, not a
matter of prompt compliance. Eliminates the hallucination/echo failure class by
construction and makes outputs unit-testable.

## ADR-003: Crisis gate ordered before generic routing
**Decision:** A deterministic crisis gate runs *before* the LLM router and pins
self-harm intent to escalation; escalation always surfaces 988 + human handoff.
**Why:** In the reference platform, a built-in content-moderation classifier
intercepted self-harm input ahead of the customer's escalation topic and emitted
a canned refusal — a patient-safety failure the customer could not reorder.
Owning the graph means owning the ordering; we guarantee crisis intent reaches a
warm handoff. This is the strongest argument for an open stack in this domain.

## ADR-004: Channel-aware core (same brain, different hands)
**Decision:** One graph; chat/voice diverge via `ChannelConfig` data
(lookback, pagination, action fulfillment), not forked prompts or forked graphs.
**Why:** The two channels genuinely differ — chat can deep-link to an
authenticated web page for actions (lowest liability), while voice must execute
in-conversation (raising the bar: confirmation, step-up auth). Encoding the
divergence as data keeps it explicit and testable and demonstrates channel
product reasoning without duplicating the agent.

## ADR-006: Config-as-data truth tables for statuses, refills, and auth
**Decision:** Encode reason codes, refill condition codes, and auth tiers as
typed data tables (`src/config/`), not prose in prompts.
**Why:** These are large, exact, regulated mappings (~30 status codes, ~25
condition codes with remap + priority rules, tiered auth). As data they are
unit-testable, diffable, and impossible for the LLM to get wrong. This is the
same "config-as-data" pattern the reference platform used in custom metadata —
reproduced here in a form a reviewer can read and test.

## ADR-007: Auth gate as a graph node, before PHI intents
**Decision:** A deterministic `auth_gate` node runs after routing and enforces
Level 1.5 step-up before any PHI-exposing intent; the LLM never adjudicates
identity.
**Why:** Identity/PHI access is a compliance boundary, not a conversational
nicety. Making it a graph node keeps it explicit, ordered, and testable, and
lets chat (session-verified) and voice (token + DOB) share one contract.

## ADR-005: Pluggable LLM provider, mock default
**Decision:** LLM behind an interface with mock | openrouter | gemini backends;
mock is default.
**Why:** Repo clones and runs with zero keys/cost; evals stay hermetic and
CI-friendly; live Claude (via OpenRouter) or Gemini swap in with one env var,
enabling multi-model consensus evaluation later. Provider-agnostic design is an
MLE signal and costs ~30 lines.

## ADR-008: Checkpointed sessions; follow-ups resolved in code
**Decision:** The graph compiles with a LangGraph checkpointer keyed by
`thread_id` (`MemorySaver` in-process; `src/serving/session.py`). When a node
offers something ("see more", "hear the estimated cost", "check 6 months"), it
records an `offer` in state. If the next turn is a yes, no, or "more", the
router maps it straight to the follow-up without calling the LLM.
**Why:** "Yes" on its own has no intent; an LLM classifying it in isolation
routes it off-topic, and one given the full history can still pick the wrong
offer. The agent knows exactly what it offered, so resolving the follow-up is a
lookup, not a guess. This extends ADR-002 to dialogue state.
**Trade-off:** `MemorySaver` loses sessions on restart and never expires them.
A deployment would swap in a Postgres/Redis saver (same interface). A free-form
follow-up ("what about the second one?") still goes to the LLM.

## ADR-009: Identity tokens never reach the LLM
**Decision:** While auth is pending, the router skips the LLM entirely and the
auth gate consumes the utterance as a credential. Member ID or Rx number is
matched against *this member's* record, then DOB is parsed (ISO, US numeric,
or spelled out). Bounded retries end in a human transfer, and the parked
request is replayed after verification.
**Why:** Sending identifiers to a third-party model adds PHI exposure for no
benefit; matching is exact and deterministic. Replaying the original request
means the member doesn't have to repeat themselves.
**Exception:** an escalation intent (crisis or "get me a human") clears pending
auth and proceeds. This was a regression caught by the `crisis_mid_auth` eval:
a crisis utterance had been consumed as a failed credential.

## ADR-010: Lookback enforced against relative dates
**Decision:** `resolve_statuses` filters by the channel's window from an
injectable `as_of` date (chat 45 days, voice 10, future fills 30), and
synthetic order dates are generated relative to today.
**Why:** With fixed dates, the window either filtered everything out as time
passed or wasn't really being tested. Relative dates keep the voice-vs-chat
difference (4 vs 5 orders) stable and testable, and `as_of` keeps tests
deterministic.

## ADR-011: Evals as gated, versioned artifacts, not tuned against
**Decision:** `python -m evals.run` scores routing, crisis recall/false alarms,
groundedness (an independent oracle, not the renderer), and multi-turn task
completion/containment. It saves timestamped JSON and exits non-zero below
thresholds.
**Why:** Training-style unit tests prove the code does what I wrote. Evals
measure whether it does what members need, and track that across changes.
Crisis recall on the keyword gate was 0.60 when this harness first ran. That
finding led to ADR-012.

## ADR-012: Crisis detection as two OR'd detectors, judged on a held-out set
**Decision:** A C-SSRS-structured lexicon (`src/config/crisis.py`) runs before
routing. The router LLM also returns `crisis: bool`. Either one sets
`state["crisis"]`, which drives the 988 reply. Neither can clear it, and it
resets each turn. Recall is judged on `crisis_holdout.jsonl`, which an
independent agent wrote without seeing the lexicon.
**Why:** The old 988 message re-matched the gate's keywords, so even a correct
LLM escalation produced a generic transfer. A lexicon is predictable, offline,
and auditable, but it doesn't generalize: 1.00 on the dev set, 0.13 held-out.
An LLM generalizes but can fail or be unavailable. OR-ing them gives the
lexicon's floor plus the model's reach, and favors false alarms over misses.
**Trade-offs:** Informational mentions ("does sertraline cause suicidal
thoughts?") can trigger 988. The held-out false-alarm rate is 0.095, inside
the 0.10 bar. Mid-auth turns get the lexicon only (ADR-009). The held-out set
must never be tuned against; when it has been looked at too often, write a
new one.
**Amendment (2026-10-16, after the first live run):**
- On Claude Opus 5.5 via OpenRouter, held-out recall was 1.00. The run still failed, because `crisis_false_escalation_rate_holdout` was 0.286.
- Diagnosis: the LLM raised no false crisis flags. 2 of the 6 alarms were the lexicon cases above. The other 4 were frustrated members ("I give up, I've called six times") whom the router hands to a human by design, with no 988 message.
- The metric was counting every handoff to a human as a crisis false alarm. It is now split:
  - `crisis_false_alarm_rate` (988 shown on a benign message) stays gated at ≤ 0.10.
  - `benign_handoff_rate` is reported but not gated.
- The metric changed after we saw the results, so it's recorded here. The rule against tuning the prompt or the lexicon to the held-out set still holds. Nothing in either was changed.

## ADR-013: Standard FDE stack: FastAPI + Postgres + Next.js, Docker, AWS
**Decision:** The stack is Python + FastAPI + Pydantic for the backend,
TypeScript + React (Next.js) for the frontend, PostgreSQL as the system of
record, Docker for packaging, AWS for deployment, and pytest + GitHub Actions
for delivery.
- With `DATABASE_URL` set, Postgres holds three things:
  - LangGraph checkpoints (`PostgresSaver`)
  - a `sessions` table
  - a per-turn `turns` audit log with decision columns
- Without it, everything stays in memory.
- Claude is called through the official Anthropic SDK (`LLM_PROVIDER=anthropic`). The router's intent schema is enforced with structured outputs.
- The Streamlit demo is removed. The UI is a separate Next.js app (`web/`) that talks only to the API.

**Why:** This is the stack forward-deployed teams most often meet in customer environments, and each piece earns its place:
- **Postgres.** Workflow state and audit history are relational, and they have to survive restarts. A session now resumes mid-auth or mid-pagination after the API restarts. Escalation and containment become SQL queries instead of log scraping.
- **Next.js.** It puts the UI on the same contract a customer's own frontend team would build against (`/openapi.json`).
- **Structured outputs.** They remove the "model returned prose" failure from the one decision the LLM owns.

**Deferred until the workload asks for them:**
- **pgvector:** the compose and CI image already ship it, but there's no retrieval yet. It's the path for benefit-inquiry RAG and avoids a separate vector DB.
- **S3:** no file inputs yet. Prescription images and benefit PDFs would go here.
- **Redis, queues and workers:** turns are synchronous and around 1 ms of orchestration on mock. Add them for outbound refill reminders or batch evals.
- **pandas/Polars:** the audit analytics fit in SQL.

**Trade-offs:**
- The API still caches live sessions in process memory. Postgres is the source of truth; the cache is only a fast path.
- Horizontal scaling works because any replica can rehydrate a session from Postgres. Two replicas writing the same session at once isn't guarded, so use sticky sessions or a per-thread lock if that matters.
- Checkpoints and `turns.user_text` hold conversation content, which is PHI with real members. That means encryption at rest (RDS + KMS) and a retention window. Neither is implemented, because all data here is synthetic.

## ADR-014: Refunds: code computes, threshold decides, a person approves in plain text
**Decision:**
- The refund amount comes from order data. `owed = charges - plan price of what was filled`. That covers three cases: cancelled after the charge, a duplicate charge, and an overcharged copay.
- The LLM only recognizes that the member is asking for a refund.
- The member's "yes" processes refunds up to `AUTO_APPROVE_LIMIT` ($50) at once.
- Above the limit, the refund waits as `pending_approval`. A specialist decides with `POST /sessions/{id}/approval` and plain text: "approved", "denied - already reversed".
  - A regex reads the decision. There is no JSON payload and no LLM.
  - The agent then tells the member the outcome.
- Lost or damaged shipments go to a Member Support Specialist and aren't computed.

**Why:**
- The demo used to stall at the approval step, where someone had to paste a JSON resume payload. A plain "approved" is what a pharmacy-support approver would actually type.
- Money is the "code decides truth" boundary (ADR-002), so no model output can propose, edit or approve an amount.
- A threshold keeps the common case (small copay errors) self-service and puts human review where the dollars are.
- Lost and damaged claims need judgment the order data can't supply: reship or refund, fraud signals, controlled-drug rules.

**Guardrail:** the approval path writes to the thread directly (`graph.update_state(..., as_node="refund")`) and never goes through the router. A member typing "approved" in chat lands in the router like any other message and cannot approve anything. Tests cover this. The approver's note is stored with the refund for audit but never shown to the member. Approver turns are prefixed `[approver] ` in the transcript and turn log.

**Not LangGraph `interrupt()`:** an interrupt suspends the member's thread until someone resumes it with `Command(resume=...)`. The member couldn't keep talking while a refund waits, and resuming means passing a structured payload, which is the original pain point. A status field in state lets the conversation continue and lets any channel (the console now, a queue later) decide.

**Trade-offs:**
- The approval endpoint has no staff auth, because this is a demo console. In production it would sit behind staff SSO and log the approver's identity.
- "Processed" means recorded in state. The payment reversal itself is stubbed, just like the web deep links.
- $50 is a per-client setting, not a universal number.
