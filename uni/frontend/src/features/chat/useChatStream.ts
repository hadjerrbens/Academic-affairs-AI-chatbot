import { useCallback, useRef, useState } from 'react';
import { postChatStream } from './chatTransport.mjs';

export type ChatEvent = { event: string; data: unknown };
export type AuthAccess = {
  getAccessToken: () => string | null;
  refresh: () => Promise<string | null>;
};

/** React wrapper around the tested plain-JavaScript SSE transport. */
export function useChatStream(auth: AuthAccess) {
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const send = useCallback(async (
    sessionId: string, text: string, onEvent: (event: ChatEvent) => void,
  ) => {
    if (controller.current) return;
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    try {
      await postChatStream(sessionId, text, auth, onEvent, abort.signal);
    } finally {
      controller.current = null;
      setBusy(false);
    }
  }, [auth]);
  const cancel = useCallback(() => controller.current?.abort(), []);
  return { send, cancel, busy };
}
