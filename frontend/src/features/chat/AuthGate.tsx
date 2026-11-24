import { useState, type FormEvent } from "react";

type Props = {
  userEmail?: string | null;
  error?: string | null;
  checking?: boolean;
  login: (email: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
};

/** Log-in form; public academic questions remain available when signed out. */
export function AuthGate({ userEmail, error, checking, login, logout }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    try { if (await login(email, password)) setPassword(""); }
    finally { setSubmitting(false); }
  }
  if (checking) return <p aria-live="polite">Checking your session…</p>;
  if (userEmail) {
    return <div className="m2-auth-user"><span>Signed in as {userEmail}</span>{" "}
      <button type="button" onClick={() => void logout()}>Log out</button></div>;
  }
  return <form className="m2-login" onSubmit={submit}>
    <strong>Login to see your own data</strong>
    <label>Email<input type="email" autoComplete="username" required value={email}
      onChange={event => setEmail(event.target.value)} /></label>
    <label>Password<input type="password" autoComplete="current-password" required value={password}
      onChange={event => setPassword(event.target.value)} /></label>
    <button disabled={submitting} type="submit">{submitting ? "Signing in…" : "Log in"}</button>
    {error && <p role="alert">{error}</p>}
  </form>;
}
