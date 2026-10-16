import type { Metadata } from "next";
import EvalsDashboard from "@/components/evals-dashboard";

export const metadata: Metadata = { title: "Evals · Member Service Agent" };

export default function EvalsPage() {
  return <EvalsDashboard />;
}
