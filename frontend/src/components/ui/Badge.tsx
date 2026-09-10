const STATUS_STYLES: Record<string, string> = {
  running: "bg-sky-900/60 text-sky-300 border-sky-700",
  sleeping: "bg-indigo-900/50 text-indigo-300 border-indigo-800",
  paused: "bg-amber-900/50 text-amber-300 border-amber-700",
  pending: "bg-slate-800 text-slate-400 border-edge",
  completed: "bg-emerald-900/50 text-emerald-300 border-emerald-700",
  terminated: "bg-red-900/50 text-red-300 border-red-800",
  failed: "bg-red-900/50 text-red-300 border-red-800",
};

const IMPORTANCE_STYLES: Record<string, string> = {
  low: "bg-slate-800 text-slate-500 border-edge",
  normal: "bg-slate-800 text-slate-300 border-edge",
  high: "bg-amber-900/50 text-amber-300 border-amber-800",
  critical: "bg-red-900/50 text-red-300 border-red-800",
};

export function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.pending;
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${style}`}
    >
      {status}
    </span>
  );
}

export function ImportanceBadge({ importance }: { importance: string }) {
  const style = IMPORTANCE_STYLES[importance] ?? IMPORTANCE_STYLES.normal;
  return (
    <span
      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-[10px] uppercase tracking-wide ${style}`}
    >
      {importance}
    </span>
  );
}

export function Chip({
  children,
  tone = "slate",
}: {
  children: React.ReactNode;
  tone?: "slate" | "sky" | "amber" | "emerald";
}) {
  const tones: Record<string, string> = {
    slate: "bg-slate-800 text-slate-300 border-edge",
    sky: "bg-sky-900/50 text-sky-300 border-sky-800",
    amber: "bg-amber-900/40 text-amber-300 border-amber-800",
    emerald: "bg-emerald-900/40 text-emerald-300 border-emerald-800",
  };
  return (
    <span
      className={`inline-flex items-center rounded border px-2 py-0.5 text-xs ${tones[tone]}`}
    >
      {children}
    </span>
  );
}
