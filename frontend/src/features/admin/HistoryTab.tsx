import { ChevronLeft, ChevronRight, Download, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { exportHistory, listHistory, type HistoryPage, type HistoryQuery } from "../../api/admin";
import { ApiError } from "../../api/client";
import { modelName } from "../chat/providers";
import { formatDateTime, formatSeconds } from "./format";
import { TurnPanel } from "./TurnPanel";

const PAGE_SIZE = 25;
const FIELD =
  "h-9 rounded-lg border border-line bg-surface px-2.5 text-sm text-ink hover:border-line-strong focus:border-brand focus:outline-none";

type Props = { token: string; retentionDays: number; onUnauthorized: () => void };

export function HistoryTab({ token, retentionDays, onUnauthorized }: Props) {
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState<HistoryQuery>({});
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<HistoryPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  // Typing in the search box waits briefly before querying.
  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters((f) => ({ ...f, q: search.trim() || undefined }));
      setOffset(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    listHistory(token, { ...filters, limit: PAGE_SIZE, offset })
      .then((p) => {
        if (!cancelled) {
          setPage(p);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) onUnauthorized();
        else setError(err instanceof Error ? err.message : "Could not load the history.");
      });
    return () => {
      cancelled = true;
    };
  }, [token, filters, offset, onUnauthorized]);

  const setFilter = (change: HistoryQuery) => {
    setFilters((f) => ({ ...f, ...change }));
    setOffset(0);
  };

  const download = async () => {
    const blob = await exportHistory(token, filters);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `chat-history-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const status = filters.refused === undefined ? "" : filters.refused ? "refused" : "answered";

  return (
    <section aria-labelledby="history-title">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="history-title" className="text-xl font-semibold text-ink">
            Response history
          </h2>
          <p className="mt-1 text-sm text-ink-muted">
            Every question and answer from the chat. Kept for {retentionDays} days.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void download()}
          disabled={!page?.total}
          className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line bg-surface px-3 text-sm text-ink hover:border-line-strong disabled:opacity-50"
        >
          <Download aria-hidden className="size-4" />
          Export CSV
        </button>
      </div>

      <div className="mb-3 flex flex-wrap gap-2">
        <label className="relative min-w-56 flex-1">
          <span className="sr-only">Search questions and answers</span>
          <Search aria-hidden className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-ink-faint" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search questions and answers"
            className={`${FIELD} w-full pl-8`}
          />
        </label>
        <label>
          <span className="sr-only">Model</span>
          <select
            value={filters.provider ?? ""}
            onChange={(e) => setFilter({ provider: e.target.value || undefined })}
            className={FIELD}
          >
            <option value="">All models</option>
            <option value="anthropic">Claude (cloud)</option>
            <option value="ollama">Local model</option>
            <option value="none">No model (refused early)</option>
          </select>
        </label>
        <label>
          <span className="sr-only">Status</span>
          <select
            value={status}
            onChange={(e) => setFilter({ refused: e.target.value === "" ? undefined : e.target.value === "refused" })}
            className={FIELD}
          >
            <option value="">All answers</option>
            <option value="answered">Answered</option>
            <option value="refused">Not covered</option>
          </select>
        </label>
        <label className="flex items-center gap-1.5 text-sm text-ink-muted">
          From
          <input
            type="date"
            value={filters.from ?? ""}
            onChange={(e) => setFilter({ from: e.target.value || undefined })}
            className={FIELD}
          />
        </label>
        <label className="flex items-center gap-1.5 text-sm text-ink-muted">
          To
          <input
            type="date"
            value={filters.to ?? ""}
            onChange={(e) => setFilter({ to: e.target.value || undefined })}
            className={FIELD}
          />
        </label>
      </div>

      {error && (
        <p role="alert" className="mb-3 rounded-lg border border-danger-line bg-danger-soft p-3 text-sm text-danger-ink">
          {error}
        </p>
      )}

      <div className="overflow-x-auto rounded-xl border border-line bg-surface shadow-sm">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="border-b border-line bg-subtle text-xs text-ink-muted">
            <tr>
              <th className="px-4 py-2.5 font-medium">Time</th>
              <th className="px-4 py-2.5 font-medium">Question</th>
              <th className="px-4 py-2.5 font-medium">Model</th>
              <th className="px-4 py-2.5 font-medium">Status</th>
              <th className="px-4 py-2.5 text-right font-medium">Sources</th>
              <th className="px-4 py-2.5 text-right font-medium">Time taken</th>
            </tr>
          </thead>
          <tbody>
            {page?.items.map((t) => (
              <tr
                key={t.message_id}
                onClick={() => setSelected(t.message_id)}
                className="cursor-pointer border-b border-line last:border-0 hover:bg-subtle"
              >
                <td className="px-4 py-2.5 whitespace-nowrap text-ink-muted">{formatDateTime(t.created_at)}</td>
                <td className="max-w-md px-4 py-2.5">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelected(t.message_id);
                    }}
                    className="block max-w-full truncate text-left text-ink hover:underline"
                  >
                    {t.question}
                  </button>
                </td>
                <td className="px-4 py-2.5 whitespace-nowrap text-ink-muted">
                  {t.provider ? modelName(t.model) : "–"}
                </td>
                <td className="px-4 py-2.5">
                  <span
                    className={`rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ${
                      t.refused ? "bg-warning-soft text-warning-ink" : "bg-success-soft text-success-ink"
                    }`}
                  >
                    {t.refused ? "Not covered" : "Answered"}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-right text-ink-muted">{t.sources}</td>
                <td className="px-4 py-2.5 text-right whitespace-nowrap text-ink-muted">{formatSeconds(t.total_ms)}</td>
              </tr>
            ))}
            {page && page.items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-10 text-center text-ink-muted">
                  No questions match these filters yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {page && page.total > 0 && (
        <div className="mt-3 flex items-center justify-between text-sm text-ink-muted">
          <span>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, page.total)} of {page.total}
          </span>
          <div className="flex gap-1">
            <button
              type="button"
              aria-label="Previous page"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              className="inline-flex size-9 items-center justify-center rounded-lg border border-line bg-surface hover:border-line-strong disabled:opacity-40"
            >
              <ChevronLeft aria-hidden className="size-4" />
            </button>
            <button
              type="button"
              aria-label="Next page"
              disabled={offset + PAGE_SIZE >= page.total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              className="inline-flex size-9 items-center justify-center rounded-lg border border-line bg-surface hover:border-line-strong disabled:opacity-40"
            >
              <ChevronRight aria-hidden className="size-4" />
            </button>
          </div>
        </div>
      )}

      {selected && <TurnPanel token={token} messageId={selected} onClose={() => setSelected(null)} />}
    </section>
  );
}
