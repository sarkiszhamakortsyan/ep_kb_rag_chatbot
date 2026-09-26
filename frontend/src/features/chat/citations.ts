// Same marker syntax the backend parses (app/rag/citations.py): [1], [2, 3], [1][3].
const MARKER = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

export const citationAnchor = (messageId: string, n: number) => `cite-${messageId}-${n}`;

/**
 * Turns [n] markers into Markdown links (#cite-<message>-<n>) so the renderer can show them
 * as clickable chips. Numbers without a matching source are left as plain text.
 */
export function linkCitations(answer: string, messageId: string, known: Set<number>): string {
  return answer.replace(MARKER, (whole, group: string) => {
    const numbers = group.split(",").map((n) => Number(n.trim()));
    if (!numbers.every((n) => known.has(n))) return whole;
    return numbers.map((n) => `[${n}](#${citationAnchor(messageId, n)})`).join("");
  });
}

export type Relevance = "strong" | "good" | "related";

/**
 * Cosine similarity is not a percentage of correctness: with embeddinggemma a correct top
 * match usually scores 0.55–0.75, and correctly used sources can score below 0.45.
 * Every source shown is cited by the answer, so the levels are deliberately never negative.
 * Thresholds are calibrated on the evaluation set (documentation/evaluation.md).
 */
export function relevance(score: number): Relevance {
  if (score >= 0.55) return "strong";
  if (score >= 0.4) return "good";
  return "related";
}

export const RELEVANCE_LABEL: Record<Relevance, string> = {
  strong: "strong match",
  good: "good match",
  related: "related",
};

/** Answer text without [n] markers, for pasting into e-mails or tickets. */
export function stripCitations(answer: string): string {
  return answer.replace(/[ \t]?\[\d+(?:\s*,\s*\d+)*\]/g, "");
}
