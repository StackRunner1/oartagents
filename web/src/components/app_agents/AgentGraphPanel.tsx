import React from 'react';

export interface AgentGraphPanelProps {
  baseUrl: string;
  scenarioId?: string;
  rootAgent?: string;
  containerClassName?: string; // allow parent to size like Chat panel
}

export const AgentGraphPanel: React.FC<AgentGraphPanelProps> = ({
  baseUrl,
  scenarioId = 'default',
  rootAgent,
  containerClassName,
}) => {
  const [imgB64, setImgB64] = React.useState<string | null>(null);
  const [format, setFormat] = React.useState<'png' | 'svg' | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${baseUrl}/api/sdk/agents/visualize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scenario_id: scenarioId,
          root_agent: rootAgent || null,
          return_dot: false,
        }),
      });
      const data = await r.json();
      if (!r.ok || !data?.ok)
        throw new Error(data?.detail || data?.error || 'viz failed');
      setImgB64(data.image_base64 || null);
      setFormat((data.format as 'png' | 'svg') || 'png');
    } catch (e: any) {
      setError(e.message);
      setImgB64(null);
      setFormat(null);
    } finally {
      setLoading(false);
    }
  }, [baseUrl, scenarioId, rootAgent]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div
      className={`bg-gray-900/70 border border-gray-800 rounded-lg p-4 space-y-3 ${
        containerClassName || ''
      }`}>
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-indigo-300">Agent Graph</h3>
        <div className="flex items-center gap-2">
          <button
            onClick={() => void refresh()}
            className="text-[10px] px-2 py-1 rounded border border-gray-700 hover:bg-gray-800 text-gray-300 disabled:opacity-40"
            disabled={loading}>
            {loading ? 'Rendering...' : 'Refresh'}
          </button>
        </div>
      </div>
      {error && <div className="text-[11px] text-amber-400">{error}</div>}
      {imgB64 ? (
        format === 'svg' ? (
          <img
            alt="Agent Graph"
            src={`data:image/svg+xml;base64,${imgB64}`}
            className="w-full h-full object-contain rounded border border-gray-800"
          />
        ) : (
          <img
            alt="Agent Graph"
            src={`data:image/png;base64,${imgB64}`}
            className="w-full h-full object-contain rounded border border-gray-800"
          />
        )
      ) : (
        <div className="text-[11px] text-gray-500">No graph available.</div>
      )}
    </div>
  );
};
