// Formatting helpers for benchmark runs: score, result, change and duration.

import type { EvalRun } from "../../api/admin";

const num = (value: unknown) => (typeof value === "number" ? value : null);

/** The headline number of a run, used for the score and for comparing runs. */
export function runScore(run: EvalRun): number | null {
  if (!run.summary) return null;
  return run.kind === "answers"
    ? num(run.summary.passed)
    : num(run.summary.mean_recall);
}

export function runResult(run: EvalRun): string {
  const s = run.summary;
  if (!s) return run.status === "running" ? `${run.done} / ${run.total}` : "–";
  if (run.kind === "answers")
    return `${num(s.passed) ?? "?"} / ${num(s.questions) ?? run.total} passed`;
  return `recall ${(num(s.mean_recall) ?? 0).toFixed(2)} · hit rate ${(num(s.hit_rate) ?? 0).toFixed(2)}`;
}

/** Change against the previous finished run of the same benchmark and model. */
export function runChange(run: EvalRun, older: EvalRun[]): string | null {
  const score = runScore(run);
  const previous = older.find(
    (r) =>
      r.kind === run.kind &&
      r.model === run.model &&
      r.status === "done" &&
      runScore(r) !== null,
  );
  const before = previous ? runScore(previous) : null;
  if (score === null || before === null) return null;
  const delta = score - before;
  if (Math.abs(delta) < 1e-9) return "same as before";
  const text =
    run.kind === "answers" ? `${Math.abs(delta)}` : Math.abs(delta).toFixed(2);
  return `${delta > 0 ? "+" : "−"}${text} vs previous`;
}

export function runDuration(run: EvalRun): string {
  if (!run.finished_at) return "–";
  const seconds =
    (new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) /
    1000;
  return seconds < 120
    ? `${Math.round(seconds)} s`
    : `${Math.round(seconds / 60)} min`;
}
