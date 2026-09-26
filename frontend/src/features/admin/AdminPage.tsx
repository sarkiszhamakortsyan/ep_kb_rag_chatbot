import { ArrowLeft, History, LogOut, type LucideIcon } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { getAdminSession, type AdminSession } from "../../api/admin";
import { LogoMark } from "../chat/LogoMark";
import { HistoryTab } from "./HistoryTab";
import { SignIn } from "./SignIn";

// The token is kept for this browser tab only (sessionStorage), never in localStorage.
const TOKEN_KEY = "omnicorp-admin-token";

function readToken(): string {
  try {
    return sessionStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

function storeToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage blocked (private mode): the user signs in again on reload.
  }
}

type Tab = { id: string; label: string; icon: LucideIcon };
const TABS: Tab[] = [{ id: "history", label: "History", icon: History }];

/** Hidden admin area (/admin, or Ctrl+Shift+A in the chat). The ADMIN_TOKEN protects the data. */
export function AdminPage() {
  const [token, setToken] = useState(readToken);
  const [session, setSession] = useState<AdminSession | null>(null);
  const [tab] = useState("history");

  // A stored token is re-checked on load; an invalid one sends the user back to sign-in.
  useEffect(() => {
    if (!token || session) return;
    getAdminSession(token)
      .then(setSession)
      .catch(() => {
        storeToken(null);
        setToken("");
      });
  }, [token, session]);

  const signIn = (newToken: string, newSession: AdminSession) => {
    storeToken(newToken);
    setToken(newToken);
    setSession(newSession);
  };
  const signOut = useCallback(() => {
    storeToken(null);
    setToken("");
    setSession(null);
  }, []);

  if (!token || !session) return <SignIn onSignIn={signIn} checking={Boolean(token)} />;

  return (
    <div className="flex min-h-dvh flex-col bg-canvas">
      <header className="sticky top-0 z-10 border-b border-line bg-surface/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4">
          <LogoMark className="size-8 shrink-0" />
          <h1 className="text-[15px] font-semibold text-ink">
            OmniCorp <span className="font-normal text-ink-muted">Admin</span>
          </h1>
          <nav aria-label="Admin sections" className="ml-4 flex gap-1">
            {TABS.map(({ id, label, icon: Icon }) => (
              <span
                key={id}
                aria-current={tab === id ? "page" : undefined}
                className={`inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm ${
                  tab === id ? "bg-brand-soft font-medium text-brand-ink" : "text-ink-muted hover:bg-subtle"
                }`}
              >
                <Icon aria-hidden className="size-4" />
                {label}
              </span>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <a
              href="/"
              className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm text-ink-muted hover:bg-subtle hover:text-ink"
            >
              <ArrowLeft aria-hidden className="size-4" />
              <span className="hidden sm:inline">Back to chat</span>
            </a>
            <button
              type="button"
              onClick={signOut}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line px-3 text-sm text-ink-muted hover:border-line-strong hover:text-ink"
            >
              <LogOut aria-hidden className="size-4" />
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        {session.history_enabled ? (
          <HistoryTab token={token} retentionDays={session.history_retention_days} onUnauthorized={signOut} />
        ) : (
          <p className="rounded-xl border border-line bg-surface p-6 text-sm text-ink-muted">
            The response history is switched off (<code>HISTORY_ENABLED=false</code>).
          </p>
        )}
      </main>
    </div>
  );
}
