"use client";

import { useState } from "react";

import { Chip } from "@/components/ui/Badge";
import { api } from "@/lib/api";
import { useSupervisors } from "@/lib/hooks";

const ALL_ACTIONS = [
  "message_fulfillment_team",
  "message_payments_team",
  "message_logistics_team",
  "message_customer",
  "create_internal_note",
];

const MODELS = [
  { id: "gemini-3.5-flash", label: "Gemini 3.5 Flash — balanced & fast" },
  { id: "gemini-3.6-flash", label: "Gemini 3.6 Flash — advanced reasoning" },
  { id: "gemini-3.5-flash-lite", label: "Gemini 3.5 Flash Lite — ultra fast" },
  { id: "openai/gpt-oss-120b", label: "GPT-OSS 120B (Groq) — fallback, high quota" },
];
const CLASSIFIER_MODELS = [
  { id: "gemini-3.5-flash-lite", label: "Gemini 3.5 Flash Lite — fast + cheap" },
  { id: "gemini-3.5-flash", label: "Gemini 3.5 Flash" },
  { id: "openai/gpt-oss-120b", label: "GPT-OSS 120B (Groq)" },
];

const EMPTY = {
  name: "",
  description: "",
  base_instruction: "",
  allowed_actions: [...ALL_ACTIONS],
  default_wake_seconds: 900,
  max_run_age_seconds: 604800,
  wake_aggressiveness: "balanced",
  wake_guidance: "",
  model: "gemini-3.5-flash",
  classifier_model: "gemini-3.5-flash-lite",
  effort: "medium",
  is_default: false,
};

