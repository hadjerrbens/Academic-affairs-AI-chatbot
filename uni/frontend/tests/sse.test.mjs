import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createSSEParser } from '../src/features/chat/sse.mjs';

test('SSE merges split chunks into a single delta', () => {
  const events = [];
  const parser = createSSEParser(e => events.push(e));
  parser.push('event: de');
  parser.push('lta\ndata: "Hello"\n\nevent: delta\ndata: " World"\n\n');
  parser.finish();
  assert.equal(events.map(e => e.data).join(''), 'Hello World');
});

test('SSE supports CRLF, M4-style payload and terminal done', () => {
  const events = [];
  const parser = createSSEParser(e => events.push(e));
  parser.push('data: {"event":"meta","data":{"primary":"grading"}}\r\n\r\n');
  parser.push('event: done\r\ndata: {}\r\n\r\n');
  assert.deepEqual(events.map(e => e.event), ['meta','done']);
});

test('SSE does not report incomplete chunk before delimiter', () => {
  const events = [];
  const parser = createSSEParser(e => events.push(e));
  parser.push('event: delta\ndata: "A"');
  assert.equal(events.length, 0);
  parser.push('\n\n');
  assert.equal(events[0].data, 'A');
});

test('SSE unwraps JSON delta payload without showing object text', () => {
  const events = [];
  const parser = createSSEParser((event) => events.push(event));
  parser.push('event: delta\ndata: {"data":"Hello"}\n\n');
  parser.push('event: delta\ndata: {"delta":" world"}\n\n');
  parser.finish();
  assert.deepEqual(events, [
    { event: 'delta', data: 'Hello' },
    { event: 'delta', data: ' world' },
  ]);
});
