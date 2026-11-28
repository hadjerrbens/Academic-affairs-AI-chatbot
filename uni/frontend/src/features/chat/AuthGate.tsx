import { useState, type FormEvent } from "react";
import { LogIn, LogOut, ShieldCheck } from "lucide-react";

type Props = {
  userEmail?: string | null; error?: string | null; checking?: boolean;
  login: (email: string, password: string) => Promise<boolean>; logout: () => Promise<void>;
};

export function AuthGate({ userEmail, error, checking, login, logout }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try { if (await login(email, password)) setPassword(""); } finally { setBusy(false); }
  }
  if (checking) return <div className="account skeleton" aria-live="polite">Checking your session…</div>;
  if (userEmail) {
    const initials = userEmail.slice(0, 2).toUpperCase();
    return (
      <div className="account signed-in">
        <span className="avatar" aria-hidden>{initials}</span>
        <div className="account-text"><strong>Signed in</strong><small title={userEmail}>{userEmail}</small></div>
        <button type="button" className="icon-btn" onClick={() => void logout()} aria-label="Log out" title="Log out"><LogOut size={18} /></button>
      </div>
    );
  }
  return (
    <form className="account" onSubmit={submit}>
      <p className="eyebrow"><ShieldCheck size={14} aria-hidden /> Student login</p>
      <label>Email<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} placeholder="you@student.example.edu" /></label>
      <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>
      <button className="btn primary" disabled={busy} type="submit"><LogIn size={16} aria-hidden /> {busy ? "Signing in…" : "Log in"}</button>
      {error && <p className="form-error" role="alert">{error}</p>}
    </form>
  );
}
