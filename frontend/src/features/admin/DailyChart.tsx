import { useEffect, useRef, useState } from "react";

const HEIGHT = 160;
const PAD_BOTTOM = 22;
const PAD_LEFT = 44;

const shortDay = (day: string) =>
  new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });

export type DayValues = { day: string; values: number[] };
export type Series = { label: string; className: string };

type Props = {
  days: DayValues[];
  series: Series[]; // one per entry in `values`, stacked bottom-up
  label: string; // accessible summary
  format?: (value: number) => string;
};

/** Stacked bars per day. Plain SVG: no chart library needed. */
export function DailyChart({ days, series, label, format = String }: Props) {
  // Drawn at the container's real width, so text keeps its size on any screen.
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(640);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(280, entry.contentRect.width)),
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const sum = (d: DayValues) => d.values.reduce((a, b) => a + b, 0);
  const peak = Math.max(0, ...days.map(sum));
  const integers = days.every((d) => d.values.every(Number.isInteger));
  const max = peak > 0 ? peak : 1;
  const ticks =
    integers && max <= 4
      ? Array.from({ length: max + 1 }, (_, i) => i)
      : [0, max / 2, max];
  const slot = (width - PAD_LEFT) / days.length;
  const bar = Math.max(3, Math.min(22, slot * 0.65));
  const plot = HEIGHT - PAD_BOTTOM;
  const y = (n: number) => plot - (n / max) * (plot - 8);
  const labelEvery = Math.ceil(
    days.length / Math.max(2, Math.floor(width / 70)),
  );

  return (
    <div ref={ref}>
      <svg
        width={width}
        height={HEIGHT}
        viewBox={`0 0 ${width} ${HEIGHT}`}
        className="block"
        role="img"
        aria-label={label}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line
              x1={PAD_LEFT}
              x2={width}
              y1={y(t)}
              y2={y(t)}
              className="stroke-line"
              strokeWidth={1}
            />
            <text
              x={PAD_LEFT - 6}
              y={y(t) + 3}
              textAnchor="end"
              className="fill-ink-faint text-[10px]"
            >
              {format(t)}
            </text>
          </g>
        ))}
        {days.map((d, i) => {
          const x = PAD_LEFT + i * slot + (slot - bar) / 2;
          let base = 0;
          return (
            <g key={d.day}>
              <title>{`${shortDay(d.day)}: ${series.map((s, k) => `${s.label} ${format(d.values[k])}`).join(", ")}`}</title>
              {d.values.map((v, k) => {
                const top = y(base + v);
                const bottom = y(base);
                base += v;
                return v > 0 ? (
                  <rect
                    key={k}
                    x={x}
                    y={top}
                    width={bar}
                    height={bottom - top}
                    rx={2}
                    className={series[k].className}
                  />
                ) : null;
              })}
              {i % labelEvery === 0 && (
                <text
                  x={x + bar / 2}
                  y={HEIGHT - 6}
                  textAnchor="middle"
                  className="fill-ink-faint text-[10px]"
                >
                  {shortDay(d.day)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function ChartLegend({ series }: { series: Series[] }) {
  return (
    <div className="mt-2 flex gap-4 text-xs text-ink-muted">
      {series.map((s) => (
        <span key={s.label} className="inline-flex items-center gap-1.5">
          <span
            className={`size-2.5 rounded-sm ${s.className.replace("fill-", "bg-")}`}
          />
          {s.label}
        </span>
      ))}
    </div>
  );
}
