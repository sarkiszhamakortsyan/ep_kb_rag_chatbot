import { Check, CircleCheck, Copy, Info, LoaderCircle, RotateCcw, TriangleAlert } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CitationList } from "./CitationList";
import { citationAnchor, linkCitations, stripCitations } from "./citations";
import { LogoMark } from "./LogoMark";
import { modelName } from "./providers";
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
  const streaming = message.status === "streaming";

  const focusCitation = (n: number) => {
    setHighlighted(n);
    const card = document.getElementById(citationAnchor(message.id, n));
    card?.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
    const details = card?.querySelector("details");
    if (details) details.open = true;
  };

  return (
    <div className="flex gap-3">
      <LogoMark className="mt-1 hidden size-8 shrink-0 sm:flex" />
      <article
        aria-busy={streaming}
        className="min-w-0 flex-1 rounded-2xl border border-line bg-surface px-4 py-4 shadow-sm sm:px-5"
      >
        {refused && (
          <div className="mb-3 flex items-center gap-2 rounded-lg border border-warning-line bg-warning-soft px-3 py-2 text-sm font-medium text-warning-ink">
            <Info aria-hidden className="size-4 shrink-0" />
            <p>{REFUSAL_LABEL}</p>
          </div>
        )}

        {streaming && !message.text && <Progress sourceCount={message.sources.length} />}

        {message.text && (
          <div className="prose-answer text-[15px] text-ink" aria-live="polite">
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
                        // The invisible ::before enlarges the click/touch target beyond the small chip.
                        className="relative mx-0.5 inline-flex h-5 min-w-5 -translate-y-0.5 items-center justify-center rounded-md bg-brand-soft px-1 align-middle text-[11px] font-semibold text-brand-ink transition-colors before:absolute before:-inset-2 before:content-[''] hover:bg-brand hover:text-on-brand"
                      >
                        {children}
                      </button>
                    );
                  }
                  return (
                    <a href={href} target="_blank" rel="noreferrer" className="text-brand underline underline-offset-2">
                      {children}
                    </a>
                  );
                },
              }}
            >
              {markdown}
            </Markdown>
            {streaming && (
              <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse rounded-sm bg-brand/60 align-middle" />
            )}
          </div>
        )}

        {message.status === "stopped" && (
          <p className="mt-2 text-sm text-ink-faint italic">{message.text ? "Stopped." : "Stopped before the answer started."}</p>
        )}

        {message.status === "error" && message.error && (
          <div
            role="alert"
            className="mt-2 flex items-start gap-2 rounded-lg border border-danger-line bg-danger-soft p-3 text-sm text-danger-ink"
          >
            <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
            <div>
              <p>{message.error.message}</p>
              <button
                type="button"
                onClick={() => onRetry(message.question)}
                className="mt-1.5 inline-flex items-center gap-1 font-medium underline underline-offset-2"
              >
                <RotateCcw aria-hidden className="size-3.5" />
                Try again
              </button>
            </div>
          </div>
        )}

        <CitationList messageId={message.id} citations={citations} highlighted={highlighted} />

        {(result || message.status === "stopped") && (
          <footer className="mt-3 flex items-center gap-1 text-xs text-ink-faint">
            {message.text && <CopyButton text={stripCitations(message.text)} />}
            <button
              type="button"
              onClick={() => onRetry(message.question)}
              className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 hover:bg-subtle hover:text-ink"
            >
              <RotateCcw aria-hidden className="size-3.5" />
              Regenerate
            </button>
            {result && (
              <span className="ml-auto">
                {result.provider ? `${modelName(result.model)} · ` : ""}
                {(result.timings.total_ms / 1000).toFixed(1)} s
              </span>
            )}
          </footer>
        )}
      </article>
    </div>
  );
}

/** Retrieval → generation steps, with elapsed time (local models can take a minute). */
function Progress({ sourceCount }: { sourceCount: number }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);

  const found = sourceCount > 0;
  const steps = [
    { label: "Searching the knowledge base", done: found },
    ...(found
      ? [
          { label: `Found ${sourceCount} relevant section${sourceCount > 1 ? "s" : ""}`, done: true },
          { label: "Writing the answer", done: false },
        ]
      : []),
  ];
  return (
    <div role="status" className="text-sm text-ink-muted">
      <ol className="space-y-1.5">
        {steps.map((s) => (
          <li key={s.label} className="flex items-center gap-2">
            {s.done ? (
              <CircleCheck aria-hidden className="size-4 text-success-ink" />
            ) : (
              <LoaderCircle aria-hidden className="size-4 animate-spin text-brand" />
            )}
            <span className={s.done ? "" : "text-ink"}>{s.label}</span>
          </li>
        ))}
      </ol>
      {seconds >= 3 && <p className="mt-2 pl-6 text-xs text-ink-faint">{seconds} s</p>}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button
      type="button"
      onClick={copy}
      className="inline-flex h-8 items-center gap-1.5 rounded-md px-2 hover:bg-subtle hover:text-ink"
    >
      {copied ? <Check aria-hidden className="size-3.5 text-success-ink" /> : <Copy aria-hidden className="size-3.5" />}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}