export default function SupervisorsPage() {
  const { data: supervisors, mutate } = useSupervisors();
  const [form, setForm] = useState({ ...EMPTY });
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof typeof EMPTY>(
    key: K,
    value: (typeof EMPTY)[K],
  ) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function toggleAction(action: string) {
    setForm((f) => ({
      ...f,
      allowed_actions: f.allowed_actions.includes(action)
        ? f.allowed_actions.filter((a) => a !== action)
        : [...f.allowed_actions, action],
    }));
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.createSupervisor({
        ...form,
        description: form.description || null,
        wake_guidance: form.wake_guidance || null,
      });
      setForm({ ...EMPTY });
      setOpen(false);
      mutate();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-100">
            Supervisor templates
          </h1>
          <p className="text-sm text-slate-500">
            Instruction, tool allowlist, wake policy and model config. A run
            freezes a copy at start, so editing a template never rewrites
            history.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setOpen(!open)}>
          {open ? "Cancel" : "+ New template"}
        </button>
      </div>

      {open && (
        <div className="card">
          <div className="card-head">
            <h2 className="card-title">Create a supervisor template</h2>
          </div>
          <div className="grid gap-4 p-4 lg:grid-cols-2">
            <div className="space-y-3">
              <div>
                <label className="label">Name</label>
                <input
                  className="input"
                  value={form.name}
                  onChange={(e) => set("name", e.target.value)}
                  placeholder="Fragile Goods Supervisor"
                />
              </div>
              <div>
                <label className="label">Description</label>
                <input
                  className="input"
                  value={form.description}
                  onChange={(e) => set("description", e.target.value)}
                  placeholder="What is this template for?"
                />
              </div>
              <div>
                <label className="label">Base instruction</label>
                <textarea
                  className="input h-40"
                  value={form.base_instruction}
                  onChange={(e) => set("base_instruction", e.target.value)}
                  placeholder="You supervise a single customer order end to end…"
                />
                <p className="hint">
                  The agent&apos;s standing system prompt, sent on every turn.
                </p>
              </div>
            </div>

            <div className="space-y-3">
              <div>
                <label className="label">Available actions</label>
                <div className="space-y-1.5">
                  {ALL_ACTIONS.map((action) => (
                    <label
                      key={action}
                      className="flex items-center gap-2 text-sm text-slate-300"
                    >
                      <input
                        type="checkbox"
                        className="accent-sky-500"
                        checked={form.allowed_actions.includes(action)}
                        onChange={() => toggleAction(action)}
                      />
                      <code className="text-xs">{action}</code>
                    </label>
                  ))}
                </div>
                <p className="hint">
                  Unchecked tools are not offered to the model at all — the
                  restriction is structural, not just a prompt instruction.
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label">Default sleep (sec)</label>
                  <input
                    type="number"
                    className="input"
                    value={form.default_wake_seconds}
                    onChange={(e) =>
                      set("default_wake_seconds", Number(e.target.value))
                    }
                  />
                </div>
                <div>
                  <label className="label">Max run age (sec)</label>
                  <input
                    type="number"
                    className="input"
                    value={form.max_run_age_seconds}
                    onChange={(e) =>
                      set("max_run_age_seconds", Number(e.target.value))
                    }
                  />
                  <p className="hint">A workflow-owned completion rule.</p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label">Wake aggressiveness</label>
                  <select
                    className="input"
                    value={form.wake_aggressiveness}
                    onChange={(e) =>
                      set("wake_aggressiveness", e.target.value)
                    }
                  >
                    <option value="low">low — only hard failures</option>
                    <option value="balanced">balanced</option>
                    <option value="high">high — wake on almost anything</option>
                  </select>
                </div>
                <div>
                  <label className="label">Effort</label>
                  <select
                    className="input"
                    value={form.effort}
                    onChange={(e) => set("effort", e.target.value)}
                  >
                    {["low", "medium", "high", "xhigh"].map((e) => (
                      <option key={e} value={e}>
                        {e}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label">Agent model</label>
                  <select
                    className="input"
                    value={form.model}
                    onChange={(e) => set("model", e.target.value)}
                  >
                    {MODELS.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="label">Classifier model</label>
                  <select
                    className="input"
                    value={form.classifier_model}
                    onChange={(e) => set("classifier_model", e.target.value)}
                  >
                    {CLASSIFIER_MODELS.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="label">Wake guidance (for the gate)</label>
                <textarea
                  className="input h-20"
                  value={form.wake_guidance}
                  onChange={(e) => set("wake_guidance", e.target.value)}
                  placeholder="Wake me for payment failures and delays; batch routine updates."
                />
              </div>

              <label className="flex items-center gap-2 text-sm text-slate-300">
                <input
                  type="checkbox"
                  className="accent-sky-500"
                  checked={form.is_default}
                  onChange={(e) => set("is_default", e.target.checked)}
                />
                Use as the default template for new runs
              </label>
            </div>

            <div className="lg:col-span-2">
              {error && (
                <p className="mb-2 rounded border border-red-800 bg-red-900/40 px-3 py-2 text-xs text-red-300">
                  {error}
                </p>
              )}
              <button
                className="btn btn-primary"
                onClick={submit}
                disabled={busy || !form.name || !form.base_instruction}
              >
                {busy ? "Creating…" : "Create template"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {supervisors?.map((s) => (
          <div key={s.id} className="card">
            <div className="card-head flex-wrap gap-2">
              <h2 className="card-title">{s.name}</h2>
              <div className="flex gap-1.5">
                {s.is_default && <Chip tone="emerald">default</Chip>}
                <Chip
                  tone={
                    s.wake_aggressiveness === "high"
                      ? "amber"
                      : s.wake_aggressiveness === "low"
                        ? "slate"
                        : "sky"
                  }
                >
                  wake: {s.wake_aggressiveness}
                </Chip>
              </div>
            </div>
            <div className="space-y-3 p-4">
              {s.description && (
                <p className="text-sm text-slate-400">{s.description}</p>
              )}
              <p className="max-h-28 overflow-y-auto whitespace-pre-wrap rounded border border-edge bg-ink p-2.5 text-xs leading-relaxed text-slate-500">
                {s.base_instruction}
              </p>
              <div className="flex flex-wrap gap-1">
                {s.allowed_actions.map((a) => (
                  <code
                    key={a}
                    className="rounded border border-edge bg-ink px-1.5 py-0.5 text-[11px] text-slate-400"
                  >
                    {a}
                  </code>
                ))}
              </div>
              <div className="flex flex-wrap gap-3 text-xs text-slate-500">
                <span>sleep {s.default_wake_seconds}s</span>
                <span>max age {Math.round(s.max_run_age_seconds / 3600)}h</span>
                <span>{s.model}</span>
                <span>gate: {s.classifier_model}</span>
                <span>effort {s.effort}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {supervisors?.length === 0 && (
        <p className="text-sm text-slate-500">
          No templates yet. Run <code>make seed</code> in the backend, or create
          one above.
        </p>
      )}
    </div>
  );
}
