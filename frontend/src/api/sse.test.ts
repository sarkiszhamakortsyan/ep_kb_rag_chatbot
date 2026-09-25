import { describe, expect, it } from "vitest";
import { SseParser } from "./sse";

describe("SseParser", () => {
  it("parses events split across arbitrary chunks", () => {
    const parser = new SseParser();
    const stream = 'event: token\ndata: {"text":"Hel"}\n\nevent: token\ndata: {"text":"lo"}\n\n';
    const events = [stream.slice(0, 7), stream.slice(7, 30), stream.slice(30)].flatMap((c) =>
      parser.push(c),
    );
    expect(events).toEqual([
      { event: "token", data: { text: "Hel" } },
      { event: "token", data: { text: "lo" } },
    ]);
  });

  it("waits for the blank line that ends an event", () => {
    const parser = new SseParser();
    expect(parser.push('event: done\ndata: {"a":1}\n')).toEqual([]);
    expect(parser.push("\n")).toEqual([{ event: "done", data: { a: 1 } }]);
  });

  it("handles CRLF line endings, comments and invalid JSON", () => {
    const parser = new SseParser();
    const events = parser.push(
      ': keep-alive\r\n\r\nevent: token\r\ndata: {"text":"x"}\r\n\r\nevent: token\ndata: not-json\n\n',
    );
    expect(events).toEqual([{ event: "token", data: { text: "x" } }]);
  });
});
