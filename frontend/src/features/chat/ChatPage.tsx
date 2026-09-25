import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { getHealth, getProviders } from "../../api/client";
import type { Health, Provider } from "../../api/types";
import { AssistantBubble } from "./AssistantBubble";
import { useChat } from "./useChat";

const EXAMPLES = [
  "Which plans support SCIM user provisioning?",
  "How should a client handle HTTP 429 responses?",
  "What happens to customer data after the contract ends?",
];
const MAX_CHARS = 4000;

export function ChatPage() {
  const { messages, busy, ask, newConversation } = useChat();
  const [draft, setDraft] = useState("");
  const [providers, setProviders] = useState<Provider[]>([]);
  const [provider, setProvider] = useState<string>("");
  const [health, setHealth] = useState<Health | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getProviders()
      .then((r) => {
        setProviders(r.providers);
        setProvider(r.default);
      })
      .catch(() => setProviders([]));
  }, []);

  // Poll health until the knowledge base is ready (the index can take minutes to build).
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const poll = () =>
      getHealth()
        .then((h) => {
          setHealth(h);
          if (!h.ready) timer = setTimeout(poll, 5000);
        })
        .catch(() => (timer = setTimeout(poll, 5000)));
    poll();
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messages]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!draft.trim() || busy) return;
    void ask(draft, provider || undefined);
    setDraft("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) submit(e);
  };

  return (
    <div className="flex h-dvh flex-col bg-slate-50">
      <header className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-4 py-3">
        <div className="flex-1">
          <h1 className="text-lg font-semibold text-slate-900">OmniCorp Knowledge Base Assistant</h1>
          <p className="text-xs text-slate-500">
            Answers only from internal documentation, with sources.
          </p>
        </div>
        <StatusDot health={health} />
        {providers.length > 0 && (
          <label className="flex items-center gap-2 text-sm text-slate-600">
            Model
            <select
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
              className="rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
            >
              {providers.map((p) => (
                <option key={p.name} value={p.name} disabled={!p.available} title={p.detail ?? ""}>
                  {p.name} {p.model ? `(${p.model})` : ""} {p.available ? "" : "– unavailable"}
                </option>
              ))}
            </select>
          </label>
        )}
        <button
          type="button"
          onClick={newConversation}
          className="rounded-md border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-100"
        >
          New conversation
        </button>
      </header>

      <main className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex max-w-3xl flex-col gap-4">
          {messages.length === 0 && (
            <div className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-slate-600">
              <p className="font-medium">Ask a question about OmniCorp products and policies.</p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {EXAMPLES.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => void ask(q, provider || undefined)}
                    disabled={busy}
                    className="rounded-full border border-slate-300 bg-white px-3 py-1 text-sm hover:bg-slate-100"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m) =>
            m.role === "user" ? (
              <div key={m.id} className="ml-auto max-w-2xl rounded-lg bg-indigo-600 px-4 py-2 text-white">
                {m.text}
              </div>
            ) : (
              <AssistantBubble key={m.id} message={m} onRetry={(q) => void ask(q, provider || undefined)} />
            ),
          )}
          <div ref={endRef} />
        </div>
      </main>

      <form onSubmit={submit} className="border-t border-slate-200 bg-white px-4 py-3">
        <div className="mx-auto flex max-w-3xl items-end gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            maxLength={MAX_CHARS}
            rows={2}
            placeholder="Ask a question… (Enter to send, Shift+Enter for a new line)"
            aria-label="Your question"
            className="flex-1 resize-none rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={busy || !draft.trim()}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? "Answering…" : "Send"}
          </button>
        </div>
      </form>
    </div>
  );
}

function StatusDot({ health }: { health: Health | null }) {
  const [color, label] = !health
    ? ["bg-slate-300", "Connecting…"]
    : !health.ready
      ? health.index.error
        ? ["bg-red-500", "Knowledge base failed to load"]
        : ["bg-amber-400", "Knowledge base loading…"]
      : health.status === "ok"
        ? ["bg-green-500", `Ready · ${health.index.documents} documents`]
        : ["bg-amber-400", "Degraded"];
  return (
    <span className="flex items-center gap-1.5 text-xs text-slate-500" title={health?.index.error ?? label}>
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {label}
    </span>
  );
}
