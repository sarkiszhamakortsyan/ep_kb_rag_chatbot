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

export type Relevance = "high" | "medium" | "low";

/**
 * Cosine similarity is not a percentage of correctness: with embeddinggemma a correct top
 * match usually scores 0.55–0.75. Thresholds are calibrated on the evaluation set
 * (documentation/evaluation.md); questions below MIN_SCORE (0.35) never reach the UI.
 */
export function relevance(score: number): Relevance {
  if (score >= 0.55) return "high";
  if (score >= 0.45) return "medium";
  return "low";
}
