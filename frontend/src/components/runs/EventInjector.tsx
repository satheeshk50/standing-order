"use client";

import { useEffect, useState } from "react";

import { Chip } from "@/components/ui/Badge";
import { api } from "@/lib/api";
import { useEventCatalog } from "@/lib/hooks";
import type { RunDetail } from "@/lib/types";
import { isTerminal } from "@/lib/types";

/** The UI half of the event generator. Sends an event into the workflow as a
 *  Temporal signal; the workflow's wake gate decides what happens next. */
export function EventInjector({
  run,
  onSent,
}: {
  run: RunDetail;
  onSent: () => void;
}) {
  const { data: catalog } = useEventCatalog();
  const [selected, setSelected] = useState<string>("");
  const [payload, setPayload] = useState<string>("{}");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState<string | null>(null);

  const done = isTerminal(run.status);

  useEffect(() => {
    if (!catalog?.length) return;
    if (!selected) {
      setSelected(catalog[0].event_type);
      setPayload(JSON.stringify(catalog[0].default_payload, null, 2));
    }
  }, [catalog, selected]);

  function pick(eventType: string) {
    setSelected(eventType);
    const entry = catalog?.find((c) => c.event_type === eventType);
    setPayload(JSON.stringify(entry?.default_payload ?? {}, null, 2));
    setError(null);
  }

  async function send() {
    setBusy(true);
    setError(null);
    setSent(null);
    try {
      let parsed: Record<string, unknown> = {};
      try {
        parsed = payload.trim() ? JSON.parse(payload) : {};
      } catch {
        throw new Error("Payload is not valid JSON.");
      }
      await api.sendEvent(run.id, {
        event_type: selected,
        payload: parsed,
        source: "ui",
      });
      setSent(selected);
      onSent();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const current = catalog?.find((c) => c.event_type === selected);

  return (
    <div className="card">
      <div className="card-head">
        <h2 className="card-title">Inject an event</h2>
        <span className="text-xs text-slate-500">delivered as a signal</span>
      </div>
      <div className="space-y-3 p-4">
        <div className="flex flex-wrap gap-1.5">
          {catalog?.map((entry) => (
            <button
              key={entry.event_type}
              onClick={() => pick(entry.event_type)}
              disabled={done}
              className={`btn btn-xs ${
                selected === entry.event_type ? "btn-primary" : ""
              }`}
              title={
                entry.is_terminal
                  ? "Terminal event — this ends the run"
                  : entry.always_wakes
                    ? "Always wakes the agent"
                    : "Subject to the wake gate"
              }
            >
              {entry.label}
              {entry.is_terminal && " ⏹"}
              {!entry.is_terminal && entry.always_wakes && " ⚡"}
            </button>
          ))}
        </div>

        {current && (
          <div className="flex flex-wrap gap-2">
            {current.is_terminal && (
              <Chip tone="emerald">
                Terminal — completes the run and triggers the final report
              </Chip>
            )}
            {!current.is_terminal && current.always_wakes && (
              <Chip tone="amber">Always wakes the agent (policy)</Chip>
            )}
            {!current.is_terminal && !current.always_wakes && (
              <Chip>Wake gate decides</Chip>
            )}
          </div>
        )}

        <div>
          <label className="label" htmlFor="payload">
            Payload (JSON)
          </label>
          <textarea
            id="payload"
            className="input h-28 font-mono text-xs"
            value={payload}
            onChange={(e) => setPayload(e.target.value)}
            disabled={done}
            spellCheck={false}
          />
        </div>

        <div className="flex items-center gap-3">
          <button
            className="btn btn-primary"
            onClick={send}
            disabled={done || busy || !selected}
          >
            {busy ? "Sending…" : "Send event"}
          </button>
          {sent && !error && (
            <span className="text-xs text-emerald-400">
              Signalled {sent} — watch the timeline.
            </span>
          )}
        </div>

        {done && (
          <p className="hint">
            This run has ended and no longer accepts events.
          </p>
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
