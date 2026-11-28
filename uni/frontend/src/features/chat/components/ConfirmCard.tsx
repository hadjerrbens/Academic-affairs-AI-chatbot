import { useState } from "react";
import { CheckCircle2, Clock, Wallet } from "lucide-react";
import type { AuthAccess } from "../useChatStream";

export type Confirmation = { action_id?: string; summary?: string; fee?: number | null; estimated_days?: number | null };

/** The only write path: nothing is submitted until the student clicks Confirm. */
export function ConfirmCard({ data, auth }: { data: Confirmation; auth: AuthAccess }) {
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "cancelled" | "error">("idle");
  const [message, setMessage] = useState("");

  async function act(kind: "confirm" | "cancel") {
    setStatus("loading");
    const call = (token: string | null) => fetch(`/api/actions/${data.action_id}/${kind}`, {
      method: "POST", headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    try {
      let res = await call(auth.getAccessToken());
      if (res.status === 401) { const t = await auth.refresh(); if (t) res = await call(t); }
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Something went wrong. Please try again.");
      setMessage(body.message ?? (kind === "confirm" ? "Request submitted." : "Request cancelled."));
      setStatus(kind === "confirm" ? "done" : "cancelled");
    } catch (e) {
      setMessage((e as Error).message);
      setStatus("error");
    }
  }

  if (status === "done" || status === "cancelled") {
    return <div className={`confirm ${status}`}><CheckCircle2 size={18} aria-hidden /> <span>{message}</span></div>;
  }
  const fee = data.fee == null ? null : data.fee === 0 ? "Free" : `${data.fee} DZD`;
  return (
    <div className="confirm">
      <p className="eyebrow">Needs your confirmation</p>
      <p className="confirm-summary">{data.summary}</p>
      <div className="confirm-facts">
        {fee && <span><Wallet size={15} aria-hidden /> {fee}</span>}
        {data.estimated_days != null && <span><Clock size={15} aria-hidden /> about {data.estimated_days} day{data.estimated_days === 1 ? "" : "s"}</span>}
      </div>
      {status === "error" && <p className="form-error" role="alert">{message}</p>}
      <div className="confirm-actions">
        <button type="button" className="btn primary" disabled={status === "loading"} onClick={() => void act("confirm")}>
          {status === "loading" ? "Working…" : "Confirm request"}
        </button>
        <button type="button" className="btn ghost" disabled={status === "loading"} onClick={() => void act("cancel")}>Cancel</button>
      </div>
    </div>
  );
}
