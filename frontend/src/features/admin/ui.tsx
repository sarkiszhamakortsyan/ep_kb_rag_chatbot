import type { ReactNode } from "react";

// Building blocks shared by the admin tabs.

export function Kpi({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note: string;
  tone?: "warning";
}) {
  return (
    <div className="rounded-xl border border-line bg-surface p-4 shadow-sm">
      <p className="text-xs font-medium text-ink-muted">{label}</p>
      <p
        className={`mt-1 text-2xl font-semibold tracking-tight ${tone === "warning" ? "text-warning-ink" : "text-ink"}`}
      >
        {value}
      </p>
      <p className="mt-0.5 text-xs text-ink-faint">{note}</p>
    </div>
  );
}

export function Card({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-surface p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      {subtitle && <p className="mt-0.5 text-xs text-ink-faint">{subtitle}</p>}
      <div className="mt-3">{children}</div>
    </div>
  );
}

export function Empty({ text = "No data in this period." }: { text?: string }) {
  return <p className="py-4 text-center text-sm text-ink-faint">{text}</p>;
}
