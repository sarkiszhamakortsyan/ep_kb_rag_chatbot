import type { Provider } from "../../api/types";

// Readable names for the model picker; unknown models fall back to their raw id.
const MODEL_NAMES: [prefix: string, name: string][] = [
  ["claude-opus", "Claude Opus"],
  ["claude-sonnet", "Claude Sonnet"],
  ["claude-haiku", "Claude Haiku"],
  ["ministral-3:3b", "Ministral 3B"],
  ["qwen3.5:4b", "Qwen 3.5 4B"],
  ["gemma3:4b", "Gemma 3 4B"],
  ["llama3.2:3b", "Llama 3.2 3B"],
];

export function modelName(model: string | null): string {
  if (!model) return "Unknown model";
  return MODEL_NAMES.find(([prefix]) => model.startsWith(prefix))?.[1] ?? model;
}

/** "Claude Opus · cloud" / "Ministral 3B · local". Local models keep data on this machine. */
export function providerLabel(p: Provider): string {
  const where = p.name === "ollama" ? "local" : "cloud";
  const label = `${modelName(p.model)} · ${where}`;
  return p.available ? label : `${label} (unavailable)`;
}
