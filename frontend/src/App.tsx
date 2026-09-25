import { useEffect, useState } from "react";

// Placeholder until the chat UI (Phase 6): shows that the frontend can reach the backend.
type Health = {
  status: "ok" | "degraded";
  version: string;
  llm_provider: string;
  ollama: { reachable: boolean; missing_models: string[] } | null;
};

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/v1/health")
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then(setHealth)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <main className="mx-auto max-w-2xl p-8 font-sans text-slate-800">
      <h1 className="text-2xl font-semibold">OmniCorp Knowledge Base Assistant</h1>
      <p className="mt-2 text-slate-500">The chat interface is coming soon.</p>
      <section className="mt-6 rounded-lg border border-slate-200 p-4 text-sm">
        <h2 className="font-medium">Backend status</h2>
        {error && <p className="mt-2 text-red-600">Unreachable: {error}</p>}
        {!error && !health && <p className="mt-2">Checking…</p>}
        {health && (
          <ul className="mt-2 space-y-1">
            <li>
              Status:{" "}
              <span className={health.status === "ok" ? "text-green-700" : "text-amber-700"}>
                {health.status}
              </span>
            </li>
            <li>Version: {health.version}</li>
            <li>LLM provider: {health.llm_provider}</li>
            {health.ollama && (
              <li>
                Ollama: {health.ollama.reachable ? "reachable" : "unreachable"}
                {health.ollama.missing_models.length > 0 &&
                  ` (missing: ${health.ollama.missing_models.join(", ")})`}
              </li>
            )}
          </ul>
        )}
      </section>
    </main>
  );
}
