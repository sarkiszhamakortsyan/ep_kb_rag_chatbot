import { ArrowUp, Database, Gauge, KeyRound, LifeBuoy, Square, SquarePen, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import { getHealth, getProviders } from "../../api/client";
import type { Health, Provider } from "../../api/types";
import { AssistantBubble } from "./AssistantBubble";
import { LogoMark } from "./LogoMark";
import { providerLabel } from "./providers";
import { useChat } from "./useChat";

const EXAMPLES: { topic: string; icon: LucideIcon; question: string }[] = [
  { topic: "SSO & provisioning", icon: KeyRound, question: "Which plans support SCIM user provisioning?" },
  { topic: "API limits", icon: Gauge, question: "How should a client handle HTTP 429 responses?" },
  { topic: "Data & GDPR", icon: Database, question: "What happens to customer data after the contract ends?" },
  { topic: "Support & SLA", icon: LifeBuoy, question: "How fast does support respond to a P1 ticket on Enterprise?" },
];
const MAX_CHARS = 4000;

export function ChatPage() {
  const { messages, busy, ask, stop, newConversation } = useChat();
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

  // Hidden entry to the admin area (it is protected by ADMIN_TOKEN, not by being hidden).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "a") {
        e.preventDefault();
        window.location.assign("/admin");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const send = (question: string) => void ask(question, provider || undefined);
  const empty = messages.length === 0;
  const composer = <Composer busy={busy} onSend={send} onStop={stop} autoFocus={empty} />;

  return (
    <div className="flex h-dvh flex-col bg-canvas">
      <header className="sticky top-0 z-10 border-b border-line bg-surface/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-5xl items-center gap-2 px-4 sm:gap-3">
          <LogoMark className="size-8 shrink-0" />
          <div className="min-w-0 flex-1 leading-tight">
            <h1 className="truncate text-[15px] font-semibold text-ink">
              OmniCorp <span className="hidden font-normal text-ink-muted sm:inline">Knowledge Assistant</span>
            </h1>
          </div>
          <StatusBadge health={health} />
          {providers.length > 0 && (
            <label className="flex items-center">
              <span className="sr-only">Model</span>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                title="Model used for answers"
                className="h-9 max-w-36 truncate rounded-lg border border-line bg-surface px-2 text-sm text-ink hover:border-line-strong sm:max-w-none"
              >
                {providers.map((p) => (
                  <option key={p.name} value={p.name} disabled={!p.available} title={p.detail ?? ""}>
                    {providerLabel(p)}
                  </option>
                ))}
              </select>
            </label>
          )}
          <button
            type="button"
            onClick={newConversation}
            aria-label="New conversation"
            title="New conversation"
            className="inline-flex size-9 shrink-0 items-center justify-center rounded-lg border border-line text-ink-muted hover:border-line-strong hover:bg-subtle hover:text-ink"
          >
            <SquarePen aria-hidden className="size-4" />
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto">
        {empty ? (
          <Welcome busy={busy} onPick={send}>
            {composer}
          </Welcome>
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6">
            {messages.map((m) =>
              m.role === "user" ? (
                <div
                  key={m.id}
                  className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-brand-soft px-4 py-2.5 whitespace-pre-wrap text-brand-ink"
                >
                  {m.text}
                </div>
              ) : (
                <AssistantBubble key={m.id} message={m} onRetry={send} />
              ),
            )}
            <div ref={endRef} />
          </div>
        )}
      </main>

      {!empty && (
        <div className="mx-auto w-full max-w-3xl px-4 pt-2 pb-[max(0.75rem,env(safe-area-inset-bottom))]">{composer}</div>
      )}
    </div>
  );
}

function Welcome({ busy, onPick, children }: { busy: boolean; onPick: (q: string) => void; children: ReactNode }) {
  return (
    <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center px-4 py-10">
      <div className="mb-8 text-center">
        <LogoMark className="mx-auto mb-4 size-12" />
        <h2 className="text-xl font-semibold tracking-tight text-ink sm:text-2xl">
          Ask a question about OmniCorp products and policies.
        </h2>
        <p className="mt-2 text-sm text-ink-muted">
          Plans, SSO, API limits, data retention and support, with a source for every fact.
        </p>
      </div>
      {children}
      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        {EXAMPLES.map(({ topic, icon: Icon, question }) => (
          <button
            key={question}
            type="button"
            onClick={() => onPick(question)}
            disabled={busy}
            className="group flex items-start gap-3 rounded-xl border border-line bg-surface p-3.5 text-left shadow-sm transition hover:-translate-y-px hover:border-brand/40 hover:shadow-md disabled:opacity-50"
          >
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-subtle text-ink-muted group-hover:bg-brand-soft group-hover:text-brand-ink">
              <Icon aria-hidden className="size-4" />
            </span>
            <span>
              <span className="block text-xs font-medium text-ink-faint">{topic}</span>
              <span className="block text-sm text-ink">{question}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

type ComposerProps = { busy: boolean; onSend: (q: string) => void; onStop: () => void; autoFocus: boolean };

function Composer({ busy, onSend, onStop, autoFocus }: ComposerProps) {
  const [draft, setDraft] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // Grow with the text, up to a limit (then it scrolls).
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [draft]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!draft.trim() || busy) return;
    onSend(draft);
    setDraft("");
  };
  const onKeyDown = (e: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) submit(e);
  };

  return (
    <form onSubmit={submit} className="w-full">
      <div className="flex items-end gap-2 rounded-2xl border border-line-strong bg-surface p-2 shadow-sm transition focus-within:border-brand focus-within:ring-4 focus-within:ring-brand/15">
        <textarea
          ref={ref}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          maxLength={MAX_CHARS}
          rows={1}
          autoFocus={autoFocus}
          placeholder="Ask a question…"
          aria-label="Your question"
          className="max-h-[200px] min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] text-ink placeholder:text-ink-faint focus:outline-none focus-visible:outline-none"
        />
        {busy ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop generating"
            title="Stop generating"
            className="inline-flex size-10 shrink-0 items-center justify-center rounded-xl bg-ink text-canvas hover:opacity-85"
          >
            <Square aria-hidden className="size-3.5 fill-current" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!draft.trim()}
            aria-label="Send"
            title="Send (Enter)"
            className="inline-flex size-10 shrink-0 items-center justify-center rounded-xl bg-brand text-on-brand hover:bg-brand-strong disabled:cursor-not-allowed disabled:bg-subtle disabled:text-ink-faint"
          >
            <ArrowUp aria-hidden className="size-5" strokeWidth={2.25} />
          </button>
        )}
      </div>
      <p className="mt-2 text-center text-xs text-ink-faint">
        Answers come only from internal documentation. Check them before sharing with customers.
        <span className="hidden sm:inline"> Shift+Enter for a new line.</span>
      </p>
    </form>
  );
}

function StatusBadge({ health }: { health: Health | null }) {
  const [dot, label] = !health
    ? ["bg-line-strong", "Connecting…"]
    : !health.ready
      ? health.index.error
        ? ["bg-danger-ink", "Knowledge base failed to load"]
        : ["bg-warning-ink animate-pulse", "Knowledge base loading…"]
      : health.status === "ok"
        ? ["bg-success-ink", `Ready · ${health.index.documents} documents`]
        : ["bg-warning-ink", "Degraded"];
  return (
    <span
      className="flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs text-ink-muted"
      title={health?.index.error ?? label}
    >
      <span className={`size-2 rounded-full ${dot}`} />
      <span className="sr-only md:not-sr-only">{label}</span>
    </span>
  );
}
