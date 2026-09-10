"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import type { RunDetail } from "@/lib/types";
import { isTerminal } from "@/lib/types";

export function RunControls({
  run,
  onChanged,
}: {
  run: RunDetail;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const done = isTerminal(run.status);
  const paused = run.live?.paused ?? run.status === "paused";

  async function act(action: string, reason?: string) {
    setBusy(action);
    setError(null);
    try {
      await api.control(run.id, action, reason);
      // Refresh straight away rather than waiting for the next poll tick.
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="card">
      <div className="card-head">
        <h2 className="card-title">Run controls</h2>
      </div>
      <div className="space-y-2 p-4">
        <div className="flex flex-wrap gap-2">
          <button
            className="btn"
            disabled={done || paused || busy !== null}
            onClick={() => act("pause", "Paused from the UI")}
          >
            {busy === "pause" ? "Pausing…" : "Pause"}
          </button>
          <button
            className="btn"
            disabled={done || !paused || busy !== null}
            onClick={() => act("resume", "Resumed from the UI")}
          >
            {busy === "resume" ? "Resuming…" : "Resume"}
          </button>
          <button
            className="btn btn-primary"
            disabled={done || busy !== null}
            onClick={() => act("interrupt", "Operator forced a review")}
          >
            {busy === "interrupt" ? "Waking…" : "Interrupt (wake now)"}
          </button>
          <button
            className="btn btn-danger"
            disabled={done || busy !== null}
            onClick={() => {
              if (
                confirm(
                  "Terminate this run? The agent will still produce its final report before the workflow closes.",
                )
              ) {
                act("terminate", "Terminated from the UI");
              }
            }}
          >
            {busy === "terminate" ? "Terminating…" : "Terminate"}
          </button>
        </div>

        <p className="hint">
          {done
            ? "This run has ended — controls are disabled."
            : paused
              ? "Paused: incoming events still queue on the workflow, but no inference runs until you resume."
              : "Interrupt forces an agent turn immediately instead of waiting for the wake timer."}
        </p>

        {error && (
          <p className="rounded border border-red-800 bg-red-900/40 px-3 py-2 text-xs text-red-300">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
