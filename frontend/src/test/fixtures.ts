import type { ChatResponse, Citation } from "../api/types";

export const citation = (n: number, overrides: Partial<Citation> = {}): Citation => ({
  number: n,
  chunk_id: `kb-00${n}#001`,
  doc_id: `kb-00${n}`,
  title: `Guide ${n}`,
  section: `Section ${n}`,
  snippet: `Snippet text ${n}.`,
  score: 0.61,
  ...overrides,
});

export const chatResponse = (overrides: Partial<ChatResponse> = {}): ChatResponse => ({
  conversation_id: "conv1",
  message_id: "msg1",
  answer: "Backups are retained for 35 days [1].",
  citations: [citation(1)],
  refused: false,
  refusal_reason: null,
  provider: "anthropic",
  model: "claude-opus-5",
  usage: { input_tokens: 1000, output_tokens: 50, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 },
  timings: { embed_ms: 700, search_ms: 1, time_to_first_token_ms: 2300, generation_ms: 3000, total_ms: 4200 },
  top_score: 0.68,
  sources_used: 3,
  stop_reason: "end_turn",
  ...overrides,
});

export const sse = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

/** A fetch Response whose body arrives in the given chunks. */
export function streamResponse(chunks: string[], status = 200): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status, headers: { "Content-Type": "text/event-stream" } });
}

export const jsonResponse = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
