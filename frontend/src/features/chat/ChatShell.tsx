import { useRef, useState, useEffect, type FormEvent, type ReactNode } from "react";
import { AuthGate } from "./AuthGate";
import { useAuth } from "./useAuth";
import { useChatStream, type ChatEvent } from "./useChatStream";
import "./ChatShell.css";

type Message = { id: string; role: "user" | "assistant"; text: string; citations: unknown[]; tools: unknown[]; confirmation?: unknown };
type Props = {
  // M5 supplies these optional renderers when the team's shared UI components arrive.
  renderCitations?: (citations: unknown[]) => ReactNode;
  renderTool?: (tool: unknown) => ReactNode;
  renderConfirmation?: (data: unknown) => ReactNode;
  connectionStatus?: string; // M1 can pass useRealtime().connectionState here
};

function SimpleMarkdown({ text }: { text: string }) {
  // Small safe renderer for the demo; React automatically escapes all text.
  function inline(content: string): ReactNode[] {
    return content.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean).map((part, i) =>
      part.startsWith("**") && part.endsWith("**")
        ? <strong key={i}>{part.slice(2, -2)}</strong>
        : part.startsWith("`") && part.endsWith("`")
          ? <code key={i}>{part.slice(1, -1)}</code>
          : <span key={i}>{part}</span>);
  }
  return <div className="m2-markdown">{text.split("\n").map((line, i) => {
    if (line.startsWith("### ")) return <h4 key={i}>{inline(line.slice(4))}</h4>;
    if (line.startsWith("## ")) return <h3 key={i}>{inline(line.slice(3))}</h3>;
    if (line.startsWith("# ")) return <h2 key={i}>{inline(line.slice(2))}</h2>;
    if (line.startsWith("- ")) return <p key={i} className="m2-bullet">• {inline(line.slice(2))}</p>;
    return <p key={i}>{line ? inline(line) : "\u00a0"}</p>;
  })}</div>;
}

export default function ChatShell({ renderCitations, renderTool, renderConfirmation, connectionStatus }: Props) {
  const auth = useAuth();
  const stream = useChatStream(auth);
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID());
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [lastQuestion, setLastQuestion] = useState("");
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const serial = useRef(0);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  async function sendText(text: string) {
    const question = text.trim();
    if (!question || stream.busy) return;
    setError(null);
    setDraft("");
    setLastQuestion(question);
    const id = String(++serial.current);
    setMessages(items => [
      ...items,
      { id: `user-${id}`, role: "user", text: question, citations: [], tools: [] },
      { id: `assistant-${id}`, role: "assistant", text: "", citations: [], tools: [] },
    ]);
    const updateAnswer = (fn: (answer: Message) => Message) => setMessages(items =>
      items.map(item => item.id === `assistant-${id}` ? fn(item) : item)
    );
    try {
      await stream.send(sessionId, question, (event: ChatEvent) => {
        switch (event.event) {
          case "delta": {
            const part = typeof event.data === "string" ? event.data : String(event.data ?? "");
            updateAnswer(item => ({ ...item, text: item.text + part }));
            break;
          }
          case "citations":
            updateAnswer(item => ({ ...item, citations: Array.isArray(event.data) ? event.data : [] }));
            break;
          case "tool":
            updateAnswer(item => ({ ...item, tools: [...item.tools, event.data] }));
            break;
          case "confirm":
            updateAnswer(item => ({ ...item, confirmation: event.data }));
            break;
          case "error": {
            const data = event.data as { message?: string } | string | null;
            const message = typeof data === "string" ? data : data?.message || "Chat is temporarily unavailable.";
            setError(message);
          }
        }
      });
    } catch (exception) {
      if ((exception as Error)?.name === "AbortError") {
        updateAnswer(item => ({ ...item, text: item.text || "Response cancelled." }));
      } else {
        setError((exception as Error).message || "Chat is temporarily unavailable.");
      }
    }
  }

  // Keep a signed-out student's academic answers off the shared screen.
  async function logout() {
    stream.cancel();
    const loggingOut = auth.logout();
    setMessages([]);
    setDraft("");
    setError(null);
    setLastQuestion("");
    setSessionId(crypto.randomUUID());
    await loggingOut;
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendText(draft);
  }

  return <div className="m2-shell">
    <header className="m2-header">
      <div><h1>Academic Affairs Assistant</h1><small>University academic questions</small></div>
      {connectionStatus && <small>Live updates: {connectionStatus}</small>}
    </header>
    <AuthGate userEmail={auth.user?.email} login={auth.login} logout={logout}
      error={auth.error} checking={auth.checking} />
    {!auth.user && <p className="m2-hint">You can ask general questions now. Log in for your GPA, standing and degree progress.</p>}
    <main className="m2-messages" aria-live="polite" aria-label="Chat messages">
      {!messages.length && <p className="m2-empty">Ask about degree requirements, academic standing, course registration, grades, exams or transcripts.</p>}
      {messages.map(message => <section className={`m2-message m2-${message.role}`} key={message.id}>
        <strong>{message.role === "user" ? "You" : "Assistant"}</strong>
        <SimpleMarkdown text={message.text || "…"} />
        {message.tools.map((tool, i) => <div className="m2-tool" key={i}>
          {renderTool ? renderTool(tool) : <small>Tool used: {String((tool as { name?: string })?.name || "academic tool")}</small>}
        </div>)}
        {message.citations.length > 0 && <div className="m2-citations">
          {renderCitations ? renderCitations(message.citations) : <small>Sources available: {message.citations.length}</small>}
        </div>}
        {message.confirmation && <div className="m2-confirm">
          {renderConfirmation ? renderConfirmation(message.confirmation) : <p>This action requires confirmation when the team's confirmation component is connected.</p>}
        </div>}
      </section>)}
      <div ref={bottomRef}/>
    </main>
    {error && <div className="m2-error" role="alert">{error}{" "}
      {lastQuestion && !stream.busy && <button type="button" onClick={() => void sendText(lastQuestion)}>Retry</button>}
    </div>}
    <form className="m2-composer" onSubmit={submit}>
      <label htmlFor="m2-chat-draft" className="m2-sr-only">Your question</label>
      <input id="m2-chat-draft" value={draft} onChange={event => setDraft(event.target.value)}
        placeholder="Type your academic question…" maxLength={1000} disabled={stream.busy}/>
      {stream.busy
        ? <button type="button" onClick={stream.cancel}>Cancel</button>
        : <button type="submit" disabled={!draft.trim()}>Send</button>}
    </form>
  </div>;
}
