import type { Metadata } from "next";
import EvalsDashboard from "@/components/evals-dashboard";

export const metadata: Metadata = { title: "Evals · PBM Member Agent" };

export default function EvalsPage() {
  return <EvalsDashboard />;
}
