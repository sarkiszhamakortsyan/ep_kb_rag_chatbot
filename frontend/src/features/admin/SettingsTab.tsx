import { Check, Cpu } from "lucide-react";
import { useEffect, useState } from "react";
import {
  getAdminSettings,
  updateAdminSettings,
  type AdminSettings,
} from "../../api/admin";
import { ApiError } from "../../api/client";
import { modelName } from "../chat/providers";
import { Card } from "./ui";

type Draft = { enabled: string[]; default: string };

const toDraft = (s: AdminSettings): Draft => ({
  enabled: s.providers.filter((p) => p.enabled).map((p) => p.name),
  default: s.providers.find((p) => p.default)?.name ?? "",
});

function problem(draft: Draft): string | null {
  if (draft.enabled.length === 0) return "Keep at least one model enabled.";
  if (!draft.enabled.includes(draft.default))
    return "The default model must be enabled.";
  return null;
}

type Props = { token: string; onUnauthorized: () => void };

/** Switch model providers on/off and choose the default, without restarting (ideas.md #7). */
export function SettingsTab({ token, onUnauthorized }: Props) {
  const [settings, setSettings] = useState<AdminSettings | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getAdminSettings(token)
      .then((s) => {
        if (cancelled) return;
        setSettings(s);
        setDraft(toDraft(s));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) onUnauthorized();
        else
          setError(
            err instanceof Error ? err.message : "Could not load the settings.",
          );
      });
    return () => {
      cancelled = true;
    };
  }, [token, onUnauthorized]);

  const toggle = (name: string) => {
    if (!draft) return;
    const enabled = draft.enabled.includes(name)
      ? draft.enabled.filter((n) => n !== name)
      : [...draft.enabled, name];
    setDraft({ ...draft, enabled });
    setSaved(false);
  };

  const save = async () => {
    if (!draft) return;
    try {
      const updated = await updateAdminSettings(token, {
        enabled_providers: draft.enabled,
        default_provider: draft.default,
      });
      setSettings(updated);
      setDraft(toDraft(updated));
      setSaved(true);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not save the settings.",
      );
    }
  };

  const invalid = draft ? problem(draft) : null;
  const changed =
    settings &&
    draft &&
    JSON.stringify(toDraft(settings)) !== JSON.stringify(draft);

  return (
    <section aria-labelledby="settings-title">
      <div className="mb-4">
        <h2 id="settings-title" className="text-xl font-semibold text-ink">
          Settings
        </h2>
        <p className="mt-1 text-sm text-ink-muted">
          Changes apply immediately and are kept after a restart.
        </p>
      </div>

      {error && (
        <p
          role="alert"
          className="mb-3 rounded-lg border border-danger-line bg-danger-soft p-3 text-sm text-danger-ink"
        >
          {error}
        </p>
      )}

      {settings && draft && (
        <div className="space-y-4">
          <Card
            title="Answer models"
            subtitle="Only models allowed in the server configuration (ENABLED_LLM_PROVIDERS) are listed."
          >
            <ul className="divide-y divide-line">
              {settings.providers.map((p) => {
                const on = draft.enabled.includes(p.name);
                return (
                  <li
                    key={p.name}
                    className="flex flex-wrap items-center gap-3 py-3"
                  >
                    <label className="flex flex-1 cursor-pointer items-center gap-3">
                      <input
                        type="checkbox"
                        role="switch"
                        checked={on}
                        onChange={() => toggle(p.name)}
                        aria-label={`Enable ${modelName(p.model)}`}
                        className="peer sr-only"
                      />
                      <span
                        aria-hidden
                        className={`relative h-5 w-9 shrink-0 rounded-full transition-colors peer-focus-visible:outline-2 peer-focus-visible:outline-brand ${
                          on ? "bg-brand" : "bg-line-strong"
                        }`}
                      >
                        <span
                          className={`absolute top-0.5 size-4 rounded-full bg-surface shadow transition-transform ${
                            on ? "translate-x-4.5" : "translate-x-0.5"
                          }`}
                        />
                      </span>
                      <span>
                        <span className="block text-sm font-medium text-ink">
                          {modelName(p.model)}
                        </span>
                        <span className="block text-xs text-ink-faint">
                          {p.name === "ollama"
                            ? "Local, private, free"
                            : "Cloud, fast, paid per question"}{" "}
                          · {p.model}
                        </span>
                      </span>
                    </label>
                    <label className="flex items-center gap-2 text-sm text-ink-muted">
                      <input
                        type="radio"
                        name="default"
                        checked={draft.default === p.name}
                        disabled={!on}
                        onChange={() => {
                          setDraft({ ...draft, default: p.name });
                          setSaved(false);
                        }}
                        className="accent-[var(--color-brand)]"
                      />
                      Default
                    </label>
                  </li>
                );
              })}
            </ul>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => void save()}
                disabled={!changed || Boolean(invalid)}
                className="h-9 rounded-lg bg-brand px-4 text-sm font-medium text-on-brand hover:bg-brand-strong disabled:opacity-50"
              >
                Save
              </button>
              {invalid && (
                <span className="text-sm text-warning-ink">{invalid}</span>
              )}
              {saved && !changed && (
                <span className="inline-flex items-center gap-1 text-sm text-success-ink">
                  <Check aria-hidden className="size-4" />
                  Saved
                </span>
              )}
            </div>
          </Card>

          <Card
            title="Embeddings"
            subtitle="Used for search; changing them rebuilds the index, so they are set in the configuration."
          >
            <p className="flex items-center gap-2 text-sm text-ink">
              <Cpu aria-hidden className="size-4 text-ink-faint" />
              {settings.embedding_provider === "local"
                ? "In the backend (no Ollama)"
                : "Ollama"}{" "}
              · <code className="text-xs">{settings.embedding_model}</code>
            </p>
            <p className="mt-2 text-xs text-ink-faint">
              To run with Claude only (no Ollama containers), start the stack
              with{" "}
              <code>
                docker compose -f docker-compose.yml -f
                docker-compose.claude-only.yml up -d
              </code>
              . The same embedding model then runs inside the backend, so search
              results do not change.
            </p>
          </Card>
        </div>
      )}
    </section>
  );
}
