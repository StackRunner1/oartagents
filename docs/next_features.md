# what we target next (in order of priority):

### Legend Key for task lists

[x] = complete [~] = in progress [ ] = pending , not started

## Primary Features to implement next

- [x] Assistant message rendering: tighten fallback paths and formatting
- [~] Handoff/agent indicators: show root-change suggestions, highlight active agent, and surface allowed tools
- [x] Improve multi-agent orchestration (LLM-only native handoffs per official docs)
- [x] Tool call visibility: clearer grouping, collapsible details
- [x] Optimistic rendering of user messages (with reconciliation)
- [x] Context Management per official documentation (session context API and injection)
- [ ] Implement basic Guardrails (reusable, per official docs)
- [~] Build a new Agent and enable built-in tools (WebSearch on; Code Interpreter gated)
- [~] Event stream UX: smoother auto-scroll, timestamps, compact system/tool events
- [ ] Transcript refresh: explicit sync button and smarter auto-refresh
- [ ] Retry/send state: disable send during in-flight, show retry on error

## Implementation Task Checklist: Assistant message rendering: tighten fallback paths and formatting

- [x] Harden SDK imports and session fallback paths
- [x] Guard model selection (avoid realtime in text flows)
- [x] Ensure assistant event always appended; robust text extraction

## Implementation Task Checklist: Handoff/agent indicators

- [x] Define UI goals: inline system message and header badge when orchestrator suggests a root change
- [x] Extend ChatPanel props to accept `handoffEvents`
- [x] Render a compact header badge showing the latest suggested target (e.g., "Handoff: Sales")
- [x] Append inline system messages in the chat body for each suggestion: `from → to — reason`
- [x] Wire handoff events state from sdkTest to ChatPanel
- [ ] Sort-merge handoff messages chronologically into chat stream (by `at`) — currently shown in a dedicated section
- [x] Action buttons to Apply/Dismiss (Apply switches agent immediately)

## New platform-aligned tasks (from main app context)

