import { useMemo, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CitationList } from "./CitationList";
import { citationAnchor, linkCitations } from "./citations";
import type { AssistantMessage } from "./useChat";

type Props = { message: AssistantMessage; onRetry: (question: string) => void };

const REFUSAL_LABEL = "Not covered by the knowledge base";

export function AssistantBubble({ message, onRetry }: Props) {
  const [highlighted, setHighlighted] = useState<number | null>(null);
  const result = message.result;
  // While streaming, markers refer to the candidate sources; afterwards to the cited ones.
  const citations = result ? result.citations : [];
  const known = useMemo(
    () => new Set((result ? result.citations : message.sources).map((c) => c.number)),
    [result, message.sources],
  );
  const markdown = useMemo(
    () => linkCitations(message.text, message.id, known),
    [message.text, message.id, known],
  );
  const refused = result?.refused ?? false;

  const focusCitation = (n: number) => {
    setHighlighted(n);
    const card = document.getElementById(citationAnchor(message.id, n));
    card?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
    const details = card?.querySelector("details");
    if (details) details.open = true;
  };

  return (
    <article
      aria-busy={message.status === "streaming"}
      className={`max-w-3xl rounded-lg border px-4 py-3 shadow-sm ${
        refused ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white"
      }`}
    >
      {refused && (
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-700">
          {REFUSAL_LABEL}
        </p>
      )}

      {message.status === "streaming" && !message.text && (
        <p className="text-sm text-slate-500" role="status">
          {message.sources.length > 0
            ? `Found ${message.sources.length} relevant section${message.sources.length > 1 ? "s" : ""}, writing the answer…`
            : "Searching the knowledge base…"}
        </p>
      )}

      {message.text && (
        <div className="prose-answer text-slate-800" aria-live="polite">
          <Markdown
            remarkPlugins={[remarkGfm]}
            components={{
              a: ({ href, children }) => {
                const cite = href?.match(/^#cite-.+-(\d+)$/);
                if (cite) {
                  const n = Number(cite[1]);
                  return (
                    <button
                      type="button"
                      onClick={() => focusCitation(n)}
                      aria-label={`Show source ${n}`}
                      className="mx-0.5 inline-flex h-4 min-w-4 -translate-y-1 items-center justify-center rounded bg-indigo-100 px-1 text-[10px] font-semibold text-indigo-700 hover:bg-indigo-200"
                    >
                      {children}
                    </button>
                  );
                }
                return (
                  <a href={href} target="_blank" rel="noreferrer" className="text-indigo-700 underline">
                    {children}
                  </a>
                );
              },
            }}
          >
            {markdown}
          </Markdown>
          {message.status === "streaming" && (
            <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-slate-400 align-middle" />
          )}
        </div>
      )}

      {message.status === "error" && message.error && (
        <div role="alert" className="mt-2 rounded-md border border-red-200 bg-red-50 p-2 text-sm text-red-800">
          <p>{message.error.message}</p>
          <button
            type="button"
            onClick={() => onRetry(message.question)}
            className="mt-1 text-xs font-medium text-red-700 underline"
          >
            Try again
          </button>
        </div>
      )}

      <CitationList messageId={message.id} citations={citations} highlighted={highlighted} />

      {result && (
        <p className="mt-2 text-right text-[11px] text-slate-400">
          {result.provider ? `${result.model} · ` : ""}
          {(result.timings.total_ms / 1000).toFixed(1)} s
        </p>
      )}
    </article>
  );
}
