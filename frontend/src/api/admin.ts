// Admin API (/api/v1/admin/*). Mirrors backend/app/api/v1/admin/*.py. Every call needs the
// ADMIN_TOKEN, sent as a Bearer token.
import { toApiError } from "./client";
import type { Citation } from "./types";

const BASE = "/api/v1/admin";

export type AdminSession = { history_enabled: boolean; history_retention_days: number };

export type TurnSummary = {
  created_at: string;
  conversation_id: string;
  message_id: string;
  question: string;
  refused: boolean;
  refusal_reason: string | null;
  provider: string | null;
  model: string | null;
  sources: number;
  total_ms: number;
};

export type TurnDetail = Omit<TurnSummary, "sources"> & {
  answer: string;
  citations: Citation[];
  language: string | null;
  stop_reason: string | null;
  top_score: number;
  sources_used: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  embed_ms: number;
  search_ms: number;
  ttft_ms: number | null;
  generation_ms: number;
  total_ms: number;
};

export type HistoryPage = { items: TurnSummary[]; total: number; limit: number; offset: number };

export type HistoryQuery = {
  q?: string;
  provider?: string; // "ollama" | "anthropic" | "none"
  refused?: boolean;
  from?: string; // YYYY-MM-DD
  to?: string;
  limit?: number;
  offset?: number;
};

function query(params: HistoryQuery): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function adminFetch(token: string, path: string): Promise<Response> {
  const response = await fetch(`${BASE}${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!response.ok) throw await toApiError(response);
  return response;
}

export const getAdminSession = async (token: string) =>
  (await (await adminFetch(token, "/session")).json()) as AdminSession;

export const listHistory = async (token: string, params: HistoryQuery) =>
  (await (await adminFetch(token, `/history${query(params)}`)).json()) as HistoryPage;

export const getTurn = async (token: string, messageId: string) =>
  (await (await adminFetch(token, `/history/${encodeURIComponent(messageId)}`)).json()) as TurnDetail;

/** The CSV file for the current filters (downloaded via a blob, since it needs the token). */
export const exportHistory = async (token: string, params: HistoryQuery) =>
  (await adminFetch(token, `/history/export.csv${query({ ...params, limit: undefined, offset: undefined })}`)).blob();

export type DayCount = { day: string; answered: number; refused: number };
export type ModelStats = {
  provider: string | null;
  model: string | null;
  questions: number;
  refused: number;
  p50_ms: number | null;
  p95_ms: number | null;
  ttft_p50_ms: number | null;
};
export type SourceCount = { doc_id: string; title: string; section: string | null; citations: number };
export type RefusedQuestion = { created_at: string; message_id: string; question: string; reason: string | null };

export type UsageStats = {
  date_from: string;
  date_to: string;
  questions: number;
  answered: number;
  refused: number;
  conversations: number;
  refused_by_reason: Record<string, number>;
  p50_ms: number | null;
  per_day: DayCount[];
  per_model: ModelStats[];
  top_documents: SourceCount[];
  top_sections: SourceCount[];
  recent_refused: RefusedQuestion[];
};

export const getStats = async (token: string, range: { from: string; to: string }) =>
  (await (await adminFetch(token, `/stats${query(range)}`)).json()) as UsageStats;
