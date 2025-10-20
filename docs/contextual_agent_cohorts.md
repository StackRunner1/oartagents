# Contextual Agent Cohorts

A quick guide to running multiple agent cohorts (aka scenarios) side-by-side,
switching between them in the UI, and governing tools and agents-as-tools with
simple allowlists.

## Current status (TL;DR)

- Scenario switching works with correct default roots; the active agent persists
  until you explicitly Apply a handoff.
- Handoff Suggestions panel lives in the right column, with a compact inline
  chip shown in Chat; Apply/Dismiss works.
- Tools are resolved per agent with roles-based gating; Tool Outputs, Context,
  and Usage panels are functional.
- Visualization is stable for agents and handoffs; agents-as-tools aren’t
  consistently visualized yet.
- Tool names are occasionally missing in chat/panel; we’ll make this 100%
  reliable in a follow-up.
- Overall session creation and event flows are stable after reverting risky viz
  edits.

## Why cohorts (scenarios)?

- Separation of concerns: Keep related agents and tools grouped by business
  context (e.g., Default: General/Sales/Support vs Project Planning:
  Planner/Estimator).
- Safer governance: Different roles can expose different tools. A Support cohort
  might allow diagnostics tools; a Sales cohort might allow product_search only.
- Better UX: The app can swap cohorts based on user context (e.g., “Project
  planning mode”) without code changes in the chat loop.

## Concepts at a glance

- Scenario (cohort): A named bundle of Agent definitions with a default root
  agent and optional supervisor. See `backend/app_agents/registry.py`.
- Agent: Name, instructions, model, tools, and valid handoff targets.
- Agents-as-tools: Any agent can be exposed as a callable tool to another (e.g.,
  supervisor calling summarizer). Gated by roles with a permissive default.
- Events: The SDK emits message, token, tool_call, tool_result,
  handoff_suggestion, handoff, and log. The UI shows compact tool usage in Chat
  and the full JSON in Tool Outputs.

## UI wiring

- Scenario Switcher: In the left panel, pick a scenario. The page fetches
  `/api/scenarios/:id`, regenerates the agent list, and sets the default root.
- Active Agent persistence: The active agent remains until you Apply a handoff.
  There is no heuristic switching.
- Tool Output UX: Chat shows “Used <tool> tool”; the Tool Outputs panel shows
  the full payload with actions (e.g., open Summary).
- Handoff UX: A compact badge appears inline in Chat when a handoff is
  suggested, while a dedicated "Handoff Suggestions" panel in the right column
  lists suggestions with Apply/Dismiss.
- Screenshot friendliness: Chat panel height increased to show more context in
  captures; Agent Graph panel height matches.

## Backend endpoints (SDK path)

- POST `/api/sdk/session/create` – create a session bound to a scenario and
  agent
- POST `/api/sdk/session/message` – send a user turn; emits events and tool
  outputs
- GET `/api/sdk/session/{session_id}/events` – poll events since a sequence
- POST `/api/sdk/session/set_active_agent` – Apply a handoff (manual switch)
- GET `/api/scenarios` and `/api/scenarios/:id` – scenario discovery and details

## Scenario definitions

See `backend/app_agents/registry.py`. Two examples are registered:

- default: supervisor, general, sales, support, summarizer
- project_planning: planner, estimator, general

Each `AgentDefinition` can specify `tools` and `handoff_targets`. The
supervisor’s handoff targets are constrained to valid agent names to prevent
invalid suggestions.

## Tool gating and roles

- Role-gated tools: A tool (e.g., `product_search`) can define
  `roles_allowed=["sales"]`. At runtime we enrich the per-agent session context
  with roles so the right tools appear for the right agent.
- Agents-as-tools allowlist: `AGENT_TOOL_ROLE_ALLOWLIST` in `sdk_manager.py`
  optionally restricts which session roles can call a given agent-as-tool.
  Default is permissive (enabled when there are no roles, or when `roles`
  contains the agent name or `"agents"`).

## Setup checklist

1. Define cohorts in `backend/app_agents/registry.py`:

   - Give each scenario an `id`, `label`, `default_root`, and `agents` list.
   - For each agent, set `name`, `model`, `instructions`, `tools`, and
     `handoff_targets`.

2. Tools and gating:

   - Register tools in `backend/app_agents/tools.py` with optional
     `roles_allowed` and `params_schema`.
   - Confirm `_resolve_agent_tools` in `sdk_manager.py` loads the right tools
     and applies the `roles_allowed` gate.

3. Agents-as-tools:

   - The orchestrator (supervisor or default_root) gets other agents as tools
     via `agent.as_tool(...)`.
   - Optionally set `AGENT_TOOL_ROLE_ALLOWLIST` to require certain session
     roles.

4. Frontend integration (already wired in `web/src/sdkTest.tsx`):
   - Pass `scenario_id` to create/message/tools/visualization endpoints.
   - Render tool events compactly in chat; list full details in Tool Outputs.
   - Keep active agent until Apply is clicked.

## Troubleshooting

- Tools not showing for an agent: Check `roles_allowed` and the per-agent
  context roles in `build_agent_network_for_runtime`. Sales should have roles
  that include `"sales"`.
- Handoff suggestions target invalid names: Ensure the supervisor’s handoff
  schema is constrained to valid `handoff_targets`.
- Graph visualization missing agent-tools: Verify `build_agent_network_for_viz`
  appends `agent.as_tool(...)` for the orchestrator and returns the updated root
  instance so agent-tools (e.g., Summarizer) appear for the selected root.

## Notes

- Usage aggregation is per session in memory. The Usage panel increments even
  when tokens aren’t available, so you won’t see zeros if the provider withholds
  usage.
