import type { AgentTurnResult } from "@/lib/types";
import OrderCard from "./order-card";
import RefundCard from "./refund-card";

export type ChatMessage =
  | { role: "user"; text: string }
  | { role: "agent"; result: AgentTurnResult }
  | { role: "system"; text: string };

const BULLET = "• ";

/** Replace the reply's bullet lines with cards when the turn carries structured orders or a refund. */
function AgentBody({ result, onCta }: { result: AgentTurnResult; onCta: (cta: string) => void }) {
  const lines = result.reply.split("\n");
  if (result.shown.length === 0 && !result.refund) return <p className="whitespace-pre-line">{result.reply}</p>;
  const found = lines.findIndex((l) => l.startsWith(BULLET));
  const first = found === -1 ? lines.length : found; // no bullets: all text, then the card
  const before = lines.slice(0, first).join("\n").trim();
  const after = lines.slice(first).filter((l) => !l.startsWith(BULLET)).join("\n").trim();
  return (
    <div className="space-y-2">
      {before && <p className="whitespace-pre-line">{before}</p>}
      <div className="space-y-2">
        {result.shown.map((o, i) => <OrderCard key={`${o.order_number}-${i}`} order={o} onCta={onCta} />)}
        {result.refund && <RefundCard refund={result.refund} />}
      </div>
      {after && <p className="whitespace-pre-line">{after}</p>}
    </div>
  );
}

export default function Message({ message, onCta }: { message: ChatMessage; onCta: (cta: string) => void }) {
  if (message.role === "system") {
    return <p className="text-center text-xs text-slate-500 dark:text-slate-400">{message.text}</p>;
  }
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[80%] whitespace-pre-line rounded-2xl rounded-br-sm bg-blue-600 px-3 py-2 text-sm text-white">
          {message.text}
        </p>
      </div>
    );
  }
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl rounded-bl-sm bg-slate-100 px-3 py-2 text-sm dark:bg-slate-800">
        <AgentBody result={message.result} onCta={onCta} />
      </div>
    </div>
  );
}
