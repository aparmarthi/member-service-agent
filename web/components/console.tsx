"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "@/lib/api";
import type { AgentTurnResult, Channel, RefundRequest, ScenarioInfo, SessionCreate } from "@/lib/types";
import Inspector, { type InspectedTurn } from "./inspector";
import Message, { type ChatMessage } from "./message";
import { Badge, Button, Card, SectionLabel, Segmented, Switch } from "./ui";

const QUICK_REPLIES: Record<string, string[]> = {
  more_orders: ["See more", "No thanks"],
  more_refills: ["See more", "No thanks"],
  extended_lookback: ["Yes, check 6 months", "No thanks"],
  connect_agent: ["Yes, connect me", "No thanks"],
  check_refill: ["Yes", "No"],
  add_to_cart: ["Yes", "No"],
  pa_cost: ["Yes, what's the cost?", "No thanks"],
  refund: ["Yes, process it", "No thanks"],
};

export default function Console() {
  const [scenarios, setScenarios] = useState<ScenarioInfo[]>([]);
  const [config, setConfig] = useState<SessionCreate | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [turns, setTurns] = useState<InspectedTurn[]>([]);
  const [crisis, setCrisis] = useState(false);
  const [sending, setSending] = useState(false);
  const [expired, setExpired] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [speak, setSpeak] = useState(false);
  const [input, setInput] = useState("");
  const logRef = useRef<HTMLDivElement>(null);

  async function start(next: SessionCreate) {
    setConfig(next);
    try {
      const s = await api.createSession(next);
      setSessionId(s.session_id);
      setMessages([]);
      setTurns([]);
      setCrisis(false);
      setExpired(false);
      setError(null);
    } catch {
      setError("Could not start a session. Is the API running?");
    }
  }

  useEffect(() => {
    api.scenarios().then(
      (list) => {
        setScenarios(list);
        if (list.length) void start({ scenario: list[0].name, channel: "chat", verified: true });
      },
      () => setError("Could not reach the API. Start it with: uvicorn src.serving.app:app --port 8000"),
    );
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(id);
  }, [toast]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || !sessionId || sending) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: trimmed }]);
    setSending(true);
    try {
      const result = await api.send(sessionId, trimmed);
      onResult(trimmed, result);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setExpired(true);
      else setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setSending(false);
    }
  }

  async function approve(text: string) {
    const trimmed = text.trim();
    if (!trimmed || !sessionId || sending) return;
    setSending(true);
    try {
      const result = await api.approve(sessionId, trimmed);
      setMessages((m) => [...m, { role: "system", text: `Specialist: “${trimmed}”` }]);
      onResult(`[approver] ${trimmed}`, result);
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 422) setError("Approver reply must start with “approved” or “denied”.");
      else if (e instanceof ApiError && e.status === 409) setError("No refund is waiting for approval.");
      else setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setSending(false);
    }
  }

  function onResult(user: string, result: AgentTurnResult) {
    const added: ChatMessage[] = [{ role: "agent", result }];
    if (result.escalated && result.handoff_target === "live_agent") {
      added.push({ role: "system", text: "Connecting you with a Member Support Specialist…" });
    }
    setMessages((m) => [...m, ...added]);
    setTurns((t) => [...t, { user, result }]);
    if (result.crisis) setCrisis(true);
    if (speak && config?.channel === "voice" && "speechSynthesis" in window) {
      window.speechSynthesis.speak(new SpeechSynthesisUtterance(result.reply));
    }
  }

  const last = turns.at(-1)?.result;
  const escalated = last?.escalated === true && last.handoff_target === "live_agent";
  const pendingAuth = last?.handoff_target === "pending_auth";
  const chips = last?.offer && !escalated ? QUICK_REPLIES[last.offer] ?? [] : [];
  const scenario = scenarios.find((s) => s.name === config?.scenario);
  // Latest refund on the thread; later non-refund turns don't carry it.
  const refund = turns.findLast((t) => t.result.refund)?.result.refund;
  const blocked = !sessionId || escalated || expired;

  return (
    <div className="mx-auto grid w-full max-w-7xl flex-1 gap-4 p-4 lg:grid-cols-[280px_1fr_320px]">
      <aside className="space-y-4">
        <Card className="space-y-4">
          <div>
            <SectionLabel>Scenario</SectionLabel>
            <select
              aria-label="Scenario"
              value={config?.scenario ?? ""}
              onChange={(e) => config && start({ ...config, scenario: e.target.value })}
              className="w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950"
            >
              {scenarios.map((s) => <option key={s.name} value={s.name}>{s.name.replaceAll("_", " ")}</option>)}
            </select>
            {scenario && (
              <div className="mt-2 space-y-1 text-xs text-slate-500 dark:text-slate-400">
                <p>{scenario.summary}</p>
                <p>Patients: {scenario.patients.join(", ")}</p>
              </div>
            )}
          </div>
          <div>
            <SectionLabel>Channel</SectionLabel>
            <Segmented<Channel>
              label="Channel"
              value={config?.channel ?? "chat"}
              options={[{ value: "chat", label: "Chat" }, { value: "voice", label: "Voice" }]}
              onChange={(channel) => config && start({ ...config, channel })}
            />
          </div>
          <Switch
            label="Already authenticated"
            checked={config?.verified ?? true}
            onChange={(verified) => config && start({ ...config, verified })}
          />
          <Button variant="outline" className="w-full" onClick={() => config && start(config)}>
            New conversation
          </Button>
        </Card>
        {config && !config.verified && scenario && <Credentials scenario={scenario} onCopy={setToast} />}
        {refund?.status === "pending_approval" && <Approval refund={refund} busy={sending} onDecide={approve} />}
      </aside>

      <Card className="flex min-h-[70vh] flex-col p-0">
        {crisis && (
          <div role="alert" className="rounded-t-xl border-b border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
            <strong>988 Suicide &amp; Crisis Lifeline</strong> — call or text{" "}
            <a href="tel:988" className="font-semibold underline">988</a>
          </div>
        )}
        {config?.channel === "voice" && (
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-2 dark:border-slate-800">
            <Badge tone="violet">Voice simulation</Badge>
            <Switch label="Read replies aloud" checked={speak} onChange={setSpeak} />
          </div>
        )}
        <div ref={logRef} role="log" aria-live="polite" className="flex-1 space-y-3 overflow-y-auto p-4">
          {messages.length === 0 && !error && (
            <p className="text-center text-sm text-slate-400">Try “where is my order?”, “refill my meds”, “how much is atorvastatin?”, or “I want a refund”</p>
          )}
          {messages.map((m, i) => <Message key={i} message={m} onCta={(cta) => setToast(`Deep link (stubbed): ${cta}`)} />)}
          {sending && <Typing />}
          {error && <p className="text-center text-sm text-red-600 dark:text-red-400">{error}</p>}
          {expired && (
            <div className="flex flex-col items-center gap-2 text-sm">
              <p className="text-slate-500">Session expired.</p>
              <Button onClick={() => config && start(config)}>Restart</Button>
            </div>
          )}
          {escalated && (
            <div className="flex justify-center">
              <Button onClick={() => config && start(config)}>Start new conversation</Button>
            </div>
          )}
        </div>
        <div className="space-y-2 border-t border-slate-200 p-3 dark:border-slate-800">
          {(chips.length > 0 || pendingAuth) && (
            <div className="flex flex-wrap items-center gap-2">
              {pendingAuth && <Badge tone="amber">🔒 Verifying identity</Badge>}
              {chips.map((c) => (
                <Button key={c} variant="outline" className="rounded-full" disabled={sending} onClick={() => send(c)}>{c}</Button>
              ))}
            </div>
          )}
          <form onSubmit={(e) => { e.preventDefault(); void send(input); }} className="flex gap-2">
            <input
              aria-label="Message"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={blocked}
              maxLength={2000}
              placeholder={escalated ? "Handed off to a specialist" : last?.offer === "drug_name" ? "Type a medication name" : "Type a message"}
              className="flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm disabled:opacity-60 dark:border-slate-700 dark:bg-slate-950"
            />
            <Button type="submit" disabled={blocked || sending || !input.trim()}>Send</Button>
          </form>
        </div>
      </Card>

      <Inspector turns={turns} />

      {toast && (
        <div role="status" className="fixed bottom-4 left-1/2 -translate-x-1/2 rounded-lg bg-slate-900 px-4 py-2 text-sm text-white shadow-lg dark:bg-slate-100 dark:text-slate-900">
          {toast}
        </div>
      )}
    </div>
  );
}

