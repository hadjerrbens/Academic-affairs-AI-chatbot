import { useEffect } from "react";
import { X } from "lucide-react";
import type { Citation } from "./CitationChips";

export function CitationDrawer({ citation, onClose }: { citation: Citation | null; onClose: () => void }) {
  useEffect(() => {
    if (!citation) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [citation, onClose]);
  if (!citation) return null;
  return (
    <div className="drawer-wrap" role="dialog" aria-modal="true" aria-label="Source">
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer">
        <button type="button" className="icon-btn drawer-close" onClick={onClose} aria-label="Close source"><X size={18} /></button>
        <p className="eyebrow">Source {citation.n}</p>
        <h2>{citation.title ?? citation.source}</h2>
        {citation.section && <p className="muted">{citation.section}</p>}
        {citation.text
          ? <blockquote dir="auto">{citation.text}</blockquote>
          : <p className="muted">The excerpt is not available for this source.</p>}
      </aside>
    </div>
  );
}
