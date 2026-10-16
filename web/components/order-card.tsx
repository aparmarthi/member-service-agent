import type { ResolvedStatus } from "@/lib/types";
import { Badge, Button, type Tone } from "./ui";

const STATUS_TONE: Record<string, Tone> = {
  Delayed: "amber",
  "We're working on it": "slate",
  Shipped: "blue",
  Delivered: "green",
  "Not filled": "gray",
};

export default function OrderCard({ order, onCta }: { order: ResolvedStatus; onCta: (cta: string) => void }) {
  const cta = order.primary_cta;
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-3 text-sm dark:border-slate-700 dark:bg-slate-950">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-medium">{order.drug_name}</p>
          <p className="text-xs text-slate-500 dark:text-slate-400">for {order.patient_name}</p>
        </div>
        <Badge tone={STATUS_TONE[order.parent_status] ?? "slate"}>{order.parent_status}</Badge>
      </div>
      <p className="mt-2">
        <span className="font-medium">{order.status}</span>
        {order.sub_status && <span className="text-slate-600 dark:text-slate-300"> · {order.sub_status}</span>}
      </p>
      <p className="mt-1 flex flex-wrap gap-x-4 text-xs text-slate-500 dark:text-slate-400">
        <span>Order <span className="font-mono">{order.order_number}</span></span>
        {order.price != null && <span>Price ${order.price.toFixed(2)}</span>}
        {order.tracking_id && <span>Tracking <span className="font-mono">{order.tracking_id}</span></span>}
      </p>
      {(cta || order.escalate) && (
        <div className="mt-3 flex items-center gap-2">
          {cta && <Button variant="outline" onClick={() => onCta(cta)}>{cta}</Button>}
          {order.escalate && <Badge tone="violet">Escalates to specialist</Badge>}
        </div>
      )}
    </article>
  );
}
