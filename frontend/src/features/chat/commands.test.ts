// Tests for the model commands: names, parsing, normal questions and paths, unknown models, and
// suggestions.

import { describe, expect, it } from "vitest";
import type { Provider } from "../../api/types";
import { modelCommands, parseInput, suggestions } from "./commands";

const providers: Provider[] = [
  {
    name: "ollama",
    model: "ministral-3:3b",
    default: true,
    available: true,
    detail: null,
  },
  {
    name: "anthropic",
    model: "claude-opus-5",
    default: false,
    available: true,
    detail: null,
  },
];

describe("model commands", () => {
  it("offers provider, short and model-family names", () => {
    expect(
      modelCommands(providers).map((c) => `${c.name}->${c.provider.name}`),
    ).toEqual([
      "local->ollama",
      "ollama->ollama",
      "ministral->ollama",
      "claude->anthropic",
      "anthropic->anthropic",
    ]);
  });

  it("parses switches, one-off questions and lists", () => {
    expect(parseInput("/claude", providers)).toMatchObject({
      kind: "switch",
      provider: { name: "anthropic" },
    });
    expect(parseInput("/Local", providers)).toMatchObject({
      kind: "switch",
      provider: { name: "ollama" },
    });
    expect(
      parseInput("/claude  How long are backups kept? ", providers),
    ).toMatchObject({
      kind: "ask",
      provider: { name: "anthropic" },
      question: "How long are backups kept?",
    });
    expect(parseInput("/models", providers)).toEqual({ kind: "list" });
    expect(parseInput("/help", providers)).toEqual({ kind: "list" });
  });

  it("leaves normal questions and paths alone", () => {
    expect(parseInput("How long are backups kept?", providers)).toEqual({
      kind: "question",
      text: "How long are backups kept?",
    });
    expect(parseInput("/v3/records:batch limits?", providers)).toMatchObject({
      kind: "question",
    });
  });

  it("reports unknown and unavailable models", () => {
    expect(parseInput("/gpt hello", providers)).toEqual({
      kind: "unknown",
      name: "gpt",
    });
    const down = providers.map((p) =>
      p.name === "anthropic" ? { ...p, available: false } : p,
    );
    expect(parseInput("/claude", down)).toMatchObject({ kind: "unavailable" });
  });

  it("suggests matching commands while typing", () => {
    expect(suggestions("/cl", providers).map((c) => c.name)).toEqual([
      "claude",
    ]);
    expect(suggestions("/", providers)).toHaveLength(5);
    expect(suggestions("/claude how", providers)).toEqual([]);
    expect(suggestions("hello", providers)).toEqual([]);
  });
});
