import type { RefundRequest } from "@/lib/types";
import { Badge, type Tone } from "./ui";

const STATUS: Record<RefundRequest["status"], { label: string; tone: Tone }> = {
  offered: { label: "Ready to process", tone: "slate" },
  approved: { label: "Approved", tone: "green" },
  pending_approval: { label: "Awaiting specialist", tone: "amber" },
  denied: { label: "Not approved", tone: "gray" },
};

const REASON: Record<RefundRequest["lines"][number]["reason"], string> = {
  cancelled: "Cancelled after charge",
  duplicate: "Charged twice",
  overcharge: "Over plan price",
};

export default function RefundCard({ refund }: { refund: RefundRequest }) {
  const status = STATUS[refund.status];
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-3 text-sm dark:border-slate-700 dark:bg-slate-950">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-medium">Refund ${refund.total.toFixed(2)}</p>
          <p className="font-mono text-xs text-slate-500 dark:text-slate-400">{refund.reference}</p>
        </div>
        <Badge tone={status.tone}>{status.label}</Badge>
      </div>
      <ul className="mt-2 space-y-1">
        {refund.lines.map((l) => (
          <li key={l.order_number} className="flex justify-between gap-2 text-xs">
            <span>
              {l.drug_name} <span className="text-slate-500 dark:text-slate-400">· {REASON[l.reason]}</span>
            </span>
            <span className="font-medium">${l.amount.toFixed(2)}</span>
          </li>
        ))}
      </ul>
    </article>
  );
}
