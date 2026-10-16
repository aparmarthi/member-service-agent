// Mirrors the FastAPI contract (src/serving/app.py, docs/openapi.json).

export type Channel = "chat" | "voice";
export type Intent =
  | "order_status" | "order_action" | "refill" | "drug_price"
  | "escalation" | "closing" | "off_topic";

export interface Health { status: string; provider: string; storage: string }

export interface ScenarioInfo {
  name: string;
  summary: string;
  patients: string[];
  member_id: string; // synthetic test credential
  dob: string; // synthetic test credential
}

export interface SessionCreate { scenario: string; channel: Channel; verified: boolean }
export interface SessionCreated extends SessionCreate { session_id: string }

export interface ResolvedStatus {
  patient_name: string;
  drug_name: string;
  status: string;
  sub_status: string;
  parent_status: string;
  order_number: string;
  priority: number;
  self_serve: string[];
  primary_cta: string | null;
  escalate: boolean;
  go_to_refill: boolean;
  tracking_id: string | null;
  price: number | null;
}

export interface AgentTurnResult {
  reply: string;
  intent: Intent;
  escalated: boolean;
  handoff_target: string | null;
  shown: ResolvedStatus[];
  has_more: boolean;
  crisis: boolean;
  offer: string | null;
}

export interface Threshold { op: string; value: number; passed: boolean }
export interface EvalSummary {
  timestamp: string;
  provider: string;
  passed: boolean;
  metrics: Record<string, number>;
  thresholds: Record<string, Threshold>;
}
export interface EvalFailure { suite: string; text?: string; expected?: string; got?: string }
export interface EvalRun extends EvalSummary { failures: EvalFailure[] }
