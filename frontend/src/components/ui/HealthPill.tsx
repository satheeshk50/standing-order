"use client";

import { useHealth } from "@/lib/hooks";

/** Shows at a glance whether the demo is running on a live model or the
 *  deterministic mock policy — the single most confusing thing to a reviewer
 *  if it isn't stated. */
export function HealthPill() {
  const { data, error } = useHealth();

  if (error) {
    return (
      <span className="rounded border border-red-800 bg-red-900/50 px-2 py-1 text-xs text-red-300">
        API unreachable
      </span>
    );
  }
  if (!data) {
    return <span className="text-xs text-slate-600">checking…</span>;
  }

  const ok = data.status === "ok";
  const live = data.llm.mode === "live";

  return (
    <div className="flex items-center gap-2 text-xs">
      <span
        className={`rounded border px-2 py-1 ${
          ok
            ? "border-emerald-800 bg-emerald-900/40 text-emerald-300"
            : "border-amber-800 bg-amber-900/40 text-amber-300"
        }`}
        title={Object.entries(data.checks)
          .map(([k, v]) => `${k}: ${v}`)
          .join("\n")}
      >
        {ok ? "healthy" : "degraded"}
      </span>
      <span
        className={`rounded border px-2 py-1 ${
          live
            ? "border-sky-800 bg-sky-900/40 text-sky-300"
            : "border-edge bg-slate-800 text-slate-400"
        }`}
        title={
          live
            ? `agent: ${data.llm.agent_model}\nclassifier: ${data.llm.classifier_model}`
            : "No ANTHROPIC_API_KEY set — running the deterministic policy."
        }
      >
        {live ? `LLM live · ${data.llm.agent_model}` : "LLM mock mode"}
      </span>
    </div>
  );
}
