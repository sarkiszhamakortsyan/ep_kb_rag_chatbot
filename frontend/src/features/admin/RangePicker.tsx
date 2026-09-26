const RANGES = [7, 30, 90];

/** 7 / 30 / 90-day switch shared by the Statistics and Costs tabs. */
export function RangePicker({
  days,
  onChange,
}: {
  days: number;
  onChange: (days: number) => void;
}) {
  return (
    <div
      role="group"
      aria-label="Time range"
      className="inline-flex rounded-lg border border-line bg-surface p-0.5"
    >
      {RANGES.map((n) => (
        <button
          key={n}
          type="button"
          aria-pressed={days === n}
          onClick={() => onChange(n)}
          className={`h-8 rounded-md px-3 text-sm ${
            days === n
              ? "bg-brand-soft font-medium text-brand-ink"
              : "text-ink-muted hover:text-ink"
          }`}
        >
          {n} days
        </button>
      ))}
    </div>
  );
}