I gave you the context to we can make and implement som critical design decision
for the agent sdk implementaiton now. BUT this is only in preparation of
integrating this work LATER into the main app. So NONE of the actual tools or
agents need to be written in code. BUT we want to have the code setup here
correctly (with simulated entry point or placeholder agent / tool in THIS
project so that WHEN WE migrate the files/folder into the main project, it is a
'plug-and-play approach)

- [x] Context-aware agent runtime: attach a placeholder context to every turn
      (SDK Context API)
  - the final path in the main project is pages/projects/[projectId]/ (+ various
    pages wihtin that)
  - BUT the real feature (and task) to implement is "Centext Management" (see
    item in main feature list!)
- [ ] CRUD tools for project object tree (create/update tasks, assign members),
      with auth via service account scoped to project
- [ ] Agent groups: define multiple cohesive groups (e.g., Planning vs
      Execution) with supervisor per group and inter-group handoffs
- [ ] Ever-present chat integration contract: minimal SDK interface to embed in
      main app drawer
- [ ] Dual-surface responses: structured actions (forms/patches) alongside chat
      messages
- [ ] Session identity: dedicated agent-user per project with Supabase auth/role
      mapping

## SDK-aligned architecture and implementation plan (native handoffs, agents-as-tools, ToolContext)

This section documents what we will implement next to align fully with the
official Agents SDK and to match the future needs of the main app. It covers
architecture choices, concrete tasks, and acceptance criteria.

### Architectural recommendation (now: LLM-only orchestration)

- Central entry point: Keep a single entry agent ("orchestrator") that users
  always talk to via the ever-present chat. This orchestrator is a normal Agent
  configured with: - Native handoffs to specialized agents for control
  transfer. - Agents-as-tools for call-and-return sub-tasks where control should
  not transfer. - A curated toolset (function tools and hosted tools), with
  dynamic enablement via `is_enabled` and runtime context.
- Handoffs policy: For this phase, orchestrate handoffs via the LLM only. We
  will add code-based orchestration later and can mix approaches per the
  official multi-agent guidance.
- Agent groups: Model cohesive clusters of agents (e.g., General, Sales,
  Support, Admin-Content) as an "agent group" definition. Each group can have
  its own orchestrator, sub-agents, handoff graph, and tool allowlists.

Rationale

- LLM-only keeps flexibility while we iterate prompts and tool availability.
- Native SDK handoffs and agents-as-tools give us first-class visibility,
  recommended prompts, and fewer custom shims.
- Agent groups map well to your main app domains and future multi-tenant setups.

### Native handoffs (replace custom supervisor handoff tool)

- Replace the custom `"handoff"` function tool approach with true SDK
  handoffs: - Construct agents with
  `Agent(..., handoffs=[handoff(target_agent, ...), ...])` based on the group
  definition. - Apply
  `agents.extensions.handoff_prompt.RECOMMENDED_PROMPT_PREFIX` (or
  `prompt_with_handoff_instructions`) to any agent that can handoff, not just
  conditionally. - Use `on_handoff` callbacks to log/trace handoff decisions and
  optionally kick off background fetches. - Optionally set `input_type` for
  structured handoff reasons and `input_filter` to sanitize/trim history.

Acceptance criteria

- [x] Handoff events are emitted without the custom supervisor tool
- [x] The LLM chooses a target agent using native handoffs and we persist the active agent with reason
- [x] Handoff prompt is consistently present on all agents with handoffs

### Agents-as-tools (subroutine calls without control transfer)

- For tasks like translate/summarize/fetch-data, expose specialized agents to
  the orchestrator via
  `some_agent.as_tool(tool_name=..., tool_description=..., is_enabled=...)`.
- Optionally supply `custom_output_extractor` to return structured payloads back
  to the orchestrator.

Acceptance criteria

- [ ] At least one example agent is wired as a tool and invoked by the orchestrator for a subtask; control returns to the orchestrator

### ToolContext / RunContextWrapper and dynamic gating

- Add per-session context storage and API: - `POST /api/sdk/session/context` to
  upsert session context (e.g.,
  `session_id, user_id, project_id, roles, feature_flags, extra`). - Store in
  our memory store and pass into `Runner.run(..., context=...)`.
- Update function tools to accept `ctx: RunContextWrapper[Any]` (or ToolContext)
  as the first parameter when appropriate, enabling access to runtime state.
- Use `is_enabled` (bool or callable) on tools and agents-as-tools to
  dynamically gate availability based on `ctx` (e.g., admin-only tools,
  project-scoped tools).

Acceptance criteria

- [x] Tools can read `ctx.context` fields (e.g., project_id) and conditionally enable behavior
- [x] A protected tool is hidden for non-admin sessions (verified in Tool Calls / logs)

### Tool library design and discovery

- Structure - Organize tools by domain folders (e.g., `tools/catalog/`,
  `tools/content/`, `tools/admin/`). - Prefer Pydantic models for tool params;
  enforce strict JSON schema generation (no additionalProperties unless
  explicitly allowed).
- Metadata & governance - Add tool metadata: tags, roles/permissions, rate
  limits, cost hints, version. - Centralize secrets; guard “dangerous” tools
  with environment flags.
- Discovery - Create a read-only catalog endpoint `GET /api/tools/catalog` (for
  UI and optional LLM discovery tool). - Optional function tool
  `search_tools(query)` to let the LLM discover tools by tags and descriptions.

Acceptance criteria

- [x] Catalog lists tools with metadata; UI shows which tools are available to the active agent/session
- [ ] Discovery tool returns relevant tools when prompted (optional, behind a flag)

### Rename "scenarios" to "agent_groups"

- Migrate `ScenarioDefinition` to `AgentGroupDefinition` (keep fields:
  `id/label/default_root/agents/description`).
- Add a compatibility shim so existing `scenario_id` params continue to work
  while we update FE.
- Plan CRUD endpoints (later): create/update/delete groups; assign group per
  session or tenant.

Acceptance criteria

- [ ] Code and docs use "agent groups" terminology; FE still works via the compatibility shim

### UI updates & observability

- Tool Calls: move to a dedicated sidebar card, grouped by call and tool,
  collapsible.
- Handoff indicators: continue header badge and inline system messages; add
  Apply/Dismiss actions.
- Show active agent and its available tools (post-gating) in the Tools
  component.
- Improve event timestamps and compact formatting; ensure handoff events are
  chronological with chat messages.

Acceptance criteria

- [x] Tool Calls are clearer and separated from the actions list
- [x] Handoff actions work and update active agent immediately

### Phased implementation plan

Phase 1

- [x] Native handoffs for existing agents (General/Sales/Support) with recommended prompt
- [x] Add ToolContext/RunContextWrapper support in tools; add `POST /api/sdk/session/context` and inject into runs
- [x] Implement `is_enabled` dynamic gating for at least one tool (roles-based) and wire gating in tool resolution
- [x] Move Tool Calls to dedicated card; add basic Apply/Dismiss wiring (UI shell)

Phase 2

- [ ] Agents-as-tools example (e.g., a summarizer or translator agent) with `custom_output_extractor`
- [ ] Tool discovery endpoint and optional discovery tool
- [ ] Migrate "scenarios" to "agent_groups" (keep shim), and begin defining 1-2 additional groups (e.g., Admin-Content)

Phase 3

- [ ] Introduce code-based orchestration for select flows and combine with LLM-only routing
- [ ] Expand tool library structure with namespaces, metadata, and tests
- [ ]Harden permissions and rate limits; add guardrails integration per docs

### Detailed task checklist (executable)

Handoffs (native)

- [x] Replace supervisor custom handoff tool with native `Agent.handoffs` for existing agents
- [x] Apply `handoff_prompt` to all handoff-capable agents
- [x] Add `on_handoff` callback to log reason and target; consider `input_type` for structured reasons
- [ ] Optionally apply `input_filter` (e.g., remove tools) from `agents.extensions.handoff_filters`

Agents-as-tools

- [ ] Create at least one example specialized agent exposed via `as_tool(...)` to the orchestrator
- [ ] Optionally add `custom_output_extractor` to return structured payloads

Context + ToolContext

- [x] Add `POST /api/sdk/session/context`; persist to store; pass into `Runner.run`
- [x] Update tools to accept `ctx` and use `ctx.context` fields
- [x] Implement `is_enabled`/roles gating on registry tools based on context roles/flags

Tool library & discovery

- [ ] Introduce folder structure and typed param models; enforce strict schemas
- [x] Add `GET /api/tools/catalog`; (optional) `search_tools` function tool pending

Rename scenarios → agent_groups

- [ ] Add new `AgentGroupDefinition` and back-compat shim for `scenario_id`
- [ ] Update docs and references; postpone FE param rename to a later PR

UI & UX

- [x] Split Tool Calls into its own card; show currently available tools for the active agent
- [x] Handoff Apply/Dismiss buttons; chronological merge still pending
- [x] Move Agent Graph into a new right column; widen page if needed
- [x] Place Handoff Actions directly below chat

### Acceptance criteria (summary)

- Native handoffs functioning with recommended prompts and event logging.
- Example agents-as-tools subroutine verified end-to-end.
- Session context is settable; tools receive `ctx`; `is_enabled` gates tools
  reliably.
- Tool catalog endpoint returns metadata; Tool Calls panel clearly shows
  calls/results.
- Terminology migrated to agent groups with a temporary shim; UI remains
  functional.

## Scenarios → Agent Groups: recommended sequence

1) Introduce AgentGroupDefinition alongside ScenarioDefinition (compat layer)
- Add `AgentGroupDefinition` with fields: `id`, `label`, `description`, `default_root`, `agents`
- Keep existing `scenario_id` query params; internally map `scenario_id` to a group via a shim
- Extend registry to hold both (`agent_groups` as the primary source; `scenarios` becomes an alias)

