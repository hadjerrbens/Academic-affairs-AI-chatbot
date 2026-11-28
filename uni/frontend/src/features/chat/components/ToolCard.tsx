import { AlertCircle, CheckCircle2 } from "lucide-react";
import { TOOL_LABELS } from "../topics";

export type ToolEvent = { name?: string; ok?: boolean };

/** One quiet line per tool the assistant used, so students see where the numbers came from. */
export function ToolCard({ tool }: { tool: ToolEvent }) {
  const name = tool.name ?? "tool";
  const label = TOOL_LABELS[name] ?? name.replace(/_/g, " ");
  const ok = tool.ok !== false;
  return (
    <span className={`tool-pill ${ok ? "ok" : "fail"}`}>
      {ok ? <CheckCircle2 size={14} aria-hidden /> : <AlertCircle size={14} aria-hidden />}
      {ok ? label : `${label} (could not complete)`}
    </span>
  );
}
