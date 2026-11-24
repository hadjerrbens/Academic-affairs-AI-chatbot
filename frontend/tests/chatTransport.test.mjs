import assert from 'node:assert/strict';
import { test } from 'node:test';
import { postChatStream } from '../src/features/chat/chatTransport.mjs';

function responseFromPieces(pieces) {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream({
    start(controller) {
      pieces.forEach(s => controller.enqueue(encoder.encode(s)));
      controller.close();
    },
  }), { status: 200 });
}

test('streaming combines incremental delta messages', async () => {
  const prior = globalThis.fetch;
  try {
    globalThis.fetch = async () => responseFromPieces([
      'event: delta\ndata: "Hel', 'lo"\n\nevent: delta\ndata: " World"\n\n',
    ]);
    const events = [];
    await postChatStream('abc', 'hello?', { getAccessToken: () => null, refresh: async () => null },
      e => events.push(e));
    assert.equal(events.map(e => e.data).join(''), 'Hello World');
  } finally { globalThis.fetch = prior; }
});

test('on 401 refresh once and retry once with the new token', async () => {
  const prior = globalThis.fetch;
  let hits = 0;
  let refreshes = 0;
  try {
    globalThis.fetch = async (url, options) => {
      hits++;
      assert.equal(url, '/api/chat/stream');
      if (hits === 1) {
        assert.equal(options.headers.Authorization, 'Bearer old');
        return new Response('{}', { status: 401 });
      }
      assert.equal(options.headers.Authorization, 'Bearer new');
      return responseFromPieces(['event: delta\ndata: "ok"\n\n']);
    };
    const events = [];
    await postChatStream('abc', 'my GPA?', {
      getAccessToken: () => 'old',
      refresh: async () => { refreshes++; return 'new'; },
    }, e => events.push(e));
    assert.equal(hits, 2);
    assert.equal(refreshes, 1);
    assert.equal(events[0].data, 'ok');
  } finally { globalThis.fetch = prior; }
});

test('two 401 responses fail without a third request', async () => {
  const prior = globalThis.fetch;
  let hits = 0;
  try {
    globalThis.fetch = async () => { hits++; return new Response('', { status: 401 }); };
    await assert.rejects(
      postChatStream('abc', 'gpa', { getAccessToken: () => 'old', refresh: async () => 'new' }, () => {}),
      /Please log in/,
    );
    assert.equal(hits, 2);
  } finally { globalThis.fetch = prior; }
});
