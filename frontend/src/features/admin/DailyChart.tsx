import { useEffect, useRef, useState } from "react";
import type { DayCount } from "../../api/admin";

const HEIGHT = 160;
const PAD_BOTTOM = 22;
const PAD_LEFT = 28;

const shortDay = (day: string) =>
  new Date(`${day}T00:00:00Z`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });

/** Stacked bars per day (answered + not covered). Plain SVG: no chart library needed. */
export function DailyChart({ days }: { days: DayCount[] }) {
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

  const max = Math.max(1, ...days.map((d) => d.answered + d.refused));
  const ticks =
    max <= 4
      ? Array.from({ length: max + 1 }, (_, i) => i)
      : [0, Math.round(max / 2), max];
  const slot = (width - PAD_LEFT) / days.length;
  const bar = Math.max(3, Math.min(22, slot * 0.65));
  const plot = HEIGHT - PAD_BOTTOM;
  const y = (n: number) => plot - (n / max) * (plot - 8);
  const labelEvery = Math.ceil(
    days.length / Math.max(2, Math.floor(width / 70)),
  );
  const total = days.reduce((sum, d) => sum + d.answered + d.refused, 0);

  return (
    <div ref={ref}>
      <svg
        width={width}
        height={HEIGHT}
        viewBox={`0 0 ${width} ${HEIGHT}`}
        className="block"
        role="img"
        aria-label={`Questions per day: ${total} in ${days.length} days`}
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
              {t}
            </text>
          </g>
        ))}
        {days.map((d, i) => {
          const x = PAD_LEFT + i * slot + (slot - bar) / 2;
          const answeredTop = y(d.answered);
          const refusedTop = y(d.answered + d.refused);
          return (
            <g key={d.day}>
              <title>{`${shortDay(d.day)}: ${d.answered} answered, ${d.refused} not covered`}</title>
              {d.answered > 0 && (
                <rect
                  x={x}
                  y={answeredTop}
                  width={bar}
                  height={plot - answeredTop}
                  rx={2}
                  className="fill-brand"
                />
              )}
              {d.refused > 0 && (
                <rect
                  x={x}
                  y={refusedTop}
                  width={bar}
                  height={answeredTop - refusedTop}
                  rx={2}
                  className="fill-warning-ink/70"
                />
              )}
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
