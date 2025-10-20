import React from 'react';

export interface HandoffSuggestionItem {
  id: string;
  from: string;
  to: string;
  reason: string;
  at: string; // ISO string
  recommended_prompts?: string[];
}

export interface HandoffSuggestionsPanelProps {
  items: HandoffSuggestionItem[];
  onApply: (targetAgent: string) => void;
  onDismiss: (id: string) => void;
}

export const HandoffSuggestionsPanel: React.FC<
  HandoffSuggestionsPanelProps
> = ({ items, onApply, onDismiss }) => {
  return (
    <section className="bg-gray-900/70 border border-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold text-indigo-300">
          Handoff Suggestions
        </h2>
        <span className="text-[10px] text-gray-500">
          {items.length} suggestion{items.length === 1 ? '' : 's'}
        </span>
      </div>
      {items.length === 0 ? (
        <div className="text-[11px] text-gray-500">No suggestions</div>
      ) : (
        <ul className="space-y-2 max-h-64 overflow-auto pr-1">
          {items.map((h) => (
            <li
              key={h.id}
              className="flex items-center justify-between bg-gray-950 border border-gray-800 rounded p-2">
              <div className="text-[12px] text-indigo-100 flex-1 pr-2">
                <span className="font-semibold">{h.from}</span> →{' '}
                <span className="font-semibold">{h.to}</span>
                {h.reason ? (
                  <span className="opacity-80"> — {h.reason}</span>
                ) : null}
                {h.at ? (
                  <span className="ml-2 text-[10px] opacity-60">
                    [{new Date(h.at).toLocaleTimeString()}]
                  </span>
                ) : null}
                {!!h.recommended_prompts?.length && (
                  <div className="mt-1 text-[11px] text-indigo-200/90">
                    Recommended prompts:
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {h.recommended_prompts.map((p, idx) => (
                        <span
                          key={idx}
                          className="px-1.5 py-0.5 rounded border border-indigo-700 bg-indigo-900/40 text-indigo-100"
                          title={p}>
                          {p}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => onApply(h.to)}
                  className="text-[11px] px-2 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white">
                  Apply
                </button>
                <button
                  onClick={() => onDismiss(h.id)}
                  className="text-[11px] px-2 py-1 rounded border border-gray-700 hover:bg-gray-800 text-gray-300">
                  Dismiss
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};

export default HandoffSuggestionsPanel;
