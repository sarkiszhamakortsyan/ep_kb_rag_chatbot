import { Play, Square } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  cancelEvalRun,
  getEvalRun,
  listEvalRuns,
  startEvalRun,
  type EvalKind,
  type EvalRun,
} from "../../api/admin";
import { ApiError, getProviders } from "../../api/client";
import type { Provider } from "../../api/types";
import { modelName } from "../chat/providers";
import { runChange, runDuration, runResult } from "./evalFormat";
import { formatDateTime } from "./format";
import { RunPanel } from "./RunPanel";
import { Card, Empty } from "./ui";

const STATUS_STYLE: Record<EvalRun["status"], string> = {
  running: "bg-brand-soft text-brand-ink",
  cancelling: "bg-subtle text-ink-muted",
  done: "bg-success-soft text-success-ink",
  failed: "bg-danger-soft text-danger-ink",
  cancelled: "bg-subtle text-ink-muted",
  interrupted: "bg-warning-soft text-warning-ink",
};

function costNote(kind: EvalKind, provider: string): string {
  if (kind === "retrieval")
    return "Checks that the right documents are found. Free, takes a few seconds.";
  return provider === "ollama"
    ? "Runs every question through the local model. Free, but takes about 20 minutes on a CPU."
    : "Runs every question through Claude. Costs about $0.20 with Claude Opus and takes about 2 minutes.";
}

type RunsData = { runs: EvalRun[]; current: EvalRun | null };

/** The run list plus the full record of the run in progress, if any. */
async function fetchRuns(token: string): Promise<RunsData> {
  const list = await listEvalRuns(token);
  return {
    runs: list.runs,
    current: list.running ? await getEvalRun(token, list.running) : null,
  };
}

type Props = { token: string; onUnauthorized: () => void };

