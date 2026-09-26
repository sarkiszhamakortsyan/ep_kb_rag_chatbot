import { useEffect, useState, type ReactNode } from "react";
import { getStats, type UsageStats } from "../../api/admin";
import { ApiError } from "../../api/client";
import { modelName } from "../chat/providers";
import { DailyChart } from "./DailyChart";
import { formatDateTime, formatSeconds } from "./format";
import { TurnPanel } from "./TurnPanel";

const RANGES = [7, 30, 90];
const REASONS: Record<string, string> = {
  low_score: "no matching documentation (before the model)",
  no_citations: "the model found no answer in the sources",
  model_refusal: "declined by the model",
};

const isoDay = (d: Date) => d.toISOString().slice(0, 10);
const percent = (part: number, whole: number) =>
  whole ? `${Math.round((part / whole) * 100)}%` : "–";

type Props = { token: string; onUnauthorized: () => void };

export function StatsTab({ token, onUnauthorized }: Props) {
  const [days, setDays] = useState(30);
  const [stats, setStats] = useState<UsageStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const to = new Date();
    const from = new Date(to.getTime() - (days - 1) * 86_400_000);
    getStats(token, { from: isoDay(from), to: isoDay(to) })
      .then((s) => {
        if (!cancelled) {
          setStats(s);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) onUnauthorized();
        else
          setError(
            err instanceof Error
              ? err.message
              : "Could not load the statistics.",
          );
      });
    return () => {
      cancelled = true;
    };
  }, [token, days, onUnauthorized]);

  const maxDocs = Math.max(
    1,
    ...(stats?.top_documents.map((d) => d.citations) ?? []),
  );

  return (
    <section aria-labelledby="stats-title">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="stats-title" className="text-xl font-semibold text-ink">
            Usage statistics
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            How the assistant is used, and where the documentation has gaps.
          </p>
        </div>
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
              onClick={() => setDays(n)}
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
      </div>

      {error && (
        <p
          role="alert"
          className="mb-3 rounded-lg border border-danger-line bg-danger-soft p-3 text-sm text-danger-ink"
        >
          {error}
        </p>
      )}

      {stats && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi
              label="Questions"
              value={String(stats.questions)}
              note={`in ${stats.conversations} conversations`}
            />
            <Kpi
              label="Answered"
              value={percent(stats.answered, stats.questions)}
              note={`${stats.answered} with sources`}
            />
            <Kpi
              label="Not covered"
              value={percent(stats.refused, stats.questions)}
              note={`${stats.refused} questions`}
              tone={stats.refused ? "warning" : undefined}
            />
            <Kpi
              label="Median answer time"
              value={formatSeconds(stats.p50_ms)}
              note="all models"
            />
          </div>

          <Card title="Questions per day">
            <DailyChart days={stats.per_day} />
            <div className="mt-2 flex gap-4 text-xs text-ink-muted">
              <Legend className="bg-brand" label="Answered" />
              <Legend className="bg-warning-ink/70" label="Not covered" />
            </div>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Models">
              {stats.per_model.length === 0 ? (
                <Empty />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[420px] text-sm">
                    <thead className="text-left text-xs text-ink-faint">
                      <tr>
                        <th className="pb-2 font-medium">Model</th>
                        <th className="pb-2 pl-3 text-right font-medium">
                          Questions
                        </th>
                        <th className="pb-2 pl-3 text-right font-medium">
                          Not covered
                        </th>
                        <th className="pb-2 pl-3 text-right font-medium">
                          Median / p95
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.per_model.map((m) => (
                        <tr
                          key={`${m.provider}-${m.model}`}
                          className="border-t border-line"
                        >
                          <td className="py-2 text-ink">
                            {m.provider
                              ? modelName(m.model)
                              : "No model (refused early)"}
                          </td>
                          <td className="py-2 pl-3 text-right whitespace-nowrap text-ink-muted">
                            {m.questions}{" "}
                            <span className="text-ink-faint">
                              ({percent(m.questions, stats.questions)})
                            </span>
                          </td>
                          <td className="py-2 pl-3 text-right text-ink-muted">
                            {m.refused}
                          </td>
                          <td className="py-2 pl-3 text-right whitespace-nowrap text-ink-muted">
                            {formatSeconds(m.p50_ms)} /{" "}
                            {formatSeconds(m.p95_ms)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card title="Most cited documents">
              {stats.top_documents.length === 0 ? (
                <Empty />
              ) : (
                <ul className="space-y-2.5 text-sm">
                  {stats.top_documents.map((d) => (
                    <li key={d.doc_id}>
                      <div className="flex justify-between gap-2">
                        <span className="truncate text-ink">{d.title}</span>
                        <span className="text-ink-muted">{d.citations}</span>
                      </div>
                      <div className="mt-1 h-1.5 rounded-full bg-subtle">
                        <div
                          className="h-1.5 rounded-full bg-brand"
                          style={{ width: `${(d.citations / maxDocs) * 100}%` }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card
              title="Documentation gaps"
              subtitle="Recent questions the knowledge base could not answer: candidates for new articles."
            >
              {stats.recent_refused.length === 0 ? (
                <Empty text="No unanswered questions in this period." />
              ) : (
                <ul className="divide-y divide-line text-sm">
                  {stats.recent_refused.map((q) => (
                    <li key={q.message_id}>
                      <button
                        type="button"
                        onClick={() => setSelected(q.message_id)}
                        className="w-full py-2 text-left hover:bg-subtle"
                      >
                        <span className="block text-ink">{q.question}</span>
                        <span className="block text-xs text-ink-faint">
                          {formatDateTime(q.created_at)} ·{" "}
                          {REASONS[q.reason ?? ""] ?? q.reason}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {Object.keys(stats.refused_by_reason).length > 0 && (
                <p className="mt-3 text-xs text-ink-faint">
                  {Object.entries(stats.refused_by_reason)
                    .map(([reason, n]) => `${n} × ${REASONS[reason] ?? reason}`)
                    .join(" · ")}
                </p>
              )}
            </Card>

            <Card title="Most cited sections">
              {stats.top_sections.length === 0 ? (
                <Empty />
              ) : (
                <ol className="space-y-1.5 text-sm">
                  {stats.top_sections.map((s) => (
                    <li
                      key={`${s.doc_id}-${s.section}`}
                      className="flex justify-between gap-3"
                    >
                      <span className="min-w-0">
                        <span className="block truncate text-ink">
                          {s.section}
                        </span>
                        <span className="block truncate text-xs text-ink-faint">
                          {s.title}
                        </span>
                      </span>
                      <span className="text-ink-muted">{s.citations}</span>
                    </li>
                  ))}
                </ol>
              )}
            </Card>
          </div>
        </div>
      )}

      {selected && (
        <TurnPanel
          token={token}
          messageId={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </section>
  );
}

function Kpi({
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

function Card({
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

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`size-2.5 rounded-sm ${className}`} />
      {label}
    </span>
  );
}

function Empty({ text = "No data in this period." }: { text?: string }) {
  return <p className="py-4 text-center text-sm text-ink-faint">{text}</p>;
}
