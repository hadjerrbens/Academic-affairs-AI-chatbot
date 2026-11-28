import type { ReactNode } from "react";

/** Small safe renderer (React escapes all text): **bold**, `code`, # headings, - / 1. lists, and [source N] markers. */
export function Markdown({ text, onCite }: { text: string; onCite?: (n: number) => void }) {
  function inline(content: string, key: string): ReactNode[] {
    return content.split(/(\*\*[^*]+\*\*|`[^`]+`|\[source\s*\d+\])/gi).filter(Boolean).map((part, i) => {
      const k = `${key}-${i}`;
      if (part.startsWith("**") && part.endsWith("**")) return <strong key={k}>{part.slice(2, -2)}</strong>;
      if (part.startsWith("`") && part.endsWith("`")) return <code key={k}>{part.slice(1, -1)}</code>;
      const cite = /^\[source\s*(\d+)\]$/i.exec(part);
      if (cite) {
        const n = Number(cite[1]);
        return <button type="button" key={k} className="cite-mark" onClick={() => onCite?.(n)} aria-label={`Open source ${n}`}>{n}</button>;
      }
      return <span key={k}>{part}</span>;
    });
  }
  const blocks: ReactNode[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;
  const flush = () => {
    if (!list) return;
    const items = list.items.map((item, i) => <li key={i}>{inline(item, `li${blocks.length}-${i}`)}</li>);
    blocks.push(list.ordered ? <ol key={`l${blocks.length}`}>{items}</ol> : <ul key={`l${blocks.length}`}>{items}</ul>);
    list = null;
  };
  text.split("\n").forEach((line, i) => {
    const bullet = /^\s*[-*•]\s+(.*)$/.exec(line);
    const number = /^\s*\d+[.)]\s+(.*)$/.exec(line);
    if (bullet || number) {
      const ordered = Boolean(number);
      if (list && list.ordered !== ordered) flush();
      list = list ?? { ordered, items: [] };
      list.items.push((bullet ?? number)![1]);
      return;
    }
    flush();
    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    if (h) blocks.push(<h4 key={i}>{inline(h[2], `h${i}`)}</h4>);
    else if (line.trim()) blocks.push(<p key={i}>{inline(line, `p${i}`)}</p>);
  });
  flush();
  return <div className="md" dir="auto">{blocks}</div>;
}
