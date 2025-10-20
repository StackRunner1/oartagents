# Target handoff implementation checklist

This checklist turns the plan into actionable, verifiable tasks across backend
and frontend with file pointers and acceptance criteria.

## Backend

- [x] Server is the routing source of truth

  - Files: `backend/app_agents/sdk_routes.py`,
    `backend/app_agents/core/store/memory_store.py`
  - Actions:
    - Use `session.active_agent_id` as the starting agent for each turn; ignore
      client-provided agent for routing.
    - Ensure session is created with a sensible default (scenario.default_root
      when available).
  - Acceptance:
    - A user turn always starts from the last server-side active agent.

- [x] Auto-apply LLM handoffs with chaining

  - Files: `backend/app_agents/sdk_routes.py`,
    `backend/app_agents/sdk_manager.py`
  - Actions:
    - In `/sdk/session/message`, loop up to `MAX_HOPS` (default 3):
      1.  Run current agent via `sdk_manager.run_agent_turn`.
      2.  Detect any `handoff_suggestion` events emitted in this hop (latest
          wins).
      3.  If present, set `session.active_agent_id` to target and emit a
          `handoff` event with `from_agent`, `to_agent`, and text "Handoff X ->
          Y"; continue.
      4.  If assistant text is produced, stop.
    - Never auto-reset to General unless suggested by the LLM.
  - Acceptance:
    - Sales question from General auto-handoffs to Sales within the same turn
      and returns a final assistant reply.

- [x] Never leave the user unanswered

  - Files: `backend/app_agents/sdk_routes.py`,
    `backend/app_agents/sdk_manager.py`
  - Actions:
    - If after chaining there’s still no assistant text, attempt a summarizer
      fallback (if present in scenario); else synthesize a short, safe default
      assistant reply (configurable via `AGENTS_DEFAULT_REPLY`).
  - Acceptance:
    - Every user message produces an assistant message event and non-empty
      `final_output`.

- [x] Standardize chat-friendly events

  - Files: `backend/app_agents/sdk_manager.py`,
    `backend/app_agents/sdk_routes.py`
  - Actions:
    - Ensure `handoff_suggestion` includes `from_agent` and `to_agent` (in
      `data`).
    - Emit `handoff` on auto-apply and include `from_agent`, `to_agent`,
      `reason`, and `text: "Handoff X -> Y"`.
    - Change manual set-active to emit `handoff_override` (and optionally a
      compatibility `handoff`) with text: "Override: X -> Y (user)".
    - On tool events, emit or augment with a concise `tool_used` message: "Tool
      used [tool_name]".
  - Acceptance:
    - FE can render simple chat lines without guessing.

- [x] Scenario-scoped catalogs

  - Files: `backend/app_agents/registry.py`, `backend/app_agents/sdk_manager.py`
  - Actions:
    - Ensure runtime uses the selected scenario and only its agents/tools.
  - Acceptance:
    - GraphViz and agent list reflect only the selected scenario.

- [x] Summarizer agent-as-tool alignment

  - Files: `backend/app_agents/sdk_manager.py`, `backend/app_agents/registry.py`
  - Actions:
    - Verify `as_tool` usage and naming follow Agents SDK docs; keep structured
      outputs for UI.
  - Acceptance:
    - Summarizer callable from General via agent-tool; tool_result includes
      `tool_name` and structured payload.

- [x] Feature flag for chaining
  - Files: `backend/app_agents/sdk_routes.py`
  - Actions:
    - Add env flag (e.g., `AGENTS_AUTO_CHAIN=1`) to toggle chaining, for safe
      rollout.
  - Acceptance:
    - Disabling the flag reverts to single-run behavior without code changes.

## Frontend

- [x] Server as source of truth for active agent

  - Files: `web/src/sdkTest.tsx`, `web/src/components/app_agents/ChatPanel.tsx`
  - Actions:
    - Stop sending agent id with user messages; update active agent based on
      `handoff`/`handoff_override` events.
  - Acceptance:
    - Agent chips always reflect the true active agent after each turn.

- [x] GraphViz auto-refresh on active agent change

  - Files: `web/src/LlmTest.tsx` or Graph component, `web/src/pages/*`
  - Actions:
    - Re-render graph on `handoff`/`handoff_override`/turn_end; use
      scenario-scoped root.
  - Acceptance:
    - Graph updates during a conversation when agents switch.

- [x] Render simple chat lines for events

  - Files: `web/src/components/app_agents/ChatPanel.tsx`
  - Actions:
    - Insert chat messages for `handoff` ("Handoff X -> Y") and `tool_used`
      ("Tool used [tool_name]").
  - Acceptance:
    - The chat shows these minimal lines alongside normal assistant/user
      messages.

- [x] Scenario-driven agent list and dynamic tools
  - Files: `web/src/*` where agent list and tools are displayed
  - Actions:
    - Filter agents by scenario; update tool availability on active agent
      change.
  - Acceptance:
    - Only cohort agents/tools are visible and updated as agent changes.

## Tests and validation

- [ ] Backend unit tests

  - Verify chaining (`handoff_suggestion` → `handoff` within a turn), tool event
    `tool_used`, and `handoff_override` semantics.

- [ ] Frontend smoke tests

  - Simulate event stream and verify chips, graph refresh, and chat lines.

- [ ] Quality gates
  - BE/FE lint/typecheck pass; dev servers start cleanly; smoke run: Sales
    question from General auto-handoffs and answers.

## Apply semantics (final)

- Single-turn override: set `session.active_agent` for the next turn only; no
  in-turn re-run.
- Emit `handoff_override` with text; FE updates chips; after next turn, agentic
  handoffs resume normally.
