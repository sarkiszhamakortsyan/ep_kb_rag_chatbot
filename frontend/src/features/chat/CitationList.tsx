import type { Citation } from "../../api/types";
import { citationAnchor } from "./citations";

type Props = { messageId: string; citations: Citation[]; highlighted: number | null };

export function CitationList({ messageId, citations, highlighted }: Props) {
  if (citations.length === 0) return null;
  return (
    <section aria-label="Sources" className="mt-3 border-t border-slate-200 pt-3">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Sources
      </h3>
      <ol className="space-y-2">
        {citations.map((c) => (
          <li
            key={c.number}
            id={citationAnchor(messageId, c.number)}
            className={`rounded-md border p-2 text-sm transition-colors ${
              highlighted === c.number ? "border-indigo-400 bg-indigo-50" : "border-slate-200 bg-white"
            }`}
          >
            <details>
              <summary className="flex cursor-pointer list-none items-start gap-2">
                <span className="mt-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded bg-indigo-100 px-1 text-xs font-semibold text-indigo-700">
                  {c.number}
                </span>
                <span className="flex-1">
                  <span className="font-medium text-slate-800">{c.title}</span>
                  {c.section && <span className="text-slate-500"> › {c.section}</span>}
                  <span className="ml-2 text-xs text-slate-400" title="Similarity to the question">
                    {Math.round(c.score * 100)}% match
                  </span>
                </span>
              </summary>
              <p className="mt-2 whitespace-pre-line pl-7 text-slate-600">{c.snippet}</p>
              <p className="mt-1 pl-7 text-xs text-slate-400">
                {c.doc_id} · {c.chunk_id}
              </p>
            </details>
          </li>
        ))}
      </ol>
    </section>
  );
}
