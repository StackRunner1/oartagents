import { describe, it, expect } from 'vitest';
import { buildChatMessages } from '../src/lib/chat';

describe('buildChatMessages tool events', () => {
  it('renders tool_result with envelope and resolves tool name', () => {
    const ev = {
      type: 'tool_result',
      seq: 2,
      timestamp_ms: Date.now(),
      tool_name: 'summarizer_agent_tool',
      data: {
        tool: 'summarizer_agent_tool',
        tool_name: 'summarizer_agent_tool',
        output: { summary: 'Hello', bullets: ['a', 'b'] },
        envelope: {
          ok: true,
          name: 'summarizer_agent_tool',
          args: { text: 'Hello' },
          data: { summary: 'Hello' },
          meta: {
            agent_tool: 'summarizer',
            tool_kind: 'agent_as_tool',
            from_agent: 'general',
          },
          recommended_prompts: ['Shorter TL;DR'],
        },
      },
      text: 'Hello\n• a\n• b',
    } as any;
    const msgs = buildChatMessages([ev], [], [], { source: 'sdk' });
    expect(msgs.length).toBe(1);
    expect(msgs[0].kind).toBe('tool');
    expect(msgs[0].toolName).toBe('summarizer_agent_tool');
    // Prefer provided text
    expect(msgs[0].text).toContain('Hello');
    // Envelope should be passed through in raw
    expect(msgs[0].raw?.data?.envelope?.name).toBe('summarizer_agent_tool');
  });

  it('renders tool_call with args as text', () => {
    const ev = {
      type: 'tool_call',
      seq: 1,
      timestamp_ms: Date.now(),
      data: { tool_name: 'WebSearchTool', args: { query: 'today news' } },
    } as any;
    const msgs = buildChatMessages([ev], [], [], { source: 'sdk' });
    expect(msgs.length).toBe(1);
    expect(msgs[0].kind).toBe('tool');
    expect(msgs[0].toolName).toBe('WebSearchTool');
    expect(msgs[0].text).toContain('today news');
  });
});
