import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { GraduationCap, Lock, Menu, MessageSquare, SendHorizontal, Square, TriangleAlert, X } from "lucide-react";
import { AuthGate } from "./AuthGate";
import { Markdown } from "./Markdown";
import { TOPICS } from "./topics";
import { useAuth } from "./useAuth";
import { useChatStream, type ChatEvent } from "./useChatStream";
import { CitationChips, type Citation } from "./components/CitationChips";
import { CitationDrawer } from "./components/CitationDrawer";
import { ConfirmCard, type Confirmation } from "./components/ConfirmCard";
import { ToolCard, type ToolEvent } from "./components/ToolCard";

type Msg = {
  id: string; role: "user" | "assistant"; text: string;
  citations: Citation[]; tools: ToolEvent[]; confirmation?: Confirmation; degraded?: boolean;
};
type PastChat = { session_id: string; title: string; last_at: string; turns: number };
const SESSION_KEY = "uni-chat-session";
const newSession = () => crypto.randomUUID();
function loadSession() {
  let id = sessionStorage.getItem(SESSION_KEY);
  if (!id) { id = newSession(); sessionStorage.setItem(SESSION_KEY, id); }
  return id;
}

export default function ChatShell() {
  const auth = useAuth();
  const stream = useChatStream(auth);
  const [sessionId, setSessionId] = useState(loadSession);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [lastQuestion, setLastQuestion] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [drawer, setDrawer] = useState<Citation | null>(null);
  const [past, setPast] = useState<PastChat[]>([]);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const serial = useRef(0);
  const signedIn = Boolean(auth.user);

  // Always points at the latest auth object WITHOUT being an effect dependency.
  // (Having `auth` in the dependency arrays caused the infinite /history loop.)
  const authRef = useRef(auth);
  authRef.current = auth;

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages]);

  // Restore this session's conversation after a refresh or login.
  useEffect(() => {
    if (auth.checking) return;
    let active = true;
    const token = authRef.current.getAccessToken();
    fetch(`/api/history/${sessionId}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then(r => (r.ok ? r.json() : []))
      .then((rows: { role: "user" | "assistant"; content: string }[]) => {
        if (!active || !rows.length) return;
        setMessages(rows.map((r, i) => ({ id: `h${i}`, role: r.role, text: r.content, citations: [], tools: [] })));
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [auth.checking, auth.user?.student_id, sessionId]);

  // "Recent chats" list: only for logged-in students; refreshed when an answer finishes.
  useEffect(() => {
    if (auth.checking || !auth.user || stream.busy) { if (!auth.user) setPast([]); return; }
    const token = authRef.current.getAccessToken();
    if (!token) return;
    fetch("/api/history", { headers: { Authorization: `Bearer ${token}` } })
      .then(r => (r.ok ? r.json() : []))
      .then((rows: PastChat[]) => setPast(Array.isArray(rows) ? rows : []))
      .catch(() => undefined);
  }, [auth.checking, auth.user?.student_id, stream.busy]);

  function openChat(id: string) {
    if (id === sessionId || stream.busy) { setMenuOpen(false); return; }
    setMessages([]); setError(null); setDrawer(null);
    sessionStorage.setItem(SESSION_KEY, id); setSessionId(id); setMenuOpen(false);
  }

  const sendText = useCallback(async (text: string) => {
    const question = text.trim();
    if (!question || stream.busy) return;
    setError(null); setDraft(""); setMenuOpen(false); setLastQuestion(question);
    const id = String(++serial.current);
    const answerId = `a${id}-${Date.now()}`;
    setMessages(items => [...items,
      { id: `u${id}-${Date.now()}`, role: "user", text: question, citations: [], tools: [] },
      { id: answerId, role: "assistant", text: "", citations: [], tools: [] }]);
    const patch = (fn: (m: Msg) => Msg) => setMessages(items => items.map(m => (m.id === answerId ? fn(m) : m)));
    try {
      await stream.send(sessionId, question, (event: ChatEvent) => {
        const d = event.data as any;
        switch (event.event) {
          case "meta": if (d?.degraded) patch(m => ({ ...m, degraded: true })); break;
          case "delta": patch(m => ({ ...m, text: m.text + (typeof d === "string" ? d : String(d ?? "")) })); break;
          case "citations": patch(m => ({ ...m, citations: Array.isArray(d) ? d : [] })); break;
          case "tool": patch(m => ({ ...m, tools: [...m.tools, d] })); break;
          case "confirm": patch(m => ({ ...m, confirmation: d })); break;
          case "error": setError(typeof d === "string" ? d : d?.message || "Chat is temporarily unavailable."); break;
        }
      });
    } catch (e) {
      if ((e as Error)?.name === "AbortError") patch(m => ({ ...m, text: m.text || "Response cancelled." }));
      else setError((e as Error).message || "Chat is temporarily unavailable.");
    }
  }, [sessionId, stream]);

  async function logout() {
    stream.cancel();
    const done = auth.logout();
    setMessages([]); setDraft(""); setError(null); setLastQuestion(""); setDrawer(null);
    const next = newSession();
    sessionStorage.setItem(SESSION_KEY, next);
    setSessionId(next);
    await done;
  }
  function newChat() {
    stream.cancel(); setMessages([]); setError(null); setDrawer(null);
    const next = newSession(); sessionStorage.setItem(SESSION_KEY, next); setSessionId(next); setMenuOpen(false);
  }
  function submit(e: FormEvent) { e.preventDefault(); void sendText(draft); }
  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void sendText(draft); }
  }
  const lastAssistant = messages[messages.length - 1];
  const waiting = stream.busy && lastAssistant?.role === "assistant" && !lastAssistant.text;

  return (
    <div className="app">
      <aside className={`sidebar ${menuOpen ? "open" : ""}`}>
        <div className="brand">
          <span className="brand-mark"><GraduationCap size={22} aria-hidden /></span>
          <div><strong>Academic Affairs</strong><small>Student assistant</small></div>
          <button type="button" className="icon-btn only-mobile" onClick={() => setMenuOpen(false)} aria-label="Close menu"><X size={20} /></button>
        </div>
        <AuthGate userEmail={auth.user?.email} login={auth.login} logout={logout} error={auth.error} checking={auth.checking} />
        {signedIn && past.length > 0 && (
          <nav aria-label="Recent chats">
            <p className="eyebrow">Recent chats</p>
            <ul className="topics">
              {past.slice(0, 8).map(c => (
                <li key={c.session_id}>
                  <button type="button" className={`topic recent ${c.session_id === sessionId ? "active" : ""}`} onClick={() => openChat(c.session_id)} title={c.title}>
                    <MessageSquare size={16} aria-hidden /><span>{c.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          </nav>
        )}
        <nav aria-label="Topics">
          <p className="eyebrow">Ask me about</p>
          <ul className="topics">
            {TOPICS.map(t => (
              <li key={t.title}>
                <button type="button" className="topic" disabled={stream.busy} onClick={() => void sendText(t.prompt)}>
                  <t.icon size={18} aria-hidden />
                  <span>{t.title}</span>
                  {t.login && !signedIn && <Lock size={13} className="lock" aria-label="Requires login" />}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <p className="fineprint">Answers come from official university data. Final decisions always rest with the registrar.</p>
      </aside>
      {menuOpen && <div className="scrim" onClick={() => setMenuOpen(false)} />}

      <section className="chat">
        <header className="chat-head">
          <button type="button" className="icon-btn only-mobile" onClick={() => setMenuOpen(true)} aria-label="Open menu"><Menu size={20} /></button>
          <div><h1>Academic Affairs Assistant</h1><small>{signedIn ? "Personalised answers on" : "General answers - log in for your own records"}</small></div>
          {messages.length > 0 && <button type="button" className="btn ghost small" onClick={newChat}>New chat</button>}
        </header>

        <main className="messages" aria-live="polite" aria-label="Conversation">
          {messages.length === 0 && (
            <div className="welcome">
              <span className="welcome-mark"><GraduationCap size={30} aria-hidden /></span>
              <h2>How can I help today?</h2>
              <p>Ask about degree progress, GPA, exams, grading, transcripts, waivers or proctoring. Pick a topic to start.</p>
              <div className="welcome-grid">
                {TOPICS.slice(0, 6).map(t => (
                  <button type="button" key={t.title} className="welcome-card" onClick={() => void sendText(t.prompt)}>
                    <t.icon size={20} aria-hidden /><strong>{t.title}</strong><small>{t.prompt}</small>
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map(m => (
            <article key={m.id} className={`msg ${m.role}`}>
              {m.role === "assistant" && <span className="msg-avatar" aria-hidden><GraduationCap size={16} /></span>}
              <div className="bubble">
                {m.degraded && <p className="degraded"><TriangleAlert size={14} aria-hidden /> AI explanation is temporarily unavailable; showing the data directly.</p>}
                {m.role === "user"
                  ? <p dir="auto" className="user-text">{m.text}</p>
                  : m.text
                    ? <Markdown text={m.text} onCite={n => { const c = m.citations.find(x => x.n === n); if (c) setDrawer(c); }} />
                    : (waiting && m === lastAssistant ? <span className="typing" aria-label="Assistant is typing"><i /><i /><i /></span> : null)}
                {m.tools.length > 0 && <div className="tools">{m.tools.map((t, i) => <ToolCard key={i} tool={t} />)}</div>}
                <CitationChips citations={m.citations} onOpen={setDrawer} />
                {m.confirmation && <ConfirmCard data={m.confirmation} auth={auth} />}
              </div>
            </article>
          ))}
          <div ref={bottomRef} />
        </main>

        {error && (
          <div className="banner" role="alert">
            <TriangleAlert size={16} aria-hidden /> <span>{error}</span>
            {lastQuestion && !stream.busy && <button type="button" className="btn ghost small" onClick={() => void sendText(lastQuestion)}>Retry</button>}
          </div>
        )}

        <form className="composer" onSubmit={submit}>
          <label htmlFor="draft" className="sr-only">Your question</label>
          <textarea id="draft" rows={1} dir="auto" value={draft} maxLength={1000} disabled={stream.busy}
            onChange={e => setDraft(e.target.value)} onKeyDown={onKey}
            placeholder="Ask about your degree, exams, grades, transcripts…" />
          {stream.busy
            ? <button type="button" className="send stop" onClick={stream.cancel} aria-label="Stop"><Square size={16} /></button>
            : <button type="submit" className="send" disabled={!draft.trim()} aria-label="Send"><SendHorizontal size={18} /></button>}
        </form>
      </section>
      <CitationDrawer citation={drawer} onClose={() => setDrawer(null)} />
    </div>
  );
}
