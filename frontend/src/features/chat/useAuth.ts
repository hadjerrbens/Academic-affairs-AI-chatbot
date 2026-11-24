import { useCallback, useEffect, useRef, useState } from "react";

type Tokens = { access_token: string; refresh_token: string };
type User = { user_id: string; student_id: string; email: string; role: string };
const STORAGE_KEY = "m2-chat-auth"; // demo-only: use httpOnly cookies in production

function loadTokens(): Tokens | null {
  try {
    const text = sessionStorage.getItem(STORAGE_KEY);
    if (!text) return null;
    const value = JSON.parse(text);
    return value?.access_token && value?.refresh_token ? value as Tokens : null;
  } catch { return null; }
}

export function useAuth() {
  const [tokens, setTokens] = useState<Tokens | null>(loadTokens);
  const tokensRef = useRef<Tokens | null>(tokens);
  const pendingRefresh = useRef<Promise<string | null> | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(Boolean(tokens));

  const remember = useCallback((next: Tokens | null) => {
    tokensRef.current = next;
    setTokens(next);
    if (next) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    else sessionStorage.removeItem(STORAGE_KEY);
  }, []);

  const getAccessToken = useCallback(() => tokensRef.current?.access_token || null, []);
  const refresh = useCallback((): Promise<string | null> => {
    if (pendingRefresh.current) return pendingRefresh.current;
    const old = tokensRef.current;
    if (!old) return Promise.resolve(null);
    const current = (async () => {
      try {
        const response = await fetch("/api/auth/refresh", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: old.refresh_token }),
        });
        if (!response.ok) throw new Error("Session expired.");
        const next = await response.json() as Tokens;
        // Do not restore tokens when the user logged out during the refresh.
        if (tokensRef.current?.refresh_token !== old.refresh_token) return null;
        remember(next);
        return next.access_token;
      } catch {
        if (tokensRef.current?.refresh_token === old.refresh_token) {
          remember(null);
          setUser(null);
        }
        return null;
      }
    })();
    pendingRefresh.current = current;
    void current.finally(() => { pendingRefresh.current = null; });
    return current;
  }, [remember]);

  const logout = useCallback(async () => {
    const old = tokensRef.current;
    remember(null);
    setUser(null);
    setError(null);
    if (old) {
      await fetch("/api/auth/logout", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: old.refresh_token }),
      }).catch(() => undefined);
    }
  }, [remember]);

  const login = useCallback(async (email: string, password: string) => {
    setError(null);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) throw new Error("Login failed");
      const next = await response.json() as Tokens;
      const me = await fetch("/api/auth/me", {
        headers: { Authorization: `Bearer ${next.access_token}` },
      });
      if (!me.ok) throw new Error("Login failed");
      const profile = await me.json() as User;
      remember(next);
      setUser(profile);
      return true;
    } catch {
      setError("Invalid email or password."); // same message for every failed login
      return false;
    }
  }, [remember]);

  useEffect(() => {
    if (!tokensRef.current) return;
    let active = true;
    void (async () => {
      try {
        let token = getAccessToken();
        let response = await fetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } });
        if (response.status === 401) {
          token = await refresh();
          if (token) response = await fetch("/api/auth/me", { headers: { Authorization: `Bearer ${token}` } });
        }
        if (!response.ok) throw new Error("Session expired");
        const profile = await response.json() as User;
        if (active) setUser(profile);
      } catch {
        if (active) { remember(null); setUser(null); }
      } finally { if (active) setChecking(false); }
    })();
    return () => { active = false; };
  }, [getAccessToken, refresh, remember]);

  return { user, error, checking, login, logout, refresh, getAccessToken };
}
