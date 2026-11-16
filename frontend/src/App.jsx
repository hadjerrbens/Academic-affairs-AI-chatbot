import { useEffect, useRef, useState } from "react";
import { loadHistory, streamChat } from "./api.js";

// One id per browser, kept in localStorage, so history survives a page refresh.
function getSessionId() {
  let id = localStorage.getItem("session_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("session_id", id);
  }
  return id;
}

export default function App() {
  const [sessionId] = useState(getSessionId);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    loadHistory(sessionId).then(setMessages);
  }, [sessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    // Add the question and an empty answer that we fill as chunks arrive.
    setMessages((m) => [...m, { role: "user", content: text }, { role: "assistant", content: "" }]);
    try {
      await streamChat(sessionId, text, (delta) => {
        setMessages((m) => {
          const copy = [...m];
          const last = copy[copy.length - 1];
          copy[copy.length - 1] = { ...last, content: last.content + delta };
          return copy;
        });
      });
    } catch (err) {
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = { role: "assistant", content: `⚠️ ${err.message}` };
        return copy;
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app">
      <header>Academic Affairs Assistant</header>
      <main>
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.content || "…"}
          </div>
        ))}
        <div ref={bottomRef} />
      </main>
      <form onSubmit={send}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type your question..."
          maxLength={1000}
        />
        <button disabled={busy || !input.trim()}>Send</button>
      </form>
    </div>
  );
}
