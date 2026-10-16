import type { AgentTurnResult } from "@/lib/types";
import { Badge, Card, SectionLabel } from "./ui";

export interface InspectedTurn { user: string; result: AgentTurnResult }

export default function Inspector({ turns }: { turns: InspectedTurn[] }) {
  return (
    <Card className="flex min-h-0 flex-col">
      <SectionLabel>Decision inspector</SectionLabel>
      <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
        The LLM picks the intent; deterministic code decides every fact shown.
      </p>
      {turns.length === 0 && <p className="text-sm text-slate-400">No turns yet.</p>}
      <ol className="space-y-3 overflow-y-auto">
        {turns.map((t, i) => ({ t, i })).reverse().map(({ t, i }) => (
          <li key={i} className="border-l-2 border-slate-200 pl-3 dark:border-slate-700">
            <p className="truncate text-xs text-slate-500 dark:text-slate-400" title={t.user}>
              Turn {i + 1}: “{t.user}”
            </p>
            <div className="mt-1 flex flex-wrap gap-1">
              <Badge tone="blue">intent: {t.result.intent}</Badge>
              {t.result.escalated && <Badge tone="violet">escalated</Badge>}
              {t.result.handoff_target && <Badge tone="slate">handoff: {t.result.handoff_target}</Badge>}
              {t.result.crisis && <Badge tone="red">crisis</Badge>}
              {t.result.offer && <Badge tone="amber">offer: {t.result.offer}</Badge>}
              {t.result.refund && <Badge tone="green">refund: {t.result.refund.status}</Badge>}
              {t.result.shown.length > 0 && <Badge tone="gray">{t.result.shown.length} cards</Badge>}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}
