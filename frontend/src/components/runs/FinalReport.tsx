"use client";

import type { RunDetail } from "@/lib/types";

function Section({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: string;
}) {
  if (!items?.length) return null;
  return (
    <div>
      <p className="label">{title}</p>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li
            key={i}
            className={`rounded border px-3 py-2 text-sm leading-relaxed ${tone}`}
          >
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function FinalReport({ run }: { run: RunDetail }) {
  const output = run.output;
  if (!output) return null;

  return (
    <div className="card border-emerald-900">
      <div className="card-head border-emerald-900 bg-emerald-950/30">
        <h2 className="card-title text-emerald-200">
          ★ Final report — summary, learnings &amp; feedback
        </h2>
        <span className="text-xs text-emerald-500/80">
          {new Date(output.created_at).toLocaleString()}
        </span>
      </div>
      <div className="space-y-4 p-4">
        <div>
          <p className="label">Summary</p>
          <p className="whitespace-pre-wrap rounded border border-edge bg-ink p-3 text-sm leading-relaxed text-slate-300">
            {output.summary}
          </p>
        </div>

        <Section
          title="Important actions taken"
          items={output.important_actions.map(String)}
          tone="border-edge bg-ink text-slate-300"
        />
        <Section
          title="Key learnings"
          items={output.learnings.map(String)}
          tone="border-sky-900 bg-sky-950/30 text-sky-200"
        />
        <Section
          title="Feedback &amp; recommendations"
          items={output.recommendations.map(String)}
          tone="border-amber-900 bg-amber-950/30 text-amber-200"
        />

        {Object.keys(output.stats ?? {}).length > 0 && (
          <div>
            <p className="label">Run analytics</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {Object.entries(output.stats).map(([k, v]) => (
                <div
                  key={k}
                  className="rounded border border-edge bg-ink px-3 py-2"
                >
                  <p className="text-[10px] uppercase tracking-wide text-slate-500">
                    {k.replace(/_/g, " ")}
                  </p>
                  <p className="text-sm font-semibold text-slate-100">
                    {String(v)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
