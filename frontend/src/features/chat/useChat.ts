import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, streamChat } from "../../api/client";
import type { ChatOptions, Citation, ChatResponse } from "../../api/types";

export type UserMessage = {
  id: string;
  role: "user";
  text: string;
  detailed?: boolean;
  model?: string; // set when a "/<model> question" command chose the model for this question only
};

/** A short note from the chat itself (model switched, command help), not sent to the API. */
export type NoticeMessage = {
  id: string;
  role: "notice";
  text: string;
  tone: "info" | "warning";
};

export type AssistantMessage = {
  id: string;
  role: "assistant";
  text: string;
  status: "streaming" | "done" | "error" | "stopped";
  sources: Citation[]; // candidates sent before generation (meta event)
  result?: ChatResponse; // final result (citations, refusal, usage, timings)
  error?: { code: string; message: string };
  question: string; // kept so a failed answer can be retried
  detailed?: boolean; // asked with detail="detailed"
  provider?: string; // the model provider it was asked with (a retry reuses it)
};

export type Message = UserMessage | AssistantMessage | NoticeMessage;

let counter = 0;
const localId = () => `local-${Date.now()}-${++counter}`;

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const update = (
    id: string,
    change: (m: AssistantMessage) => AssistantMessage,
  ) =>
    setMessages((all) =>
      all.map((m) => (m.id === id && m.role === "assistant" ? change(m) : m)),
    );

  const ask = useCallback(
    async (
      question: string,
      options: ChatOptions = {},
      modelLabel?: string,
    ) => {
      const text = question.trim();
      if (!text || busy) return;
      const controller = new AbortController();
      abortRef.current = controller;
      const answerId = localId();
      setBusy(true);
      const detailed = options.detail === "detailed";
      setMessages((all) => [
        ...all,
        { id: localId(), role: "user", text, detailed, model: modelLabel },
        {
          id: answerId,
          role: "assistant",
          text: "",
          status: "streaming",
          sources: [],
          question: text,
          detailed,
          provider: options.provider,
        },
      ]);

      try {
        const request = {
          message: text,
          conversation_id: conversationId,
          options,
        };
        for await (const event of streamChat(request, controller.signal)) {
          if (event.event === "meta") {
            setConversationId(event.data.conversation_id);
            update(answerId, (m) => ({ ...m, sources: event.data.sources }));
          } else if (event.event === "token") {
            update(answerId, (m) => ({ ...m, text: m.text + event.data.text }));
          } else if (event.event === "done") {
            update(answerId, (m) => ({
              ...m,
              text: event.data.answer,
              status: "done",
              result: event.data,
            }));
          } else if (event.event === "error") {
            update(answerId, (m) => ({
              ...m,
              status: "error",
              error: event.data,
            }));
          }
        }
        // A stream that ends without `done` or `error` was cut off.
        update(answerId, (m) =>
          m.status === "streaming"
            ? {
                ...m,
                status: "error",
                error: {
                  code: "stream_interrupted",
                  message: "The answer was interrupted. Please try again.",
                },
              }
            : m,
        );
      } catch (err) {
        if (controller.signal.aborted) return;
        const error =
          err instanceof ApiError
            ? { code: err.code, message: err.message }
            : {
                code: "network_error",
                message: "Could not reach the server. Is the backend running?",
              };
        update(answerId, (m) => ({ ...m, status: "error", error }));
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        setBusy(false);
      }
    },
    [busy, conversationId],
  );

  // Stops the answer being generated and keeps the text streamed so far.
  const stop = useCallback(() => {
    abortRef.current?.abort();
    setMessages((all) =>
      all.map((m) =>
        m.role === "assistant" && m.status === "streaming"
          ? { ...m, status: "stopped" }
          : m,
      ),
    );
    setBusy(false);
  }, []);

  const newConversation = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
    setConversationId(undefined);
    setBusy(false);
  }, []);

  const addNotice = useCallback(
    (text: string, tone: NoticeMessage["tone"] = "info") => {
      setMessages((all) => [
        ...all,
        { id: localId(), role: "notice", text, tone },
      ]);
    },
    [],
  );

  return {
    messages,
    conversationId,
    busy,
    ask,
    stop,
    newConversation,
    addNotice,
  };
}
