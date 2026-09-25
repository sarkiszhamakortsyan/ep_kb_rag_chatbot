import { describe, expect, it, vi } from "vitest";
import { chatResponse, jsonResponse, sse, streamResponse } from "../test/fixtures";
import { ApiError, streamChat } from "./client";

describe("streamChat", () => {
  it("yields meta, token and done events from the SSE body", async () => {
    const body =
      sse("meta", { conversation_id: "c", message_id: "m", sources: [] }) +
      sse("token", { text: "Hi" }) +
      sse("done", chatResponse());
    const fetchMock = vi.fn().mockResolvedValue(streamResponse([body.slice(0, 50), body.slice(50)]));
    vi.stubGlobal("fetch", fetchMock);

    const events = [];
    for await (const event of streamChat({ message: "q", options: { provider: "anthropic" } })) {
      events.push(event.event);
    }

    expect(events).toEqual(["meta", "token", "done"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/chat/stream");
    expect(JSON.parse(init.body)).toEqual({ message: "q", options: { provider: "anthropic" } });
  });

  it("throws ApiError with the server's error code before the stream starts", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ error: { code: "not_ready", message: "The knowledge base is still loading." } }, 503),
      ),
    );
    const run = async () => {
      for await (const _ of streamChat({ message: "q" })) void _;
    };
    await expect(run()).rejects.toMatchObject({ status: 503, code: "not_ready" });
    await expect(run()).rejects.toBeInstanceOf(ApiError);
  });
});
