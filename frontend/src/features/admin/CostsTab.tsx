import { Info, PiggyBank, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  getCostAdvice,
  getCosts,
  type CostAdvice,
  type CostReport,
} from "../../api/admin";
import { ApiError } from "../../api/client";
import { modelName } from "../chat/providers";
import { ChartLegend, DailyChart, type Series } from "./DailyChart";
import { formatNumber, formatUsd, lastDays } from "./format";
import { RangePicker } from "./RangePicker";
import { Card, Empty, Kpi } from "./ui";

const COST_SERIES: Series[] = [
  { label: "Cost (USD)", className: "fill-brand" },
];

type Props = { token: string; onUnauthorized: () => void };

export function CostsTab({ token, onUnauthorized }: Props) {
  const [days, setDays] = useState(30);
  const [report, setReport] = useState<CostReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [advice, setAdvice] = useState<CostAdvice | null>(null);
  const [adviceState, setAdviceState] = useState<"idle" | "loading" | "error">(
    "idle",
  );
  const [adviceError, setAdviceError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCosts(token, lastDays(days))
      .then((r) => {
        if (!cancelled) {
          setReport(r);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) onUnauthorized();
        else
          setError(
            err instanceof Error ? err.message : "Could not load the costs.",
          );
      });
    return () => {
      cancelled = true;
    };
  }, [token, days, onUnauthorized]);

  const askClaude = async () => {
    setAdviceState("loading");
    setAdviceError(null);
    try {
      setAdvice(await getCostAdvice(token, lastDays(days)));
      setAdviceState("idle");
    } catch (err) {
      setAdviceState("error");
      setAdviceError(
        err instanceof Error ? err.message : "The advice request failed.",
      );
    }
  };

  const claudeUsd =
    report?.per_model
      .filter((m) => m.provider && m.provider !== "ollama")
      .reduce((a, m) => a + m.usd, 0) ?? 0;

  return (
    <section aria-labelledby="costs-title">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="costs-title" className="text-xl font-semibold text-ink">
            Costs
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Estimated from the stored token counts and list prices (set{" "}
            <code>MODEL_PRICES</code> to change them).
          </p>
        </div>
        <RangePicker days={days} onChange={setDays} />
      </div>

      {error && (
        <p
          role="alert"
          className="mb-3 rounded-lg border border-danger-line bg-danger-soft p-3 text-sm text-danger-ink"
        >
          {error}
        </p>
      )}

      {report && (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi
              label="Total cost"
              value={formatUsd(report.total_usd)}
              note={`${report.questions} questions`}
            />
            <Kpi
              label="Per question"
              value={
                report.usd_per_question === null
                  ? "–"
                  : formatUsd(report.usd_per_question)
              }
              note="average, all models"
            />
            <Kpi
              label="Saved by the prompt cache"
              value={formatUsd(report.cache_savings_usd)}
              note={
                report.cache_share === null
                  ? "no Claude questions"
                  : `${Math.round(report.cache_share * 100)}% of Claude input cached`
              }
            />
            <Kpi
              label="Tokens"
              value={formatNumber(
                report.per_model.reduce(
                  (a, m) =>
                    a +
                    m.input_tokens +
                    m.cache_read_tokens +
                    m.cache_write_tokens,
                  0,
                ),
              )}
              note={`in, ${formatNumber(report.per_model.reduce((a, m) => a + m.output_tokens, 0))} out`}
            />
          </div>

          <Card title="Cost per day">
            <DailyChart
              days={report.per_day.map((d) => ({
                day: d.day,
                values: [d.usd],
              }))}
              series={COST_SERIES}
              label={`Cost per day: ${formatUsd(report.total_usd)} in ${report.per_day.length} days`}
              format={(v) =>
                v === 0 ? "$0" : `$${v < 0.1 ? v.toFixed(3) : v.toFixed(2)}`
              }
            />
            <ChartLegend series={COST_SERIES} />
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="By model">
              {report.per_model.length === 0 ? (
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
                          Tokens in / out
                        </th>
                        <th className="pb-2 pl-3 text-right font-medium">
                          Cost
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.per_model.map((m) => (
                        <tr
                          key={`${m.provider}-${m.model}`}
                          className="border-t border-line"
                        >
                          <td className="py-2 text-ink">
                            {m.provider
                              ? modelName(m.model)
                              : "No model (refused early)"}
                            {!m.priced && (
                              <span className="ml-1 text-xs text-warning-ink">
                                (no price)
                              </span>
                            )}
                          </td>
                          <td className="py-2 pl-3 text-right text-ink-muted">
                            {m.questions}
                          </td>
                          <td className="py-2 pl-3 text-right whitespace-nowrap text-ink-muted">
                            {formatNumber(
                              m.input_tokens +
                                m.cache_read_tokens +
                                m.cache_write_tokens,
                            )}{" "}
                            / {formatNumber(m.output_tokens)}
                          </td>
                          <td className="py-2 pl-3 text-right text-ink">
                            {formatUsd(m.usd)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <Card
              title="The same Claude questions with another model"
              subtitle="Same token counts, priced as each Claude model."
            >
              {claudeUsd === 0 ? (
                <Empty text="No Claude questions in this period." />
              ) : (
                <ul className="space-y-2.5 text-sm">
                  {report.what_if.map((w) => {
                    const change = w.usd / claudeUsd - 1;
                    return (
                      <li
                        key={w.model}
                        className="flex items-center justify-between gap-3"
                      >
                        <span className="text-ink">{modelName(w.model)}</span>
                        <span className="text-ink-muted">
                          {formatUsd(w.usd)}{" "}
                          <span
                            className={
                              change < -0.01
                                ? "text-success-ink"
                                : change > 0.01
                                  ? "text-warning-ink"
                                  : ""
                            }
                          >
                            ({change > 0 ? "+" : ""}
                            {Math.round(change * 100)}%)
                          </span>
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>
          </div>

          <Card
            title="How to reduce costs"
            subtitle="Computed from the figures above."
          >
            {report.hints.length === 0 ? (
              <Empty text="No questions in this period." />
            ) : (
              <ul className="space-y-3 text-sm">
                {report.hints.map((h) => (
                  <li key={h.title} className="flex gap-3">
                    <span
                      className={`mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg ${
                        h.kind === "saving"
                          ? "bg-success-soft text-success-ink"
                          : "bg-subtle text-ink-muted"
                      }`}
                    >
                      {h.kind === "saving" ? (
                        <PiggyBank aria-hidden className="size-4" />
                      ) : (
                        <Info aria-hidden className="size-4" />
                      )}
                    </span>
                    <span>
                      <span className="block font-medium text-ink">
                        {h.title}
                      </span>
                      <span className="block text-ink-muted">{h.detail}</span>
                    </span>
                  </li>
                ))}
              </ul>
            )}

            <div className="mt-4 border-t border-line pt-4">
              <button
                type="button"
                onClick={() => void askClaude()}
                disabled={adviceState === "loading" || report.questions === 0}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand px-3 text-sm font-medium text-on-brand hover:bg-brand-strong disabled:opacity-50"
              >
                <Sparkles aria-hidden className="size-4" />
                {adviceState === "loading"
                  ? "Asking Claude…"
                  : "Ask Claude for suggestions"}
              </button>
              <p className="mt-1.5 text-xs text-ink-faint">
                Sends only the aggregated figures above (no questions or
                answers). Costs about $0.02–0.03 with Claude Opus.
              </p>
              {adviceError && (
                <p role="alert" className="mt-2 text-sm text-danger-ink">
                  {adviceError}
                </p>
              )}
              {advice && (
                <div className="mt-3 rounded-lg border border-line bg-subtle p-4">
                  <div className="prose-answer text-sm text-ink">
                    <Markdown remarkPlugins={[remarkGfm]}>
                      {advice.advice}
                    </Markdown>
                  </div>
                  <p className="mt-2 text-xs text-ink-faint">
                    {modelName(advice.model)}
                    {advice.usd !== null &&
                      ` · this advice cost ${formatUsd(advice.usd)}`}
                  </p>
                </div>
              )}
            </div>
          </Card>
        </div>
      )}
    </section>
  );
}
