"use client";

import { useMemo, useState } from "react";

import { ImportanceBadge } from "@/components/ui/Badge";
import type { Activity } from "@/lib/types";

const KIND_META: Record<string, { label: string; dot: string; icon: string }> = {
  event_received: { label: "Event", dot: "bg-sky-400", icon: "⇢" },
  classifier_decision: { label: "Wake gate", dot: "bg-violet-400", icon: "⚖" },
  agent_turn: { label: "Agent turn", dot: "bg-emerald-400", icon: "◆" },
  agent_action: { label: "Action", dot: "bg-amber-400", icon: "▶" },
  sleep_scheduled: { label: "Sleep", dot: "bg-indigo-400", icon: "☾" },
  wake: { label: "Wake", dot: "bg-yellow-300", icon: "☀" },
  instruction_added: { label: "Instruction", dot: "bg-pink-400", icon: "✎" },
  memory_updated: { label: "Memory", dot: "bg-teal-400", icon: "⛁" },
  control: { label: "Control", dot: "bg-orange-400", icon: "⏻" },
  final_output: { label: "Final report", dot: "bg-emerald-300", icon: "★" },
  system: { label: "System", dot: "bg-slate-500", icon: "•" },
};

const FILTERS: { key: string; label: string; kinds: string[] | null }[] = [
  { key: "all", label: "Everything", kinds: null },
  {
    key: "actions",
    label: "Actions only",
    kinds: ["agent_action"],
  },
  {
    key: "events",
    label: "Events + gate",
    kinds: ["event_received", "classifier_decision"],
  },
  {
    key: "agent",
    label: "Agent reasoning",
    kinds: ["agent_turn", "sleep_scheduled", "wake", "memory_updated"],
  },
];

export function Timeline({ activities }: { activities: Activity[] }) {
  const [filter, setFilter] = useState("all");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const shown = useMemo(() => {
    const spec = FILTERS.find((f) => f.key === filter);
    const rows = spec?.kinds
      ? activities.filter((a) => spec.kinds!.includes(a.kind))
      : activities;
    return [...rows].sort((a, b) => b.seq - a.seq); // newest first
  }, [activities, filter]);

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  return (
    <div className="card">
      <div className="card-head flex-wrap gap-2">
        <h2 className="card-title">
          Timeline &amp; activity log{" "}
          <span className="font-normal text-slate-500">
            ({shown.length} of {activities.length})
          </span>
        </h2>
        <div className="flex flex-wrap gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`btn btn-xs ${
                filter === f.key ? "btn-primary" : ""
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="max-h-[36rem] overflow-y-auto">
        {shown.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-slate-500">
            Nothing recorded yet.
          </p>
        ) : (
          <ul className="divide-y divide-edge">
            {shown.map((a) => {
              const meta = KIND_META[a.kind] ?? KIND_META.system;
              const isOpen = expanded.has(a.id);
              const hasMore =
                (a.body?.length ?? 0) > 160 ||
                Object.keys(a.payload ?? {}).length > 0;
              return (
                <li key={a.id} className="px-4 py-2.5 hover:bg-slate-900/40">
                  <div className="flex items-start gap-3">
                    <span
                      className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${meta.dot}`}
                      aria-hidden
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[11px] uppercase tracking-wide text-slate-500">
                          {meta.icon} {meta.label}
                        </span>
                        <ImportanceBadge importance={a.importance} />
                        <span className="text-[11px] text-slate-600">
                          #{a.seq} ·{" "}
                          {new Date(a.created_at).toLocaleTimeString()}
                        </span>
                        <span className="text-[11px] text-slate-600">
                          by {a.actor}
                        </span>
                      </div>
                      <p className="mt-0.5 text-sm font-medium text-slate-100">
                        {a.title}
                      </p>
                      {a.body && (
                        <p
                          className={`mt-0.5 whitespace-pre-wrap text-sm text-slate-400 ${
                            isOpen ? "" : "line-clamp-2"
                          }`}
                        >
                          {a.body}
                        </p>
                      )}
                      {isOpen && Object.keys(a.payload ?? {}).length > 0 && (
                        <pre className="scroll-x mt-2 rounded border border-edge bg-ink p-2 text-[11px] text-slate-400">
                          {JSON.stringify(a.payload, null, 2)}
                        </pre>
                      )}
                      {hasMore && (
                        <button
                          onClick={() => toggle(a.id)}
                          className="mt-1 text-[11px] text-sky-400 hover:underline"
                        >
                          {isOpen ? "less" : "more"}
                        </button>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
