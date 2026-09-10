"use client";

import type { RunDetail } from "@/lib/types";

export function MemoryPanel({ run }: { run: RunDetail }) {
  const memory = run.memory;
  // The workflow query is fresher than the DB projection while a run is live.
  const summary = run.live?.memory_summary || memory?.summary || "";
  const guidance = run.live?.wake_guidance || memory?.wake_guidance || null;

  return (
    <div className="card">
      <div className="card-head">
        <h2 className="card-title">Compact memory</h2>
        <span className="text-xs text-slate-500">
          v{memory?.version ?? 0}
          {memory && memory.compaction_count > 0 && (
            <> · compacted {memory.compaction_count}×</>
          )}
        </span>
      </div>
      <div className="space-y-3 p-4">
        <div>
          <p className="label">Rolling summary</p>
          <p className="whitespace-pre-wrap rounded border border-edge bg-ink p-3 text-sm leading-relaxed text-slate-300">
            {summary || (
              <span className="text-slate-600">
                No memory yet — the agent writes this on its first turn.
              </span>
            )}
          </p>
          <p className="hint">
            This summary is the only long-term history sent to the model. Older
            timeline entries are dropped from the prompt once compacted
            {memory && memory.compacted_through_seq > 0 && (
              <> (watermark: seq {memory.compacted_through_seq})</>
            )}
            .
          </p>
        </div>

        {guidance && (
          <div>
            <p className="label">Agent-authored wake guidance</p>
            <p className="rounded border border-violet-900 bg-violet-950/30 p-3 text-sm text-violet-200">
              {guidance}
            </p>
            <p className="hint">
              The agent writes this for the cheap wake gate, so future events
              are filtered against what it actually cares about now.
            </p>
          </div>
        )}

        {memory && memory.open_issues?.length > 0 && (
          <div>
            <p className="label">Open issues</p>
            <ul className="list-inside list-disc text-sm text-slate-300">
              {memory.open_issues.map((issue, i) => (
                <li key={i}>{String(issue)}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
