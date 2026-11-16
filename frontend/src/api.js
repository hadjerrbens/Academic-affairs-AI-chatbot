// POST + streaming: EventSource only supports GET, so we read the response body ourselves.
export async function streamChat(sessionId, message, onDelta) {
  const res = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Server error (${res.status})`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Server-sent events are separated by a blank line.
    let end;
    while ((end = buffer.indexOf("\n\n")) !== -1) {
      const event = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      if (!event.startsWith("data:")) continue;
      const data = event.slice(5).trim();
      if (data === "[DONE]") return;
      const payload = JSON.parse(data);
      if (payload.error) throw new Error(payload.error);
      if (payload.delta) onDelta(payload.delta);
    }
  }
}

export async function loadHistory(sessionId) {
  const res = await fetch(`/api/history/${sessionId}`);
  return res.ok ? res.json() : [];
}
