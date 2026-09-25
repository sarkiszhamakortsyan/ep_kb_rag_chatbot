import type { StreamEvent } from "./types";

/**
 * Incremental Server-Sent Events parser. Network chunks can split an event anywhere,
 * so text is buffered until a blank line ends the event.
 * (EventSource can't be used: it only supports GET, and the chat stream is a POST.)
 */
export class SseParser {
  private buffer = "";

  push(chunk: string): StreamEvent[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const events: StreamEvent[] = [];
    let end: number;
    while ((end = this.buffer.indexOf("\n\n")) !== -1) {
      const block = this.buffer.slice(0, end);
      this.buffer = this.buffer.slice(end + 2);
      const event = parseBlock(block);
      if (event) events.push(event);
    }
    return events;
  }
}

function parseBlock(block: string): StreamEvent | null {
  let name = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith(":")) continue; // comment / keep-alive
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") name = value;
    else if (field === "data") data.push(value);
  }
  if (data.length === 0) return null;
  try {
    return { event: name, data: JSON.parse(data.join("\n")) } as StreamEvent;
  } catch {
    return null;
  }
}