- Realtime models are replaced automatically in the SDK path to text models
  (e.g., `gpt-4.1-mini`).
- For Windows, Graphviz detection tries common locations and `GRAPHVIZ_DOT`.

## Current Status of Implementation

### Scenario switching and discovery

- You can list scenarios and fetch one by id.
- The UI has a Scenario dropdown; switching scenarios rehydrates the agent list
  and selects the correct default root.
- The active agent persists until you explicitly Apply a handoff (no heuristic
  auto-switching).

### Agents and handoffs (LLM-native)

- Agents are defined per scenario (Default: General, Sales, Support; Project
  Planning: Planner, Estimator).
- Handoff suggestions are emitted via native Agents SDK handoffs.
- The UI shows a compact badge in Chat and a right-column Handoff Suggestions
  panel with Apply/Dismiss.
- Applying a handoff updates the active agent immediately and is recorded in
  events.

### Tools and gating

- Tools are resolved per agent with roles-based gating (e.g., product_search for
  Sales).
- A read-only Tool Catalog endpoint exists; the UI shows allowed tools for the
  active agent.
- Agents-as-tools concept is present and shown in the UI list, but GraphViz does
  not yet reliably visualize them.

### Events and Chat UX

- Optimistic user message rendering with reconciliation avoids the “first
  message disappears” bug.
- Tool calls/results are visible in Chat (compact) and in a dedicated Tool
  Outputs panel (structured details).
- A Context panel shows the session context; the Usage panel tracks
  requests/tokens.
- Chat and Graph panels are taller for easier screenshots.

### Visualization (GraphViz)

- Agent graph and handoff edges render reliably.
- Agents-as-tools are not consistently visualized (not always mirrored at the
  selected root). We paused backend changes that previously caused regressions.

### Stability

- Session creation flow is working after reverting risky backend edits.
- We’ve kept the backend surface stable while improving the frontend UX and tool
  visibility.

---

Questions or improvements? Consider adding more cohorts (e.g., billing,
onboarding) and tailor `roles_allowed` accordingly.# Outline of architecture for
a context aware mounting of agent cohorts with relevant tools (dynamic)

Scenarios vs Agent Groups — recommended path Goal: Align with the official
OpenAI Agents SDK and prepare for your main app by making the runtime mount the
right “cohort” of agents and tools based on app context and user role.

Short version:

Keep “scenarios” as a compatibility layer. Introduce “agent groups” as the
first-class concept and route all runtime building through it. Immediately
leverage context to mount the correct group and dynamically equip agents (tools
and agents‑as‑tools) instead of hard-coding lists. Suggested sequencing:

Introduce AgentGroupDefinition alongside ScenarioDefinition (compat)

Add a new AgentGroupDefinition type with id, label, description, default_root,
agents. Registry exposes agent_groups; scenarios becomes an alias/shim. Keep
scenario_id params in endpoints; internally map to agent_group_id for now.
Context-driven mounting and dynamic equipping

On session create, derive agent_group_id from app context (page location,
projectId, orgId) and user role (admin, project member). Persist app_location,
project_id, org_id, roles in session context. Gate tools and agents-as-tools
with is_enabled(ctx). Mount the correct group automatically. Catalog expansion
and discovery

Extend /api/tools/catalog with metadata (tags, roles_required, cost hints) and
group classification. Optional: add GET /api/tools/search?query= and an LLM
discovery tool (behind a feature flag). Gradual UI migration

Update labels to “Agent Group” in UI first; keep scenario_id API. Later add a
group switcher (if needed) to preview configurations per location. Finalize
migration

Deprecate “scenarios” naming after FE is migrated; keep shim for a release. Why
this order?

You get immediate value (agents-as-tools, dynamic equipping, better catalog)
without breaking current flows. Terminology migrates safely and aligns with the
Agents SDK’s mental model. Prepares for main app export where mounting the right
cohort per route/user is essential. Mapping to your main app use cases Project
page (pages/projects/[projectId]):

Agent group: “Project Management” Orchestrator: Project Manager Tools: CRUD
project/task/member, attachments, external work ingestion Agents-as-tools: Task
Creator, Assignment Planner, External Researcher Context: project_id, roles =>
gates tools and which agents-as-tools are available Projects overview
(pages/projects/):

Agent group: “Strategic Planning” Orchestrator: Planner/Creator Tools: Create
project, plan scaffolding, org-scoped CRUD Agents-as-tools: Requirements
Analyzer, Estimator, Proposal Generator My dashboard / My account (org tab):

Agent group: “Org Intelligence” Orchestrator: Research Coordinator Tools: Org
CRUD, web search, content summarization, report generation Agents-as-tools:
Market Researcher, Data Summarizer Content engagement:

Agent group: “Content Companion” Orchestrator: Discussion Partner Tools:
Retrieval, enrichment, apply-to-project/org Agents-as-tools: Contextual
Summarizer, Citation Finder Assessments (phase 2 voice-first upgrade later):

Agent group: “Assessment Assistant” Orchestrator: Form Runner Tools: Form schema
loader, answer generator, section context manager Agents-as-tools: Answer
Refiner, Section Coach UX: Chat-first; agent fills form; user reviews/approves
Admin users:

Agent group: “Admin-Content” Orchestrator: Content Editor Coordinator Tools:
Content editor integration (tiptap), JSON-schema tool builder, assessment
builder Agents-as-tools: Content Rewriter, Tool Factory, Assessment Designer
Strict is_enabled(ctx) gating by admin role Each group is mounted based on app
context and role. The orchestrator receives specialized agents as tools; tools
and agents-as-tools use is_enabled to respect roles and scope.
