import { X } from "lucide-react";
import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getTurn, type TurnDetail } from "../../api/admin";
import { modelName } from "../chat/providers";
import { formatDateTime, formatNumber, formatSeconds } from "./format";

type Props = { token: string; messageId: string; onClose: () => void };

/** Slide-over with one stored turn: question, full answer, sources and metrics. */
export function TurnPanel({ token, messageId, onClose }: Props) {
  const [turn, setTurn] = useState<TurnDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getTurn(token, messageId)
      .then((t) => !cancelled && setTurn(t))
      .catch((err: unknown) => !cancelled && setError(err instanceof Error ? err.message : "Could not load."));
    return () => {
      cancelled = true;
    };
  }, [token, messageId]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-20 flex justify-end">
      <button type="button" aria-label="Close details" onClick={onClose} className="absolute inset-0 bg-black/30" />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Answer details"
        className="relative flex h-full w-full max-w-xl flex-col overflow-y-auto border-l border-line bg-surface shadow-xl"
      >
        <div className="sticky top-0 flex items-center justify-between border-b border-line bg-surface px-5 py-3">
          <h3 className="font-semibold text-ink">Answer details</h3>
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
        {!turn && !error && <p className="p-5 text-sm text-ink-muted">Loading…</p>}
        {turn && (
          <div className="space-y-5 p-5 text-sm">
            <p className="text-xs text-ink-faint">{formatDateTime(turn.created_at)}</p>
            <div className="rounded-xl bg-brand-soft px-4 py-3 text-brand-ink">{turn.question}</div>

            <div>
              {turn.refused && (
                <p className="mb-2 inline-block rounded-full bg-warning-soft px-2 py-0.5 text-xs font-medium text-warning-ink">
                  Not covered ({turn.refusal_reason?.replace("_", " ")})
                </p>
              )}
              <div className="prose-answer text-ink">
                <Markdown remarkPlugins={[remarkGfm]}>{turn.answer}</Markdown>
              </div>
            </div>

            {turn.citations.length > 0 && (
              <div>
                <h4 className="mb-2 text-xs font-semibold tracking-wide text-ink-muted uppercase">Sources</h4>
                <ol className="space-y-1.5">
                  {turn.citations.map((c) => (
                    <li key={c.number} className="flex gap-2 rounded-lg border border-line p-2.5">
                      <span className="inline-flex size-5 shrink-0 items-center justify-center rounded bg-brand-soft text-[11px] font-semibold text-brand-ink">
                        {c.number}
                      </span>
                      <span className="min-w-0">
                        <span className="block font-medium text-ink">{c.title}</span>
                        <span className="block text-xs text-ink-faint">
                          {c.section} · {c.doc_id} · similarity {c.score.toFixed(2)}
                        </span>
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            )}

            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-xl border border-line bg-subtle p-4 text-xs">
              <Metric label="Model" value={turn.provider ? modelName(turn.model) : "None (refused before the model)"} />
              <Metric label="Time taken" value={formatSeconds(turn.total_ms)} />
              <Metric label="First token after" value={formatSeconds(turn.ttft_ms)} />
              <Metric label="Retrieval" value={`${Math.round(turn.embed_ms + turn.search_ms)} ms`} />
              <Metric label="Input tokens" value={formatNumber(turn.input_tokens)} />
              <Metric label="Output tokens" value={formatNumber(turn.output_tokens)} />
              <Metric label="Cached input tokens" value={formatNumber(turn.cache_read_tokens)} />
              <Metric label="Best similarity" value={turn.top_score.toFixed(2)} />
              <Metric label="Conversation" value={turn.conversation_id} mono />
              <Metric label="Message" value={turn.message_id} mono />
            </dl>
          </div>
        )}
      </aside>
    </div>
  );
}

function Metric({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-ink-faint">{label}</dt>
      <dd className={`truncate text-ink ${mono ? "font-mono text-[11px]" : ""}`} title={value}>
        {value}
      </dd>
    </div>
  );
}
