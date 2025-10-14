import React from 'react';

export interface ToolsPanelProps {
  sessionId: string;
  baseUrl: string;
  activeAgentName: string;
  allowedTools: string[];
  onError: (msg: string) => void;
  // Optional: a list of raw events to render a Collapsible Tool Calls view
  events?: any[];
  // Show the built-in Tool Calls section (defaults to false; we now use a dedicated panel)
  showCallsSection?: boolean;
}

export const ToolsPanel: React.FC<ToolsPanelProps> = ({
  sessionId,
  baseUrl,
  activeAgentName,
  allowedTools,
  onError,
  events = [],
  showCallsSection = false,
}) => {
  const [toolBusy, setToolBusy] = React.useState<string | null>(null);
  const [toolResult, setToolResult] = React.useState<any | null>(null);
  const [lastToolStatus, setLastToolStatus] = React.useState<{
    tool: string;
    ok: boolean;
    at: string;
  } | null>(null);
  const [showCalls, setShowCalls] = React.useState(true);

  // Group tool_call + tool_result by seq proximity and tool name
  const groupedCalls = React.useMemo(() => {
    const calls: Array<{
      seq: number;
      tool: string;
      args?: any;
      result?: any;
      time?: string;
    }> = [];
    const pending: Record<string, number> = {};
    for (const ev of events) {
      if (ev.type === 'tool_call' && ev.data?.tool) {
        const idx = calls.push({
          seq: ev.seq,
          tool: ev.data.tool,
          args: ev.data.args ?? undefined,
          time: new Date(ev.timestamp_ms || Date.now()).toLocaleTimeString(),
        });
        pending[`${ev.seq}:${ev.data.tool}`] = idx - 1;
      } else if (ev.type === 'tool_result') {
        const tool = ev.data?.tool || 'unknown';
        // Try to match with the latest call for the same tool
        let pairIndex = -1;
        for (let i = calls.length - 1; i >= 0; i--) {
          if (calls[i].tool === tool && !calls[i].result) {
            pairIndex = i;
            break;
          }
        }
        if (pairIndex >= 0) {
          calls[pairIndex].result = ev.text ?? ev.output ?? ev.data ?? null;
        } else {
          calls.push({
            seq: ev.seq,
            tool,
            result: ev.text ?? ev.output ?? ev.data ?? null,
            time: new Date(ev.timestamp_ms || Date.now()).toLocaleTimeString(),
          });
        }
      }
    }
    return calls.sort((a, b) => a.seq - b.seq);
  }, [events]);

  return (
    <div className="bg-gray-900/70 border border-gray-800 rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-indigo-300">Tools</h3>
        <span className="text-[10px] text-gray-500">agent-scoped</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {allowedTools.length === 0 && (
          <span className="text-[11px] text-gray-500">No tools allowed</span>
        )}
        {allowedTools.map((tool) => (
          <button
            key={tool}
            disabled={!sessionId || toolBusy === tool}
            onClick={async () => {
              onError('');
              setToolResult(null);
              setToolBusy(tool);
              try {
                const r = await fetch(
                  `${baseUrl}/api/tools/execute?scenario_id=default&session_id=${encodeURIComponent(
                    sessionId
                  )}`,
                  {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                      tool,
                      args: { agent: activeAgentName },
                    }),
                  }
                );
                const data = await r.json();
                const ok = r.ok;
                if (!ok) throw new Error(data?.error || 'tool failed');
                setToolResult(data);
                setLastToolStatus({
                  tool,
                  ok: true,
                  at: new Date().toISOString(),
                });
              } catch (e: any) {
                onError(e.message);
                setLastToolStatus({
                  tool,
                  ok: false,
                  at: new Date().toISOString(),
                });
              } finally {
                setToolBusy(null);
              }
            }}
            className="text-[11px] px-2 py-1 rounded border border-gray-700 hover:bg-gray-800 text-gray-300 disabled:opacity-40">
            {tool}
          </button>
        ))}
      </div>
      {lastToolStatus && (
        <div
          className={`text-[11px] ${
            lastToolStatus.ok ? 'text-teal-300' : 'text-red-300'
          }`}>
          Last: {lastToolStatus.tool} — {lastToolStatus.ok ? 'ok' : 'error'} (
          {new Date(lastToolStatus.at).toLocaleTimeString()})
        </div>
      )}
      {toolResult && (
        <pre className="text-[11px] bg-gray-950 border border-gray-800 rounded p-2 overflow-auto max-h-40">
          {JSON.stringify(toolResult, null, 2)}
        </pre>
      )}
      {showCallsSection && (
        <div className="pt-2 border-t border-gray-800">
          <div className="flex items-center justify-between mb-1">
            <h4 className="text-[12px] font-semibold text-indigo-300">
              Tool Calls
            </h4>
            <button
              onClick={() => setShowCalls((v) => !v)}
              className="text-[10px] text-gray-400 hover:text-gray-200">
              {showCalls ? 'Hide' : 'Show'}
            </button>
          </div>
          {showCalls ? (
            groupedCalls.length === 0 ? (
              <div className="text-[11px] text-gray-500">
                No tool activity yet
              </div>
            ) : (
              <ul className="space-y-1 max-h-40 overflow-auto pr-1">
                {groupedCalls.map((c, i) => (
                  <li key={`${c.seq}:${i}`} className="text-[11px]">
                    <div className="flex items-center justify-between">
                      <span className="text-indigo-200">
                        #{c.seq} {c.tool}
                      </span>
                      {c.time && (
                        <span className="text-[10px] text-gray-500">
                          {c.time}
                        </span>
                      )}
                    </div>
                    {c.args && (
                      <pre className="mt-1 bg-gray-950 border border-gray-800 rounded p-2 text-[10px] overflow-auto">
                        {JSON.stringify(c.args, null, 2)}
                      </pre>
                    )}
                    {typeof c.result !== 'undefined' && (
                      <pre className="mt-1 bg-gray-950 border border-gray-800 rounded p-2 text-[10px] overflow-auto">
                        {typeof c.result === 'string'
                          ? c.result
                          : JSON.stringify(c.result, null, 2)}
                      </pre>
                    )}
                  </li>
                ))}
              </ul>
            )
          ) : null}
        </div>
      )}
    </div>
  );
};
