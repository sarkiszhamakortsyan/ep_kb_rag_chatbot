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
