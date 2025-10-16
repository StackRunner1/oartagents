import React from 'react';

export interface ContextPanelProps {
  baseUrl: string;
  sessionId: string;
}

export const ContextPanel: React.FC<ContextPanelProps> = ({
  baseUrl,
  sessionId,
}) => {
  const [ctx, setCtx] = React.useState<any | null>(null);
  const [err, setErr] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  async function load() {
    if (!sessionId) return;
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch(
        `${baseUrl}/api/sdk/session/context?session_id=${encodeURIComponent(
          sessionId
        )}`
      );
      if (!r.ok) throw new Error(await r.text());
      const data = await r.json();
      setCtx(data?.context ?? {});
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  React.useEffect(() => {
    if (sessionId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  return (
    <section className="bg-gray-900/70 border border-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold text-emerald-300">Context</h2>
        <button
          onClick={load}
          className="text-[11px] px-2 py-1 rounded border border-gray-700 hover:bg-gray-800 text-gray-300">
          Refresh
        </button>
      </div>
      {err && <div className="text-[11px] text-amber-300">{err}</div>}
      {!ctx || Object.keys(ctx).length === 0 ? (
        <div className="text-[11px] text-gray-500">No context set.</div>
      ) : (
        <pre className="text-[11px] bg-black/30 border border-emerald-900 rounded p-2 overflow-auto max-h-64">
          {JSON.stringify(ctx, null, 2)}
        </pre>
      )}
    </section>
  );
};

export default ContextPanel;
