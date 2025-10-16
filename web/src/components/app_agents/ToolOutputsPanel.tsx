import React from 'react';
import { ToolOutputCard } from './ToolOutputCard';

export interface ToolOutputsPanelProps {
  events: any[];
  onAction?: (action: { kind: string; payload?: any }) => void;
}

export const ToolOutputsPanel: React.FC<ToolOutputsPanelProps> = ({
  events,
  onAction,
}) => {
  const toolResults = (events || [])
    .filter((e: any) => e && e.type === 'tool_result')
    .sort((a: any, b: any) => (a.seq || 0) - (b.seq || 0));

  return (
    <section className="bg-gray-900/70 border border-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold text-sky-300">Tool Outputs</h2>
        <span className="text-[10px] text-gray-500">from events</span>
      </div>
      {toolResults.length === 0 ? (
        <div className="text-[11px] text-gray-500">No tool outputs yet</div>
      ) : (
        <ul className="space-y-2 max-h-72 overflow-auto pr-1">
          {toolResults.map((ev: any, i: number) => (
            <li key={`${ev.seq}:${i}`}>
              <ToolOutputCard
                toolName={ev?.data?.tool || 'tool'}
                text={typeof ev.text === 'string' ? ev.text : ''}
                data={ev.data}
                onAction={onAction}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
};

export default ToolOutputsPanel;
