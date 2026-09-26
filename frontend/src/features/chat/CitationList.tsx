import { ChevronDown, FileText } from "lucide-react";
import type { Citation } from "../../api/types";
import { citationAnchor, relevance, RELEVANCE_LABEL, type Relevance } from "./citations";

const RELEVANCE_STYLE: Record<Relevance, string> = {
  strong: "bg-success-soft text-success-ink",
  good: "bg-brand-soft text-brand-ink",
  related: "bg-subtle text-ink-muted",
};

type Props = { messageId: string; citations: Citation[]; highlighted: number | null };

export function CitationList({ messageId, citations, highlighted }: Props) {
  if (citations.length === 0) return null;
  return (
    <section aria-label="Sources" className="mt-4 border-t border-line pt-4">
      <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold tracking-wide text-ink-muted uppercase">
        Sources
        <span className="rounded-full bg-subtle px-1.5 py-0.5 text-[11px] font-medium text-ink-faint normal-case">
          {citations.length}
        </span>
      </h3>
      <ol className="space-y-2">
        {citations.map((c) => {
          const level = relevance(c.score);
          return (
            <li
              key={c.number}
              id={citationAnchor(messageId, c.number)}
              title={`${c.doc_id} · ${c.chunk_id}`}
              className={`rounded-xl border text-sm transition-colors ${
                highlighted === c.number
                  ? "border-brand bg-brand-soft/60 ring-2 ring-brand/20"
                  : "border-line bg-surface hover:border-line-strong"
              }`}
            >
              <details className="group">
                <summary className="flex cursor-pointer list-none items-start gap-3 px-3 py-2.5 [&::-webkit-details-marker]:hidden">
                  <span className="inline-flex size-6 shrink-0 items-center justify-center rounded-md bg-brand-soft text-xs font-semibold text-brand-ink">
                    {c.number}
                  </span>
                  <FileText aria-hidden className="mt-1 hidden size-4 shrink-0 text-ink-faint sm:block" />
                  <span className="min-w-0 flex-1">
                    <span className="block font-medium text-ink">{c.title}</span>
                    <span className="mt-0.5 flex items-center gap-2">
                      {c.section && <span className="min-w-0 truncate text-xs text-ink-faint">{c.section}</span>}
                      <span
                        className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap ${RELEVANCE_STYLE[level]}`}
                        title={`Similarity to the question: ${c.score.toFixed(2)}`}
                      >
                        {RELEVANCE_LABEL[level]}
                      </span>
                    </span>
                  </span>
                  <ChevronDown
                    aria-hidden
                    className="mt-1 size-4 shrink-0 text-ink-faint transition-transform group-open:rotate-180"
                  />
                </summary>
                <p className="mx-3 mb-3 border-l-2 border-line-strong pl-3 leading-relaxed whitespace-pre-line text-ink-muted">
                  {c.snippet}
                </p>
              </details>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
