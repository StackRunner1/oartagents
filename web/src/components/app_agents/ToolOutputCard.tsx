import React, { useMemo, useState } from 'react';

export interface ToolOutputCardProps {
  toolName: string;
  text: string; // concise text to display (already shaped on backend)
  data?: any; // event.data including optional extra.parsed
  onAction?: (action: { kind: string; payload?: any }) => void; // for navigation/open panels
  compact?: boolean; // compact chat mode: only show a one-liner
}

function isObject(v: any): v is Record<string, any> {
  return v && typeof v === 'object' && !Array.isArray(v);
}

export const ToolOutputCard: React.FC<ToolOutputCardProps> = ({
  toolName,
  text,
  data,
  onAction,
  compact = false,
}) => {
  // Normalize tool name from various fields
  const resolvedName = useMemo(() => {
    const rawCandidates = [data?.tool, data?.tool_name, data?.name, toolName];
    const candidates = (rawCandidates.filter(Boolean) as string[]).map((s) =>
      s.toString()
    );
    const first = candidates.find(
      (n) => n && n.trim() && n.trim().toLowerCase() !== 'tool'
    );
    return first || '';
  }, [toolName, data]);
  const [expanded, setExpanded] = useState(false);
  const parsed = useMemo(() => {
    const p = data?.extra?.parsed;
    return isObject(p) ? p : undefined;
  }, [data]);

  // Derive generic quick actions, reusable in main app
  // Example mapping: summarizer outputs -> Open Summary Panel
  const actions = useMemo(() => {
    const acts: { label: string; kind: string; payload?: any }[] = [];
    if (resolvedName.toLowerCase().startsWith('summarizer')) {
      acts.push({
        label: 'Open Summary',
        kind: 'open_summary',
        payload: parsed || { text },
      });
    }
    // Example for a FileSearch or WebSearch: link into app routes/panels
    if (resolvedName.toLowerCase().includes('websearch')) {
      acts.push({
        label: 'View Web Sources',
        kind: 'show_web_sources',
        payload: parsed,
      });
    }
    return acts;
  }, [resolvedName, parsed, text]);

  if (compact) {
    const hasName =
      resolvedName &&
      resolvedName.toLowerCase() !== 'tool' &&
      resolvedName.trim() !== '';
    const label = hasName ? `Used ${resolvedName} tool` : 'Used tool';
    return (
      <div className="rounded-md border border-sky-800 bg-sky-950/40 text-sky-100">
        <div className="px-3 py-2 flex items-start justify-between gap-2">
          <div className="text-xs font-medium">
            <span className="px-1.5 py-0.5 rounded bg-sky-800/60 border border-sky-700 mr-2">
              Tool
            </span>
            <span className="opacity-90">{label}</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-sky-800 bg-sky-950/40 text-sky-100">
      <div className="px-3 py-2 flex items-start justify-between gap-2">
        <div className="text-xs font-medium">
          <span className="px-1.5 py-0.5 rounded bg-sky-800/60 border border-sky-700 mr-2">
            Tool
          </span>
          <span className="opacity-90">
            {resolvedName && resolvedName.toLowerCase() !== 'tool'
              ? resolvedName
              : '(unknown tool)'}
          </span>
        </div>
        <div className="flex gap-2">
          {actions.map((a) => (
            <button
              key={a.kind}
              onClick={() => onAction?.({ kind: a.kind, payload: a.payload })}
              className="text-[10px] px-2 py-1 rounded border border-sky-700 hover:bg-sky-800/40">
              {a.label}
            </button>
          ))}
          {parsed ? (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="text-[10px] px-2 py-1 rounded border border-sky-700 hover:bg-sky-800/40"
              aria-expanded={expanded}>
              {expanded ? 'Hide details' : 'Show details'}
            </button>
          ) : null}
        </div>
      </div>
      <div className="px-3 pb-3 text-sm whitespace-pre-wrap break-words">
        {text || <span className="opacity-60">(no textual output)</span>}
      </div>
      {expanded && parsed ? (
        <div className="px-3 pb-3 text-[11px]">
          <pre className="bg-black/30 border border-sky-900 rounded p-2 overflow-auto max-h-72">
            {JSON.stringify(parsed, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
};

export default ToolOutputCard;
