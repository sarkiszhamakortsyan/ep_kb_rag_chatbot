import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, streamChat } from "../../api/client";
import type { Citation, ChatResponse } from "../../api/types";

export type UserMessage = { id: string; role: "user"; text: string };

export type AssistantMessage = {
  id: string;
  role: "assistant";
  text: string;
  status: "streaming" | "done" | "error";
  sources: Citation[]; // candidates sent before generation (meta event)
  result?: ChatResponse; // final result (citations, refusal, usage, timings)
  error?: { code: string; message: string };
  question: string; // kept so a failed answer can be retried
};

export type Message = UserMessage | AssistantMessage;

let counter = 0;
const localId = () => `local-${Date.now()}-${++counter}`;

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const update = (id: string, change: (m: AssistantMessage) => AssistantMessage) =>
    setMessages((all) =>
      all.map((m) => (m.id === id && m.role === "assistant" ? change(m) : m)),
    );

  const ask = useCallback(
    async (question: string, provider?: string) => {
      const text = question.trim();
      if (!text || busy) return;
      const controller = new AbortController();
      abortRef.current = controller;
      const answerId = localId();
      setBusy(true);
      setMessages((all) => [
        ...all,
        { id: localId(), role: "user", text },
        { id: answerId, role: "assistant", text: "", status: "streaming", sources: [], question: text },
      ]);

      try {
        const request = { message: text, conversation_id: conversationId, options: { provider } };
        for await (const event of streamChat(request, controller.signal)) {
          if (event.event === "meta") {
            setConversationId(event.data.conversation_id);
            update(answerId, (m) => ({ ...m, sources: event.data.sources }));
          } else if (event.event === "token") {
            update(answerId, (m) => ({ ...m, text: m.text + event.data.text }));
          } else if (event.event === "done") {
            update(answerId, (m) => ({ ...m, text: event.data.answer, status: "done", result: event.data }));
          } else if (event.event === "error") {
            update(answerId, (m) => ({ ...m, status: "error", error: event.data }));
          }
        }
        // A stream that ends without `done` or `error` was cut off.
        update(answerId, (m) =>
          m.status === "streaming"
            ? { ...m, status: "error", error: { code: "stream_interrupted", message: "The answer was interrupted. Please try again." } }
            : m,
        );
      } catch (err) {
        if (controller.signal.aborted) return;
        const error =
          err instanceof ApiError
            ? { code: err.code, message: err.message }
            : { code: "network_error", message: "Could not reach the server. Is the backend running?" };
        update(answerId, (m) => ({ ...m, status: "error", error }));
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        setBusy(false);
      }
    },
    [busy, conversationId],
  );

  const newConversation = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setConversationId(undefined);
    setBusy(false);
  }, []);

  return { messages, conversationId, busy, ask, newConversation };
}
