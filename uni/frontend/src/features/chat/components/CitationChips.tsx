import { FileText } from "lucide-react";

export type Citation = { n: number; source?: string; title?: string; section?: string; text?: string };

export function CitationChips({ citations, onOpen }: { citations: Citation[]; onOpen: (c: Citation) => void }) {
  if (!citations.length) return null;
  return (
    <div className="chips" aria-label="Sources">
      {citations.map(c => (
        <button type="button" key={c.n} className="chip" onClick={() => onOpen(c)}>
          <FileText size={13} aria-hidden /> <span className="chip-n">{c.n}</span> {c.title ?? c.source ?? "Source"}
        </button>
      ))}
    </div>
  );
}
