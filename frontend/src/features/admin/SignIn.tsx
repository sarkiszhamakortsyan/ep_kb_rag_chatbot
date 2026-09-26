import { useState, type FormEvent } from "react";
import { getAdminSession, type AdminSession } from "../../api/admin";
import { ApiError } from "../../api/client";
import { LogoMark } from "../chat/LogoMark";

type Props = {
  onSignIn: (token: string, session: AdminSession) => void;
  checking: boolean;
};

function describe(err: unknown): string {
  if (err instanceof ApiError && err.code === "admin_disabled") {
    return "The admin area is switched off. Set ADMIN_TOKEN in .env and restart the backend.";
  }
  if (err instanceof ApiError && err.code === "unauthorized")
    return "That token is not valid.";
  return "Could not reach the server.";
}

export function SignIn({ onSignIn, checking }: Props) {
  const [value, setValue] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const entered = value.trim();
    if (!entered) return;
    setBusy(true);
    setMessage(null);
    try {
      onSignIn(entered, await getAdminSession(entered));
    } catch (err) {
      setMessage(describe(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas px-4">
      <form
        onSubmit={(e) => void submit(e)}
        className="w-full max-w-sm rounded-2xl border border-line bg-surface p-6 shadow-sm"
      >
        <LogoMark className="mb-4 size-10" />
        <h1 className="text-lg font-semibold text-ink">Admin sign-in</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Enter the admin token configured on the server.
        </p>
        <label
          className="mt-5 block text-sm font-medium text-ink"
          htmlFor="admin-token"
        >
          Admin token
        </label>
        <input
          id="admin-token"
          type="password"
          autoComplete="current-password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className="mt-1.5 h-10 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink focus:border-brand focus:ring-4 focus:ring-brand/15 focus:outline-none"
        />
        {message && (
          <p role="alert" className="mt-3 text-sm text-danger-ink">
            {message}
          </p>
        )}
        <button
          type="submit"
          disabled={busy || checking || !value.trim()}
          className="mt-5 h-10 w-full rounded-lg bg-brand text-sm font-medium text-on-brand hover:bg-brand-strong disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy || checking ? "Checking…" : "Sign in"}
        </button>
        <a
          href="/"
          className="mt-4 block text-center text-sm text-ink-muted underline-offset-2 hover:underline"
        >
          Back to the chat
        </a>
      </form>
    </div>
  );
}