function Credentials({ scenario, onCopy }: { scenario: ScenarioInfo; onCopy: (msg: string) => void }) {
  const rows = [["Member ID", scenario.member_id], ["Date of birth", scenario.dob]];
  return (
    <Card>
      <SectionLabel>Test credentials</SectionLabel>
      <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">Synthetic — for testing step-up auth</p>
      <dl className="space-y-1.5 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-2">
            <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
            <dd className="flex items-center gap-1 font-mono">
              {value}
              <Button
                variant="ghost"
                aria-label={`Copy ${label}`}
                onClick={() => navigator.clipboard.writeText(value).then(() => onCopy(`${label} copied`))}
              >
                ⧉
              </Button>
            </dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

function Approval({ refund, busy, onDecide }: {
  refund: RefundRequest; busy: boolean; onDecide: (text: string) => void;
}) {
  const [text, setText] = useState("");
  return (
    <Card className="space-y-3 border-amber-300 dark:border-amber-800">
      <div>
        <SectionLabel>Specialist approval</SectionLabel>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Staff view. ${refund.total.toFixed(2)} · <span className="font-mono">{refund.reference}</span> is over
          the auto-approve limit. Type a decision in plain text; the agent tells the member.
        </p>
      </div>
      <div className="flex gap-2">
        <Button className="flex-1" disabled={busy} onClick={() => onDecide("approved")}>Approve</Button>
        <Button variant="outline" className="flex-1" disabled={busy} onClick={() => onDecide("denied")}>Deny</Button>
      </div>
      <form onSubmit={(e) => { e.preventDefault(); onDecide(text); setText(""); }} className="flex gap-2">
        <input
          aria-label="Approver decision"
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={200}
          placeholder="approved — verified against claim"
          className="flex-1 rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-950"
        />
        <Button type="submit" variant="outline" disabled={busy || !text.trim()}>Send</Button>
      </form>
    </Card>
  );
}

function Typing() {
  return (
    <div className="flex gap-1 px-3 py-2" aria-label="Agent is typing">
      {[0, 150, 300].map((d) => (
        <span key={d} className="h-2 w-2 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: `${d}ms` }} />
      ))}
    </div>
  );
}
