import { SseParser } from "./sse";
import type {
  ApiErrorBody,
  ChatRequest,
  ChatResponse,
  Health,
  ProvidersResponse,
  StreamEvent,
} from "./types";

const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as ApiErrorBody;
    return new ApiError(response.status, body.error.code, body.error.message);
  } catch {
    return new ApiError(response.status, "http_error", `Request failed (HTTP ${response.status})`);
  }
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`);
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as T;
}

export const getHealth = () => getJson<Health>("/health");
export const getProviders = () => getJson<ProvidersResponse>("/providers");

export async function chat(request: ChatRequest): Promise<ChatResponse> {
  const response = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as ChatResponse;
}

/**
 * Streams an answer. Errors before the stream starts (validation, provider config,
 * index loading) throw ApiError; errors during the stream arrive as an `error` event.
 */
export async function* streamChat(
  request: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(request),
    signal,
  });
  if (!response.ok) throw await toApiError(response);
  if (!response.body) throw new ApiError(0, "no_body", "The server returned an empty stream");

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  const parser = new SseParser();
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      yield* parser.push(value);
    }
  } finally {
    reader.releaseLock();
  }
}
