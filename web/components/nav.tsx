"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Health } from "@/lib/types";
import { Badge } from "./ui";

const LINKS = [
  { href: "/", label: "Console" },
  { href: "/evals", label: "Evals" },
];

export default function Nav() {
  const pathname = usePathname();
  const [health, setHealth] = useState<Health | null | "down">(null);

  useEffect(() => {
    const check = () => api.health().then(setHealth, () => setHealth("down"));
    check();
    const id = setInterval(check, 15000);
    return () => clearInterval(id);
  }, []);

  const up = health !== null && health !== "down";
  return (
    <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <nav className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
        <span className="font-semibold">PBM Member Agent</span>
        <div className="flex gap-1">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              aria-current={pathname === l.href ? "page" : undefined}
              className={`rounded-md px-3 py-1.5 text-sm font-medium focus-visible:outline-2 focus-visible:outline-blue-500 ${pathname === l.href ? "bg-slate-100 dark:bg-slate-800" : "text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"}`}
            >
              {l.label}
            </Link>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-3">
          <Badge tone="green">Synthetic data · no PHI</Badge>
          <span className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400" aria-live="polite">
            <span className={`h-2 w-2 rounded-full ${up ? "bg-green-500" : health === "down" ? "bg-red-500" : "bg-slate-400"}`} />
            {up ? `${health.provider} · ${health.storage}` : health === "down" ? "API unreachable" : "checking…"}
          </span>
        </div>
      </nav>
    </header>
  );
}
