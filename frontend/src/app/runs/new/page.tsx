"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { useSupervisors } from "@/lib/hooks";
import type { RunDetail } from "@/lib/types";

function randomOrderId() {
  return `ORD-${Math.floor(10000 + Math.random() * 89999)}`;
}

export default function NewRunPage() {
  const router = useRouter();
  const { data: supervisors } = useSupervisors();

  const [orderId, setOrderId] = useState("");
  const [supervisorId, setSupervisorId] = useState("");
  const [customerName, setCustomerName] = useState("Priya Raman");
  const [value, setValue] = useState("129.99");
  const [items, setItems] = useState("1x Noise-cancelling headphones");
  const [priority, setPriority] = useState("standard");
  const [seed, setSeed] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setOrderId(randomOrderId()), []);
  useEffect(() => {
    if (!supervisorId && supervisors?.length) {
      setSupervisorId(
        (supervisors.find((s) => s.is_default) ?? supervisors[0]).id,
      );
    }
  }, [supervisors, supervisorId]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const run = (await api.createRun({
        order_id: orderId,
        supervisor_id: supervisorId || null,
        order_context: {
          customer_name: customerName,
          value: Number(value) || value,
          items,
          priority,
        },
        seed_order_created_event: seed,
      })) as RunDetail;
      router.push(`/runs/${run.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-slate-100">
          Start a supervision run
        </h1>
        <p className="text-sm text-slate-500">
          Starts one Temporal workflow for this order. The workflow id is
          derived from the order id, so an order can never get two supervisors.
        </p>
      </div>

      <div className="card">
        <div className="space-y-4 p-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="label">Order ID</label>
              <div className="flex gap-2">
                <input
                  className="input"
                  value={orderId}
                  onChange={(e) => setOrderId(e.target.value)}
                />
                <button
                  className="btn"
                  type="button"
                  onClick={() => setOrderId(randomOrderId())}
                >
                  ↻
                </button>
              </div>
            </div>
            <div>
              <label className="label">Supervisor template</label>
              <select
                className="input"
                value={supervisorId}
                onChange={(e) => setSupervisorId(e.target.value)}
              >
                {supervisors?.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                    {s.is_default ? " (default)" : ""}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <fieldset className="space-y-3 rounded border border-edge p-3">
            <legend className="px-1 text-xs uppercase tracking-wide text-slate-500">
              Order context
            </legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="label">Customer</label>
                <input
                  className="input"
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                />
              </div>
              <div>
                <label className="label">Value</label>
                <input
                  className="input"
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                />
              </div>
            </div>
            <div>
              <label className="label">Items</label>
              <input
                className="input"
                value={items}
                onChange={(e) => setItems(e.target.value)}
              />
            </div>
            <div>
              <label className="label">Priority</label>
              <select
                className="input"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
              >
                <option value="standard">standard</option>
                <option value="express">express</option>
                <option value="vip">vip</option>
              </select>
            </div>
          </fieldset>

          <label className="flex items-start gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              className="mt-0.5 accent-sky-500"
              checked={seed}
              onChange={(e) => setSeed(e.target.checked)}
            />
            <span>
              Send an <code className="text-xs">order_created</code> event
              immediately
              <span className="block text-xs text-slate-500">
                Gives the agent something to react to on its very first turn.
              </span>
            </span>
          </label>

          {error && (
            <p className="rounded border border-red-800 bg-red-900/40 px-3 py-2 text-sm text-red-300">
              {error}
            </p>
          )}

          <button
            className="btn btn-primary"
            onClick={submit}
            disabled={busy || !orderId || !supervisorId}
          >
            {busy ? "Starting workflow…" : "Start supervision"}
          </button>
        </div>
      </div>
    </div>
  );
}
