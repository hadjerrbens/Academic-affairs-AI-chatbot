/** Parse SSE even when network chunks split between lines or JSON characters. */
export function createSSEParser(onEvent) {
  let pending = "";
  function deliver(block) {
    const lines = block.split(/\r\n|\r|\n/);
    let name = "message";
    const payloadLines = [];
    for (const line of lines) {
      if (line.startsWith(":")) continue; // heartbeat
      if (line.startsWith("event:")) name = line.slice(6).trim();
      if (line.startsWith("data:")) payloadLines.push(line.slice(5).trimStart());
    }
    if (!payloadLines.length) return;
    const text = payloadLines.join("\n");
    if (text === "[DONE]") return onEvent({ event: "done", data: {} });
    let value = text;
    try { value = JSON.parse(text); } catch { /* SSE may carry plain text */ }
    if (name === "message" && typeof value === "object" && value !== null) {
      if (typeof value.event === "string") return onEvent(value);
      if ("delta" in value) return onEvent({ event: "delta", data: value.delta });
      if ("error" in value) return onEvent({ event: "error", data: value.error });
    }
    // Some SSE wrappers send {delta:"..."} or {data:"..."} for an event: delta.
    if (name === "delta" && value && typeof value === "object") {
      if (typeof value.delta === "string") return onEvent({ event: "delta", data: value.delta });
      if (typeof value.data === "string") return onEvent({ event: "delta", data: value.data });
    }
    onEvent({ event: name, data: value });
  }
  return {
    push(chunk) {
      pending += chunk;
      let match;
      while ((match = /\r\n\r\n|\n\n|\r\r/.exec(pending))) {
        deliver(pending.slice(0, match.index));
        pending = pending.slice(match.index + match[0].length);
      }
    },
    finish() {
      if (pending.trim()) deliver(pending);
      pending = "";
    },
  };
}
