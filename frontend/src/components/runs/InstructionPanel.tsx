"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import type { RunDetail } from "@/lib/types";
import { isTerminal } from "@/lib/types";

const PRESETS = [
  "For this order, prioritize speed over cost.",
  "If shipment is delayed, escalate immediately.",
  "Do not contact the customer without human review.",
  "This is a VIP customer — be proactive and over-communicate.",
];

export function InstructionPanel({
  run,
  onAdded,
}: {
  run: RunDetail;
  onAdded: () => void;
}) {
  const [text, setText] = useState("");
  const [urgent, setUrgent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const done = isTerminal(run.status);
  const instructions = run.live?.instructions ?? run.instructions;

  async function submit() {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.addInstruction(run.id, text.trim(), urgent);
      setText("");
      setUrgent(false);
      onAdded();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="card-head">
        <h2 className="card-title">Run instructions</h2>
        <span className="text-xs text-slate-500">
          {instructions.length} active
        </span>
      </div>
      <div className="space-y-3 p-4">
        {instructions.length > 0 && (
          <ul className="space-y-1.5">
            {instructions.map((t, i) => (
              <li
                key={i}
                className="rounded border border-edge bg-ink px-3 py-2 text-sm text-slate-300"
              >
                <span className="mr-2 text-slate-600">{i + 1}.</span>
                {t}
              </li>
            ))}
          </ul>
        )}

        {!done && (
          <>
            <div className="flex flex-wrap gap-1.5">
              {PRESETS.map((p) => (
                <button
                  key={p}
                  className="btn btn-xs"
                  onClick={() => setText(p)}
                  type="button"
                >
                  {p.length > 34 ? `${p.slice(0, 34)}…` : p}
                </button>
              ))}
            </div>
            <textarea
              className="input h-20"
              placeholder="Add an instruction that applies only to this run…"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
            <div className="flex flex-wrap items-center gap-3">
              <button
                className="btn btn-primary"
                onClick={submit}
                disabled={busy || !text.trim()}
              >
                {busy ? "Adding…" : "Add instruction"}
              </button>
              <label className="flex items-center gap-2 text-xs text-slate-400">
                <input
                  type="checkbox"
                  checked={urgent}
                  onChange={(e) => setUrgent(e.target.checked)}
                  className="accent-sky-500"
                />
                Urgent — wake the agent now instead of on its next turn
              </label>
            </div>
            <p className="hint">
              Instructions become part of the run context permanently and are
              re-sent to the model on every subsequent turn.
            </p>
          </>
        )}

        {error && (
          <p className="rounded border border-red-800 bg-red-900/40 px-3 py-2 text-xs text-red-300">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