2) Context-driven mounting and dynamic equipping
- At session create, derive `agent_group_id` from app context (route: page/projects/[projectId], user role)
- Inject `app_location`, `project_id`, `org_id`, `roles` into session context
- Use `is_enabled(ctx)` to gate tools and agents-as-tools; mount the correct group and toolset dynamically

3) Catalog expansion and discovery
- Expand `/api/tools/catalog` to include metadata (tags, roles_required, cost hints); add grouping by agent group
- Add optional `GET /api/tools/search?query=` and an LLM discovery tool (behind a feature flag)

4) Gradual FE migration
- Update UI labels to say "Agent Group"; keep using `scenario_id` under the hood
- Introduce a switcher UI for selecting agent groups per context (later)

5) Finalize migration
- Deprecate `scenarios` naming in code after FE fully migrated; keep shim for at least one release

Rationale: This path lets us integrate new functionality (catalog, dynamic equipping, agents-as-tools) immediately while moving terminology and APIs safely, preserving current FE and preparing for export to the main app.

## Next batch of tasks (proposed)

1. Visualization UX polish

- Add a small header toolbar on Agent Graph: Download SVG/DOT, Health check
  badge (dot found / not found)
- Button to toggle SVG/PNG (for debugging) and auto-refresh on handoff apply

2. Handoff timeline coherence

- Merge handoff events chronologically with chat messages (by timestamp)
- Add a compact status strip above Chat showing “Active: <agent>” and last
  switch reason

3. Agents-as-tools example and discovery

- Add one minimal agent-as-tool (e.g., summarizer) wired to orchestrator via `as_tool`
- [x] Create `GET /api/tools/catalog` and surface available tools in ToolsPanel

4. Rename scenarios → agent_groups (shim)

- Introduce `AgentGroupDefinition` and a compatibility shim for `scenario_id`
- Update backend docs and comments; surface new term in UI labels (keep API
  param via shim)

5. Deployment readiness: Graphviz on Fly.io

- Add Dockerfile or buildpack steps to install Graphviz; set `GRAPHVIZ_DOT`
- Expose viz health on UI and link to troubleshooting tips

6. Tests and types

- Add minimal tests for tool gating and context injection
- Tighten types for event shapes (tool_call/tool_result) and agent graph
  response
