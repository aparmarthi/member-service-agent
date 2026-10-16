# CLAUDE.md: pbm-member-agent

This repo follows the FDE default stack. It overrides the global "Streamlit for UI" rule here.

| Layer | Use | Notes |
|---|---|---|
| Backend | Python, FastAPI, Pydantic, LangGraph | All business logic lives here. |
| Frontend | TypeScript, React, Next.js in `web/` | A client of the API only; `web/lib/types.ts` mirrors the contract. UX spec: docs/BOLT_PROMPT.md. No Streamlit. |
| Database | PostgreSQL via psycopg 3 (`src/serving/store.py`) | Workflow state (LangGraph `PostgresSaver`), sessions, turn audit log. |
| Vector search | pgvector, in the same Postgres | Only when retrieval exists. No separate vector DB. |
| Files | S3 | Only when there are file inputs. |
| AI | Official model SDKs (Anthropic Python SDK) | Structured outputs for anything the code parses. The mock provider stays the default for tests. |
| Data processing | SQL first, then pandas or Polars | |
| Deployment | Docker, AWS (ECR, ECS Fargate, RDS, Secrets Manager) | docs/DEPLOY.md |
| Testing and delivery | pytest, GitHub Actions | CI runs pytest against a Postgres service and builds and smoke-tests the image. |
| Redis, queues, workers | Not yet | Add when jobs, caching or load need them. Record an ADR. |

## Rules
- Design principle: LLM decides intent; code decides truth (ADR-002).
- `DATABASE_URL` unset means in-memory, so tests stay hermetic. Postgres-only tests skip without it.
- Never tune the crisis lexicon or the router prompt against `evals/datasets/crisis_holdout.jsonl`.
- Synthetic data only. Treat checkpoints and `turns.user_text` as PHI-bearing in any real deployment.
- Record stack changes in docs/decisions.md.

## Commands
```bash
pytest -q
python -m evals.run            # LLM_PROVIDER=anthropic for the live ship gate
python -m scripts.demo
uvicorn src.serving.app:app --reload --port 8000
docker compose up --build      # + --profile web for the console on :3000
cd web && npm run dev          # console against a local API
cd web && npm run lint && npm run typecheck && npm run build
```
