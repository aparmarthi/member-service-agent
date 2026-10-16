"use client";

import { useEffect, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import type { EvalRun, EvalSummary } from "@/lib/types";
import { Badge, Card, SectionLabel } from "./ui";

const TRENDED = [
  { key: "crisis_recall_holdout", color: "#dc2626" },
  { key: "routing_accuracy", color: "#2563eb" },
  { key: "task_completion_rate", color: "#16a34a" },
];

function fmt(metric: string, value: number): string {
  return metric.endsWith("_ms") ? `${value.toFixed(1)} ms` : `${(value * 100).toFixed(1)}%`;
}

function fmtDelta(metric: string, delta: number): string {
  const sign = delta > 0 ? "+" : "";
  return metric.endsWith("_ms") ? `${sign}${delta.toFixed(1)} ms` : `${sign}${(delta * 100).toFixed(1)} pts`;
}

export default function EvalsDashboard() {
  const [runs, setRuns] = useState<EvalSummary[] | null>(null);
  const [latest, setLatest] = useState<EvalRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [suite, setSuite] = useState("all");

  useEffect(() => {
    Promise.all([api.evals(), api.latestEval()]).then(
      ([r, l]) => { setRuns(r); setLatest(l); },
      () => setError("No eval runs available. Run `python -m evals.run` and make sure the API is up."),
    );
  }, []);

  if (error) return <p className="p-8 text-center text-sm text-slate-500">{error}</p>;
  if (!runs || !latest) return <p className="p-8 text-center text-sm text-slate-400">Loading evals…</p>;

  const previous = runs[1];
  const history = [...runs].reverse().map((r) => ({ timestamp: r.timestamp.replace("T", " "), ...r.metrics }));
  const suites = [...new Set(latest.failures.map((f) => f.suite))];
  const failures = latest.failures.filter((f) => suite === "all" || f.suite === suite);

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-lg font-semibold">Latest run · {latest.timestamp.replace("T", " ")}</h1>
        <Badge tone={latest.passed ? "green" : "red"}>{latest.passed ? "ALL GATES PASS" : "GATES FAILING"}</Badge>
        <Badge
          tone={latest.provider === "mock" ? "amber" : "blue"}
          title={latest.provider === "mock" ? "Mock runs use a keyword router; routing and holdout crisis recall need a live-model run." : undefined}
        >
          provider: {latest.provider}
        </Badge>
      </div>

      <section aria-label="Scorecard" className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
        {Object.entries(latest.metrics).map(([name, value]) => {
          const gate = latest.thresholds[name];
          const prev = previous?.metrics[name];
          return (
            <Card key={name} className="space-y-1">
              <p className="truncate text-xs text-slate-500 dark:text-slate-400" title={name}>{name}</p>
              <p className="text-2xl font-semibold tabular-nums">{fmt(name, value)}</p>
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                {gate ? (
                  <>
                    <Badge tone={gate.passed ? "green" : "red"}>{gate.passed ? "PASS" : "FAIL"}</Badge>
                    <span className="text-slate-500">{gate.op} {fmt(name, gate.value)}</span>
                  </>
                ) : <span className="text-slate-400">tracked</span>}
                {prev !== undefined && prev !== value && (
                  <span className="text-slate-500">Δ {fmtDelta(name, value - prev)}</span>
                )}
              </div>
            </Card>
          );
        })}
      </section>

      <Card>
        <SectionLabel>History</SectionLabel>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history}>
              <CartesianGrid strokeDasharray="3 3" stroke="#94a3b8" strokeOpacity={0.3} />
              <XAxis dataKey="timestamp" fontSize={11} />
              <YAxis domain={[0, 1]} tickFormatter={(v: number) => `${v * 100}%`} fontSize={11} />
              <Tooltip formatter={(v) => (typeof v === "number" ? `${(v * 100).toFixed(1)}%` : v)} />
              <Legend />
              {TRENDED.map((m) => <Line key={m.key} dataKey={m.key} stroke={m.color} strokeWidth={2} dot />)}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card>
        <div className="mb-3 flex items-center justify-between">
          <SectionLabel>Failing cases ({failures.length})</SectionLabel>
          <select
            aria-label="Filter by suite"
            value={suite}
            onChange={(e) => setSuite(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-950"
          >
            <option value="all">All suites</option>
            {suites.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-slate-500 dark:text-slate-400">
              <tr><th className="py-2 pr-4">Suite</th><th className="py-2 pr-4">Input</th><th className="py-2 pr-4">Expected</th><th className="py-2">Got</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
              {failures.map((f, i) => (
                <tr key={i}>
                  <td className="py-2 pr-4"><Badge tone="gray">{f.suite}</Badge></td>
                  <td className="py-2 pr-4">{f.text ?? "—"}</td>
                  <td className="py-2 pr-4 font-mono text-xs">{f.expected ?? "—"}</td>
                  <td className="py-2 font-mono text-xs">{f.got ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
