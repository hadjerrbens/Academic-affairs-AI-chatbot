import { createSSEParser } from './sse.mjs';

/** POST streaming + a single access-token refresh retry on HTTP 401. */
export async function postChatStream(sessionId, message, auth, onEvent, signal) {
  const request = (token) => fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ session_id: sessionId, message }),
    signal,
  });
  const originalToken = auth.getAccessToken();
  let response = await request(originalToken);
  if (response.status === 401 && originalToken) {
    const replacement = await auth.refresh();
    if (replacement) response = await request(replacement);
  }
  if (!response.ok) {
    if (response.status === 401) throw new Error('Please log in to see your academic information.');
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : `Chat request failed (${response.status}).`);
  }
  if (!response.body) throw new Error('This browser cannot read chat responses.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = createSSEParser(onEvent);
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
    }
    parser.push(decoder.decode());
    parser.finish();
  } finally {
    reader.releaseLock();
  }
}