export function TestsTab({ token, onUnauthorized }: Props) {
  const [kind, setKind] = useState<EvalKind>("retrieval");
  const [providers, setProviders] = useState<Provider[]>([]);
  const [provider, setProvider] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [current, setCurrent] = useState<EvalRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const fail = useCallback(
    (err: unknown) => {
      if (err instanceof ApiError && err.status === 401) onUnauthorized();
      else
        setError(err instanceof Error ? err.message : "Something went wrong.");
    },
    [onUnauthorized],
  );

  const apply = useCallback((data: RunsData) => {
    setRuns(data.runs);
    setCurrent(data.current);
  }, []);

  const refresh = useCallback(
    () => fetchRuns(token).then(apply, fail),
    [token, apply, fail],
  );

  useEffect(() => {
    let cancelled = false;
    fetchRuns(token).then((data) => !cancelled && apply(data), fail);
    getProviders()
      .then((r) => {
        if (cancelled) return;
        const usable = r.providers.filter((p) => p.available);
        setProviders(usable);
        setProvider(
          usable.find((p) => p.default)?.name ?? usable[0]?.name ?? "",
        );
      })
      .catch(() => setProviders([]));
    return () => {
      cancelled = true;
    };
  }, [token, apply, fail]);

  // While a run is in progress, follow it every 2 seconds.
  useEffect(() => {
    if (!current || current.status !== "running") return;
    const timer = setTimeout(() => {
      getEvalRun(token, current.id)
        .then((run) =>
          run.status === "running" ? setCurrent(run) : void refresh(),
        )
        .catch(fail);
    }, 2000);
    return () => clearTimeout(timer);
  }, [current, token, refresh, fail]);

  const start = async () => {
    setConfirming(false);
    setError(null);
    try {
      setCurrent(
        await startEvalRun(
          token,
          kind,
          kind === "answers" ? provider : undefined,
        ),
      );
      void refresh();
    } catch (err) {
      fail(err);
    }
  };

  const needsConfirm = kind === "answers" && provider !== "ollama";
  const running = current?.status === "running";

  return (
    <section aria-labelledby="tests-title">
      <div className="mb-4">
        <h2 id="tests-title" className="text-xl font-semibold text-ink">
          Tests
        </h2>
        <p className="mt-1 text-sm text-ink-muted">
          Run the 18-question benchmark against the live system and compare the
          results over time.
        </p>
      </div>

      {error && (
        <p
          role="alert"
          className="mb-3 rounded-lg border border-danger-line bg-danger-soft p-3 text-sm text-danger-ink"
        >
          {error}
        </p>
      )}

      <div className="space-y-4">
        <Card title="Run a benchmark">
          {running && current ? (
            <div>
              <div className="flex items-center justify-between gap-3 text-sm">
                <span className="text-ink">
                  {current.kind === "answers"
                    ? "Answer benchmark"
                    : "Retrieval benchmark"}
                  {current.kind === "answers" &&
                    ` · ${modelName(current.model)}`}
                </span>
                <span className="text-ink-muted">
                  {current.done} / {current.total} questions
                </span>
              </div>
              <div
                role="progressbar"
                aria-label="Benchmark progress"
                aria-valuemin={0}
                aria-valuemax={current.total}
                aria-valuenow={current.done}
                className="mt-2 h-2 rounded-full bg-subtle"
              >
                <div
                  className="h-2 rounded-full bg-brand transition-all"
                  style={{
                    width: `${(current.done / Math.max(1, current.total)) * 100}%`,
                  }}
                />
              </div>
              <button
                type="button"
                onClick={() =>
                  void cancelEvalRun(token, current.id).then(refresh, fail)
                }
                className="mt-3 inline-flex h-9 items-center gap-1.5 rounded-lg border border-line px-3 text-sm text-ink-muted hover:border-line-strong hover:text-ink"
              >
                <Square aria-hidden className="size-3.5 fill-current" />
                Cancel
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <div
                role="radiogroup"
                aria-label="Benchmark"
                className="grid gap-2 sm:grid-cols-2"
              >
                {(["retrieval", "answers"] as const).map((k) => (
                  <label
                    key={k}
                    className={`flex cursor-pointer gap-3 rounded-lg border p-3 text-sm ${
                      kind === k
                        ? "border-brand bg-brand-soft/50"
                        : "border-line hover:border-line-strong"
                    }`}
                  >
                    <input
                      type="radio"
                      name="kind"
                      checked={kind === k}
                      onChange={() => {
                        setKind(k);
                        setConfirming(false);
                      }}
                      className="mt-0.5 accent-[var(--color-brand)]"
                    />
                    <span>
                      <span className="block font-medium text-ink">
                        {k === "retrieval" ? "Retrieval" : "Answers"}
                      </span>
                      <span className="block text-ink-muted">
                        {k === "retrieval"
                          ? "Are the right documents found? No model needed."
                          : "The full pipeline: facts, citations and refusals."}
                      </span>
                    </span>
                  </label>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {kind === "answers" && (
                  <label className="flex items-center gap-2 text-sm text-ink-muted">
                    Model
                    <select
                      value={provider}
                      onChange={(e) => {
                        setProvider(e.target.value);
                        setConfirming(false);
                      }}
                      className="h-9 rounded-lg border border-line bg-surface px-2.5 text-sm text-ink"
                    >
                      {providers.map((p) => (
                        <option key={p.name} value={p.name}>
                          {modelName(p.model)}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {confirming ? (
                  <>
                    <button
                      type="button"
                      onClick={() => void start()}
                      className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand px-3 text-sm font-medium text-on-brand hover:bg-brand-strong"
                    >
                      Yes, run it (about $0.20)
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirming(false)}
                      className="h-9 rounded-lg px-3 text-sm text-ink-muted hover:text-ink"
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={() =>
                      needsConfirm ? setConfirming(true) : void start()
                    }
                    disabled={kind === "answers" && !provider}
                    className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand px-3 text-sm font-medium text-on-brand hover:bg-brand-strong disabled:opacity-50"
                  >
                    <Play aria-hidden className="size-4" />
                    Run benchmark
                  </button>
                )}
              </div>
              <p className="text-xs text-ink-faint">
                {costNote(kind, provider)}
              </p>
            </div>
          )}
        </Card>

        <Card title="Recent runs">
          {runs.length === 0 ? (
            <Empty text="No benchmark runs yet." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead className="text-xs text-ink-faint">
                  <tr>
                    <th className="pb-2 font-medium">Started</th>
                    <th className="pb-2 pl-3 font-medium">Benchmark</th>
                    <th className="pb-2 pl-3 font-medium">Result</th>
                    <th className="pb-2 pl-3 font-medium">Change</th>
                    <th className="pb-2 pl-3 font-medium">Duration</th>
                    <th className="pb-2 pl-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run, i) => (
                    <tr
                      key={run.id}
                      onClick={() => setSelected(run.id)}
                      className="cursor-pointer border-t border-line hover:bg-subtle"
                    >
                      <td className="py-2 whitespace-nowrap text-ink-muted">
                        {formatDateTime(run.started_at)}
                      </td>
                      <td className="py-2 pl-3">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelected(run.id);
                          }}
                          className="text-left text-ink hover:underline"
                        >
                          {run.kind === "answers"
                            ? `Answers · ${modelName(run.model)}`
                            : "Retrieval"}
                        </button>
                      </td>
                      <td className="py-2 pl-3 whitespace-nowrap text-ink">
                        {runResult(run)}
                      </td>
                      <td className="py-2 pl-3 whitespace-nowrap text-ink-muted">
                        {runChange(run, runs.slice(i + 1)) ?? "–"}
                      </td>
                      <td className="py-2 pl-3 whitespace-nowrap text-ink-muted">
                        {runDuration(run)}
                      </td>
                      <td className="py-2 pl-3">
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[run.status]}`}
                        >
                          {run.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {selected && (
        <RunPanel
          token={token}
          runId={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </section>
  );
}
