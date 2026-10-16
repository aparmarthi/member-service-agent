"""FastAPI service — the agent behind a session-based HTTP API.

Endpoints:
    GET  /health                         liveness + active LLM provider
    GET  /scenarios                      synthetic member scenarios (+ test credentials)
    POST /sessions                       start a conversation → session_id
    GET  /sessions/{session_id}          session config + transcript
    POST /sessions/{session_id}/messages send one member turn → AgentTurnResult
    GET  /evals                          saved eval runs, newest first (summary)
    GET  /evals/latest                   most recent eval run, with failing cases

The OpenAPI contract at ``/openapi.json`` is what a frontend builds against.
CORS origins come from ``CORS_ORIGINS`` (comma-separated, default ``*``). That
default is safe only because every member here is synthetic.

Run:
    uvicorn src.serving.app:app --reload --port 8000

Sessions live in process memory (see ``session.py``); a deployment would back
them with a persistent checkpointer and expire idle threads.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.data import synthetic
from src.models.schemas import AgentTurnResult, Channel
from src.serving.session import AgentSession

app = FastAPI(title="PBM Member Agent", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["content-type"],
)
_sessions: dict[str, AgentSession] = {}
_RESULTS = Path(__file__).resolve().parents[2] / "evals" / "results"


class HealthResponse(BaseModel):
    """Liveness payload."""

    status: str
    provider: str


class ScenarioInfo(BaseModel):
    """A synthetic member a session can load."""

    name: str
    summary: str
    patients: list[str]
    member_id: str = Field(description="Synthetic test credential for unverified sessions.")
    dob: str = Field(description="Synthetic test credential (account holder's DOB).")


class SessionCreate(BaseModel):
    """Request to start a conversation."""

    scenario: str = "single_patient_mixed_statuses"
    channel: Channel = Channel.CHAT
    verified: bool = Field(default=True, description="False exercises step-up auth.")


class SessionCreated(BaseModel):
    """A started conversation."""

    session_id: str
    scenario: str
    channel: Channel
    verified: bool


class Turn(BaseModel):
    """One member message and the agent's structured response."""

    user: str
    result: AgentTurnResult


class SessionDetail(SessionCreated):
    """A conversation's config and transcript (for rehydrating a UI)."""

    turns: list[Turn]


class EvalSummary(BaseModel):
    """One saved eval run."""

    timestamp: str
    provider: str
    passed: bool
    metrics: dict[str, float]
    thresholds: dict[str, dict]


class EvalRun(EvalSummary):
    """One saved eval run including its failing cases."""

    failures: list[dict]


class MessageIn(BaseModel):
    """One member utterance."""

    text: str = Field(min_length=1, max_length=2000)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check."""
    return HealthResponse(status="ok", provider=os.getenv("LLM_PROVIDER", "mock"))


@app.get("/scenarios", response_model=list[ScenarioInfo])
def scenarios() -> list[ScenarioInfo]:
    """List synthetic member scenarios, with test credentials for step-up auth."""
    out = []
    for name in sorted(synthetic.SCENARIOS):
        member = synthetic.build(name)
        doc = synthetic.SCENARIOS[name].__doc__ or ""
        out.append(ScenarioInfo(
            name=name, summary=doc.strip().splitlines()[0] if doc else name,
            patients=[f"{p.first_name} {p.last_name}" for p in member.patients],
            member_id=member.member_id, dob=member.patients[0].dob))
    return out


@app.post("/sessions", response_model=SessionCreated, status_code=201)
def create_session(body: SessionCreate) -> SessionCreated:
    """Start a conversation for a synthetic member."""
    if body.scenario not in synthetic.SCENARIOS:
        raise HTTPException(status_code=422, detail=f"Unknown scenario {body.scenario!r}")
    session = AgentSession(body.scenario, body.channel, verified=body.verified)
    _sessions[session.thread_id] = session
    return SessionCreated(session_id=session.thread_id, scenario=body.scenario,
                          channel=body.channel, verified=body.verified)


def _session(session_id: str) -> AgentSession:
    session = _sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    return session


@app.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: str) -> SessionDetail:
    """Return a conversation's config and full transcript."""
    s = _session(session_id)
    return SessionDetail(session_id=s.thread_id, scenario=s.scenario, channel=s.channel,
                         verified=s.verified,
                         turns=[Turn(user=u, result=r) for u, r in s.turns])


@app.post("/sessions/{session_id}/messages", response_model=AgentTurnResult)
def send_message(session_id: str, body: MessageIn) -> AgentTurnResult:
    """Send one member turn and return the agent's reply and decisions."""
    return _session(session_id).send(body.text)


def _eval_runs() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(_RESULTS.glob("*.json"), reverse=True)]


@app.get("/evals", response_model=list[EvalSummary])
def evals() -> list[EvalSummary]:
    """List saved eval runs, newest first, without per-case failures."""
    return [EvalSummary(**run) for run in _eval_runs()]


@app.get("/evals/latest", response_model=EvalRun)
def latest_eval() -> EvalRun:
    """Return the most recent eval run, including failing cases."""
    runs = _eval_runs()
    if not runs:
        raise HTTPException(status_code=404, detail="No eval runs saved; run python -m evals.run")
    return EvalRun(**runs[0])
