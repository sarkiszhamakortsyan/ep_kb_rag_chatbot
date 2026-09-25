import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { chatResponse, citation, jsonResponse, sse, streamResponse } from "../../test/fixtures";
import { ChatPage } from "./ChatPage";

const health = { status: "ok", ready: true, version: "0.1.0", llm_provider: "ollama", index: { ready: true, documents: 5, chunks: 49, error: null } };
const providers = {
  default: "ollama",
  providers: [
    { name: "ollama", model: "gemma3:4b", default: true, available: true, detail: null },
    { name: "anthropic", model: "claude-opus-5", default: false, available: true, detail: null },
  ],
};

function mockBackend(streamBody: string) {
  const fetchMock = vi.fn((url: string, _init?: RequestInit) => {
    void _init;
    if (url.endsWith("/health")) return Promise.resolve(jsonResponse(health));
    if (url.endsWith("/providers")) return Promise.resolve(jsonResponse(providers));
    return Promise.resolve(streamResponse([streamBody]));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("ChatPage", () => {
  it("sends a question with the chosen model and renders the streamed, cited answer", async () => {
    const answer = "Backups are retained for 35 days [1].";
    const fetchMock = mockBackend(
      sse("meta", { conversation_id: "conv1", message_id: "m1", sources: [citation(1)] }) +
        sse("token", { text: "Backups are retained " }) +
        sse("token", { text: "for 35 days [1]." }) +
        sse("done", chatResponse({ answer })),
    );
    const user = userEvent.setup();
    render(<ChatPage />);

    expect(await screen.findByText("Ready · 5 documents")).toBeInTheDocument();
    await user.selectOptions(await screen.findByLabelText("Model"), "anthropic");
    await user.type(screen.getByLabelText("Your question"), "How long are backups kept?{Enter}");

    expect(await screen.findByRole("button", { name: "Show source 1" })).toBeInTheDocument();
    expect(screen.getByText("How long are backups kept?")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Sources" })).toHaveTextContent("Guide 1");

    const chatCall = fetchMock.mock.calls.find(([url]) => url.endsWith("/chat/stream"));
    expect(JSON.parse(chatCall![1]!.body as string)).toEqual({
      message: "How long are backups kept?",
      options: { provider: "anthropic" },
    });
  });

  it("clears the conversation", async () => {
    mockBackend(sse("done", chatResponse()));
    const user = userEvent.setup();
    render(<ChatPage />);
    await user.type(screen.getByLabelText("Your question"), "Question one{Enter}");
    await waitFor(() => expect(screen.getByText("Question one")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "New conversation" }));
    expect(screen.queryByText("Question one")).not.toBeInTheDocument();
    expect(screen.getByText(/Ask a question about OmniCorp/)).toBeInTheDocument();
  });
});
