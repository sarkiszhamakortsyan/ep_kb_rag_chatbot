import type { Provider } from "../../api/types";
import { modelName } from "./providers";

// Chat commands for choosing the model by typing, next to the model dropdown:
//   /claude              switch the selected model (the dropdown follows)
//   /claude <question>   ask this one question with that model; the selection stays
//   /models  (or /help)  list the models and their commands

export type ModelCommand = { name: string; provider: Provider };

export type ParsedInput =
  | { kind: "question"; text: string } // not a command: send as typed
  | { kind: "switch"; provider: Provider }
  | { kind: "ask"; provider: Provider; question: string }
  | { kind: "list" }
  | { kind: "unknown"; name: string }
  | { kind: "unavailable"; provider: Provider };

const SHORT_NAMES: Record<string, string> = {
  anthropic: "claude",
  ollama: "local",
};
const LIST_COMMANDS = new Set(["models", "help"]);
// A command word: letters, digits, dots and dashes, e.g. "claude" or "ministral".
const COMMAND = /^\/([a-z][a-z0-9.-]*)(?:\s+([\s\S]*))?$/i;

/** Every command that selects a model: provider name, short name and model family. */
export function modelCommands(providers: Provider[]): ModelCommand[] {
  const seen = new Set<string>();
  const commands: ModelCommand[] = [];
  for (const provider of providers) {
    const family = modelName(provider.model).split(" ")[0].toLowerCase();
    for (const name of [SHORT_NAMES[provider.name], provider.name, family]) {
      if (name && /^[a-z][a-z0-9.-]*$/.test(name) && !seen.has(name)) {
        seen.add(name);
        commands.push({ name, provider });
      }
    }
  }
  return commands;
}

export function parseInput(text: string, providers: Provider[]): ParsedInput {
  const trimmed = text.trim();
  const match = COMMAND.exec(trimmed);
  // "/v3/records:batch …" and other paths are questions, not commands.
  if (!match) return { kind: "question", text: trimmed };
  const name = match[1].toLowerCase();
  const rest = match[2]?.trim() ?? "";
  if (LIST_COMMANDS.has(name)) return { kind: "list" };
  const command = modelCommands(providers).find((c) => c.name === name);
  if (!command) return { kind: "unknown", name };
  if (!command.provider.available)
    return { kind: "unavailable", provider: command.provider };
  return rest
    ? { kind: "ask", provider: command.provider, question: rest }
    : { kind: "switch", provider: command.provider };
}

/** Commands matching what has been typed so far ("/cl" -> /claude), for the suggestion list. */
export function suggestions(
  draft: string,
  providers: Provider[],
): ModelCommand[] {
  const match = /^\/([a-z0-9.-]*)$/i.exec(draft.trim());
  if (!match) return [];
  const prefix = match[1].toLowerCase();
  return modelCommands(providers).filter(
    (c) => c.name.startsWith(prefix) && c.provider.available,
  );
}
