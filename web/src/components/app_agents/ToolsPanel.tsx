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
  scenarioId?: string;
}

export const ToolsPanel: React.FC<ToolsPanelProps> = ({
  sessionId,
  baseUrl,
  activeAgentName,
  allowedTools,
  onError,
  events = [],
  showCallsSection = false,
  scenarioId = 'default',
}) => {
  const [toolBusy, setToolBusy] = React.useState<string | null>(null);
  const [toolResult, setToolResult] = React.useState<any | null>(null);
  const [lastToolStatus, setLastToolStatus] = React.useState<{
    tool: string;
    ok: boolean;
    at: string;
  } | null>(null);
  const [showCalls, setShowCalls] = React.useState(true);
  const [catalogOpen, setCatalogOpen] = React.useState(false);
  const [toolCatalog, setToolCatalog] = React.useState<
    { name: string; description?: string | null; params?: any }[]
  >([]);
  const [agentTools, setAgentTools] = React.useState<string[]>([]);

  // Fetch the global tools list with descriptions for display
  React.useEffect(() => {
    let alive = true;
    async function fetchCatalog() {
      try {
        const r = await fetch(`${baseUrl}/api/tools/list`);
        const data = await r.json();
        if (!r.ok) throw new Error(data?.error || 'failed to load tools');
        if (alive) setToolCatalog(data || []);
      } catch (e) {
        // Non-fatal; ignore
      }
    }
    fetchCatalog();
    return () => {
      alive = false;
    };
  }, [baseUrl]);

  // Fetch per-agent catalog to discover agents-as-tools for the active agent
  React.useEffect(() => {
    let alive = true;
    async function fetchAgentTools() {
      try {
        const r = await fetch(
          `${baseUrl}/api/tools/catalog?scenario_id=${encodeURIComponent(
            scenarioId
          )}`
        );
        const data = await r.json();
        if (r.ok && Array.isArray(data)) {
          const aName = (activeAgentName || '').toLowerCase();
          const entry = data.find(
            (x: any) => (x.agent || '').toLowerCase() === aName
          );
          if (alive) setAgentTools(entry?.agent_tools || []);
        } else if (alive) {
          setAgentTools([]);
        }
      } catch {
        if (alive) setAgentTools([]);
      }
    }
    fetchAgentTools();
    return () => {
      alive = false;
    };
  }, [baseUrl, activeAgentName, scenarioId]);

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

      {/* Agents-as-Tools (read-only) */}
      <div className="pt-2 border-t border-gray-800">
        <div className="flex items-center justify-between mb-1">
          <h4 className="text-[12px] font-semibold text-indigo-300">
            Agents-as-Tools
          </h4>
          <span className="text-[10px] text-gray-500">invoked by LLM</span>
        </div>
        {agentTools.length === 0 ? (
          <div className="text-[11px] text-gray-500">None</div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {agentTools.map((n) => (
              <span
                key={n}
                className="text-[11px] px-2 py-1 rounded border border-gray-700 bg-gray-900/60 text-indigo-200"
                title="Exposed as a tool to this agent at runtime">
                {n}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Catalog (read-only) */}
      <div className="pt-2 border-t border-gray-800">
        <div className="flex items-center justify-between mb-1">
          <h4 className="text-[12px] font-semibold text-indigo-300">Catalog</h4>
          <button
            onClick={() => setCatalogOpen((v) => !v)}
            className="text-[10px] text-gray-400 hover:text-gray-200">
            {catalogOpen ? 'Hide' : 'Show'}
          </button>
        </div>
        {catalogOpen && (
          <ul className="space-y-2 max-h-40 overflow-auto pr-1">
            {toolCatalog.length === 0 ? (
              <li className="text-[11px] text-gray-500">No tools</li>
            ) : (
              toolCatalog.map((t) => {
                const enabled = allowedTools.includes(t.name);
                return (
                  <li
                    key={t.name}
                    className="bg-gray-950 border border-gray-800 rounded p-2">
                    <div className="flex items-center justify-between">
                      <div className="text-[12px] text-indigo-100">
                        {t.name}
                      </div>
                      <button
                        disabled={!enabled || !sessionId || toolBusy === t.name}
                        onClick={async () => {
                          // Run only if enabled for this agent
                          if (!enabled) return;
                          onError('');
                          setToolResult(null);
                          setToolBusy(t.name);
                          try {
                            const r = await fetch(
                              `${baseUrl}/api/tools/execute?scenario_id=default&session_id=${encodeURIComponent(
                                sessionId
                              )}`,
                              {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                  tool: t.name,
                                  args: { agent: activeAgentName },
                                }),
                              }
                            );
                            const data = await r.json();
                            if (!r.ok)
                              throw new Error(data?.error || 'tool failed');
                            setToolResult(data);
                            setLastToolStatus({
                              tool: t.name,
                              ok: true,
                              at: new Date().toISOString(),
                            });
                          } catch (e: any) {
                            onError(e.message);
                            setLastToolStatus({
                              tool: t.name,
                              ok: false,
                              at: new Date().toISOString(),
                            });
                          } finally {
                            setToolBusy(null);
                          }
                        }}
                        className={`text-[10px] px-2 py-1 rounded border ${
                          enabled
                            ? 'border-gray-700 hover:bg-gray-800 text-gray-300'
                            : 'border-gray-800 bg-gray-900/50 text-gray-500 cursor-not-allowed'
                        }`}>
                        {enabled ? 'Run' : 'Disabled'}
                      </button>
                    </div>
                    {t.description && (
                      <div className="mt-1 text-[11px] text-gray-400">
                        {t.description}
                      </div>
                    )}
                  </li>
                );
              })
            )}
          </ul>
        )}
        {/* Agents-as-tools for this agent (read-only, invoked by LLM) */}
        {catalogOpen && (
          <div className="mt-2">
            <div className="text-[11px] text-gray-400 mb-1">Agent Tools</div>
            {agentTools.length === 0 ? (
              <div className="text-[11px] text-gray-500">None</div>
            ) : (
              <div className="flex flex-wrap gap-1">
                {agentTools.map((n) => (
                  <span
                    key={n}
                    className="text-[10px] px-2 py-0.5 rounded border border-gray-800 bg-gray-900/60 text-indigo-200"
                    title="Exposed as a tool to this agent at runtime">
                    {n}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
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
