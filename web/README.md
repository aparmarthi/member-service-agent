# Web: operator console + eval dashboard

Next.js (App Router), React, TypeScript, Tailwind. A client of the FastAPI service only. Order status, eligibility, prices, auth, and crisis detection all come from the API. Nothing is re-derived here.

| Route | What it shows |
|---|---|
| `/` | Member console: scenario, channel (chat/voice), and auth controls; chat with order cards and quick replies; 988 banner; specialist handoff; per-turn decision inspector |
| `/evals` | Latest scorecard against ship gates, metric history, and failing cases by suite |

## Run

```bash
# API first, from the repo root
uvicorn src.serving.app:app --port 8000

# then here
npm install
npm run dev            # http://localhost:3000
```

`NEXT_PUBLIC_API_URL` (default `http://localhost:8000`) is inlined at **build** time. In Docker, pass it as a build arg:

```bash
docker build -t pbm-web --build-arg NEXT_PUBLIC_API_URL=https://api.example.com .
```

## Checks (same as CI)

```bash
npm run lint && npm run typecheck && npm run build
```

## Layout

- `lib/types.ts`: TypeScript mirror of the API contract (`docs/openapi.json`). Update it when `src/serving/app.py` changes.
- `lib/api.ts`: typed fetch client. `ApiError.status` drives the "Session expired" state on 404.
- `components/console.tsx`: session lifecycle and chat state.
- `components/message.tsx`: when a turn has `shown` orders, swaps the reply's `• ` lines for `OrderCard`s.
- `components/evals-dashboard.tsx`: scorecard, history chart (Recharts), and failures table.
