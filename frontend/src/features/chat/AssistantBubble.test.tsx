import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { chatResponse, citation } from "../../test/fixtures";
import { AssistantBubble } from "./AssistantBubble";
import type { AssistantMessage } from "./useChat";

const message = (overrides: Partial<AssistantMessage> = {}): AssistantMessage => ({
  id: "a1",
  role: "assistant",
  text: "Backups are retained for **35 days** [1].",
  status: "done",
  sources: [citation(1)],
  result: chatResponse(),
  question: "How long are backups kept?",
  ...overrides,
});

describe("AssistantBubble", () => {
  it("renders Markdown, citation chips and source cards", async () => {
    render(<AssistantBubble message={message()} onRetry={vi.fn()} />);

    expect(screen.getByText("35 days").tagName).toBe("STRONG");
    const chip = screen.getByRole("button", { name: "Show source 1" });
    const sources = screen.getByRole("region", { name: "Sources" });
    expect(sources).toHaveTextContent("Guide 1");
    expect(sources).toHaveTextContent("Section 1");
    expect(sources).toHaveTextContent("high relevance");

    await userEvent.click(chip);
    expect(document.getElementById("cite-a1-1")).toHaveClass("border-indigo-400");
    expect(screen.getByText("Snippet text 1.")).toBeVisible();
  });

  it("marks refusals and shows no sources", () => {
    const refused = chatResponse({ refused: true, refusal_reason: "low_score", citations: [] });
    render(
      <AssistantBubble message={message({ text: "I couldn't find this.", result: refused })} onRetry={vi.fn()} />,
    );
    expect(screen.getByText("Not covered by the knowledge base")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Sources" })).not.toBeInTheDocument();
  });

  it("shows progress while streaming", () => {
    render(
      <AssistantBubble
        message={message({ text: "", status: "streaming", result: undefined, sources: [citation(1), citation(2)] })}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Found 2 relevant sections");
  });

  it("shows errors with a retry button", async () => {
    const onRetry = vi.fn();
    render(
      <AssistantBubble
        message={message({
          text: "",
          status: "error",
          result: undefined,
          error: { code: "provider_unavailable", message: "Anthropic is busy" },
        })}
        onRetry={onRetry}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Anthropic is busy");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledWith("How long are backups kept?");
  });
});
