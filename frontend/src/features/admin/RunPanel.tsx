// Detail panel for one benchmark run in the Tests tab: progress, score, and every question with its
// result, failures first.

import { CircleCheck, CircleX, X } from "lucide-react";
import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getEvalRun, type EvalRun } from "../../api/admin";
import { modelName } from "../chat/providers";
import { runDuration, runResult } from "./evalFormat";
import { formatDateTime, formatSeconds } from "./format";

type Row = Record<string, unknown>;
const list = (value: unknown) =>
  Array.isArray(value) ? value.join(", ") || "none" : "–";

type Props = { token: string; runId: string; onClose: () => void };

/** Slide-over with one benchmark run: summary and per-question results, failures first. */
export function RunPanel({ token, runId, onClose }: Props) {
  const [run, setRun] = useState<EvalRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getEvalRun(token, runId)
      .then((r) => !cancelled && setRun(r))
      .catch(
        (err: unknown) =>
          !cancelled &&
          setError(err instanceof Error ? err.message : "Could not load."),
      );
    return () => {
      cancelled = true;
    };
  }, [token, runId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const rows = [...(run?.results ?? [])].sort(
    (a, b) => Number(a.passed) - Number(b.passed),
  );

  return (
    <div className="fixed inset-0 z-20 flex justify-end">
      <button
        type="button"
        aria-label="Close details"
        onClick={onClose}
        className="absolute inset-0 bg-black/30"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Benchmark run"
        className="relative flex h-full w-full max-w-2xl flex-col overflow-y-auto border-l border-line bg-surface shadow-xl"
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-surface px-5 py-3">
          <h3 className="font-semibold text-ink">
            {run
              ? run.kind === "answers"
                ? `Answer benchmark · ${modelName(run.model)}`
                : "Retrieval benchmark"
              : "Benchmark run"}
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="inline-flex size-8 items-center justify-center rounded-lg text-ink-muted hover:bg-subtle"
          >
            <X aria-hidden className="size-4" />
          </button>
        </div>

        {error && <p className="p-5 text-sm text-danger-ink">{error}</p>}
        {!run && !error && (
          <p className="p-5 text-sm text-ink-muted">Loading…</p>
        )}
        {run && (
          <div className="space-y-4 p-5 text-sm">
            <p className="text-ink-muted">
              {formatDateTime(run.started_at)} · {runDuration(run)} ·{" "}
              <span className="font-medium text-ink">{runResult(run)}</span>
            </p>
            {run.error && (
              <p className="rounded-lg bg-danger-soft p-3 text-danger-ink">
                {run.error}
              </p>
            )}
            <ul className="divide-y divide-line rounded-xl border border-line">
              {rows.map((r) => (
                <ResultRow key={String(r.id)} row={r} kind={run.kind} />
              ))}
            </ul>
          </div>
        )}
      </aside>
    </div>
  );
}

function ResultRow({ row, kind }: { row: Row; kind: EvalRun["kind"] }) {
  const passed = Boolean(row.passed);
  const detail =
    kind === "retrieval"
      ? `expected ${list(row.expected)} · found ${list(row.retrieved)} · best similarity ${Number(row.top_score).toFixed(2)}`
      : row.answerable
        ? `cited ${list(row.cited)} · facts ${(row.facts_found as unknown[]).length}/${(row.key_facts as unknown[]).length} · ${formatSeconds(Number(row.total_ms))}`
        : `${row.refused ? "refused" : "answered"} (should be refused) · ${formatSeconds(Number(row.total_ms))}`;
  return (
    <li className="p-3">
      <details className="group">
        <summary className="flex cursor-pointer list-none items-start gap-2 [&::-webkit-details-marker]:hidden">
          {passed ? (
            <CircleCheck
              aria-label="passed"
              className="mt-0.5 size-4 shrink-0 text-success-ink"
            />
          ) : (
            <CircleX
              aria-label="failed"
              className="mt-0.5 size-4 shrink-0 text-danger-ink"
            />
          )}
          <span className="min-w-0">
            <span className="block text-ink">
              <span className="mr-1.5 font-mono text-xs text-ink-faint">
                {String(row.id)}
              </span>
              {String(row.question)}
            </span>
            <span className="block text-xs text-ink-faint">{detail}</span>
          </span>
        </summary>
        {kind === "answers" && typeof row.answer === "string" && (
          <div className="prose-answer mt-2 ml-6 rounded-lg bg-subtle p-3 text-ink">
            <Markdown remarkPlugins={[remarkGfm]}>{row.answer}</Markdown>
          </div>
        )}
      </details>
    </li>
  );
}
