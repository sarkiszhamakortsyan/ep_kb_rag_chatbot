// Mirrors backend/app/api/schemas.py (API v1). Keep both sides in sync.

export type Citation = {
  number: number; // the [n] marker used in the answer
  chunk_id: string;
  doc_id: string;
  title: string;
  section: string;
  snippet: string;
  score: number;
};

export type RefusalReason = "low_score" | "no_citations" | "model_refusal";

export type Usage = {
  input_tokens: number;
  output_tokens: number;
  cache_read_input_tokens: number;
  cache_creation_input_tokens: number;
};

export type Timings = {
  embed_ms: number;
  search_ms: number;
  time_to_first_token_ms: number | null;
  generation_ms: number;
  total_ms: number;
};

export type ChatResponse = {
  conversation_id: string;
  message_id: string;
  answer: string;
  citations: Citation[];
  refused: boolean;
  refusal_reason: RefusalReason | null;
  provider: string | null;
  model: string | null;
  usage: Usage;
  timings: Timings;
  top_score: number;
  sources_used: number;
  stop_reason: string | null;
};

export type ChatRequest = {
  message: string;
  conversation_id?: string;
  options?: { provider?: string };
};

export type Provider = {
  name: string;
  model: string | null;
  default: boolean;
  available: boolean;
  detail: string | null;
};

export type ProvidersResponse = { default: string; providers: Provider[] };

export type Health = {
  status: "ok" | "starting" | "degraded";
  ready: boolean;
  version: string;
  llm_provider: string;
  index: { ready: boolean; documents: number | null; chunks: number | null; error: string | null };
};

export type ApiErrorBody = { error: { code: string; message: string } };

// Server-Sent Events from POST /api/v1/chat/stream
export type StreamEvent =
  | { event: "meta"; data: { conversation_id: string; message_id: string; sources: Citation[] } }
  | { event: "token"; data: { text: string } }
  | { event: "done"; data: ChatResponse }
  | { event: "error"; data: { code: string; message: string } };
