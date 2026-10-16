import type {
  AgentTurnResult, EvalRun, EvalSummary, Health, ScenarioInfo, SessionCreate, SessionCreated,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "content-type": "application/json" },
  });
  if (!res.ok) {
    // Show the API's own message (e.g. the demo's turn limit) when it sends one.
    const detail: unknown = await res.json().then((b) => b?.detail, () => null);
    throw new ApiError(res.status, typeof detail === "string" ? detail : `${init?.method ?? "GET"} ${path} failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  scenarios: () => request<ScenarioInfo[]>("/scenarios"),
  createSession: (body: SessionCreate) =>
    request<SessionCreated>("/sessions", { method: "POST", body: JSON.stringify(body) }),
  send: (sessionId: string, text: string) =>
    request<AgentTurnResult>(`/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  // Specialist decision in plain text: "approved", "denied - reason".
  approve: (sessionId: string, text: string) =>
    request<AgentTurnResult>(`/sessions/${sessionId}/approval`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  evals: () => request<EvalSummary[]>("/evals"),
  latestEval: () => request<EvalRun>("/evals/latest"),
};
