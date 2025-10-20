# Plan at a glance

- Harden tool registration and output conventions for reliable tool_name.
- Guarantee tool name propagation in backend events with robust fallbacks.
- Enrich the demo tools via JSON “mock data” and richer utilities (search, CRUD,
  PM-like tools).
- Add small FE affordances (show args, clickable recommended prompts).
- Add tests and update docs.

## Task checklist (implement in order)

### Phase 1 — Tool registry hardening (tools.py + registration)

- [ ] Replace schema inference with explicit schemas for ctx-aware tools
  - [ ] Exclude ctx from JSON schemas; keep ctx in function signature for context.
  - [ ] Acceptance: Every registry tool has an explicit parameters schema (no inference).
- [ ] Enforce a standard output envelope across all tools

  - [ ] Shape: { ok: boolean, name: string, args: object, data: object, meta?: object, recommended_prompts?: string[] }
  - [ ] Acceptance: All tools return this envelope; unit test validates keys.

- [ ] Canonical names and descriptions

  - [ ] Ensure ToolSpec.name (snake_case) is passed to function_tool as name=...
  - [ ] Ensure description is action-oriented (helps model choose the tool).
  - [ ] Acceptance: Catalog endpoint lists name/description and matches function_tool name.

- [ ] Roles gating alignment

  - [ ] Keep roles_allowed in ToolSpec authoritative and consistent with runtime gating.
  - [ ] Acceptance: Sales-only tools never appear for Support in the allowlist endpoint.

- [ ] Recommended prompts support
  - [ ] When appropriate (e.g., search tools), include recommended_prompts in output envelope.
  - [ ] Acceptance: FE suggestions render when present.

### Phase 2 — Backend event shaping and name propagation (sdk_manager)

- [ ] Tool call events always include a tool_name

  - [ ] Prefer SDK-extracted name; fallback to ToolSpec.name; finally fallback to envelope.name.
  - [ ] Acceptance: tool_call has top-level `tool_name` and `data.tool_name` set.

- [ ] Tool result events always include a tool_name

  - [ ] Same fallback order; guarantee `data.tool_name` mirrors top-level.
  - [ ] Acceptance: tool_result has `tool_name` set; FE shows name instead of “(unknown tool)”.

- [ ] Tests for tool labelling
  - [ ] Add unit/integration tests asserting tool_call/tool_result contain `tool_name` and match the called tool.
  - [ ] Acceptance: Tests pass; FE shows names in Chat + Tool Outputs.

### Phase 3 — Broaden demo tool surface (mock-only, no external systems)

- [ ] Introduce mock data files

  - [ ] `data/catalog.json` (products with categories, price, tags, stock)
  - [ ] `data/orders.json` (orders with id, items, status)
  - [ ] `data/tickets.json` (support tickets with status, tags)
  - [ ] `data/projects.json` (projects, tasks, owners, statuses)
  - [ ] Acceptance: Files load at startup; lightweight in-memory indexes
        created.

- [ ] Add richer demo tools (all return standard envelope)

  - [ ] `catalog_search(query, filters?, sort?, page?, page_size?)`
  - [ ] `catalog_facets(field: 'category' | 'brand' | 'tags')`
  - [ ] `order_lookup(order_id)`
  - [ ] `order_create(items[], customer_info)` // mock “write” in memory
  - [ ] `ticket_search(query, status?, tags?)`
  - [ ] `ticket_update(ticket_id, status?, note?)`
  - [ ] `project_task_list(project_id, status?, assignee?)`
  - [ ] `project_task_create(project_id, title, assignee?, due?)`
  - [ ] `summarizer_agent_tool` (kept as-is, returns envelope)
  - Optional advanced:
    - [ ] `generic_query(table, where?, select?, sort?, limit?)`: a constrained DSL over JSON
  - [ ] Acceptance: Each tool passes schema validation, returns an envelope, and
        is role-gated sensibly (e.g., order tools for “sales”, tickets for
        “support”, PM tools for “planner/estimator”).

- [ ] Tool catalog endpoint + metadata
  - [ ] Enrich catalog with tags, roles_required, example_args.
  - [ ] Acceptance: FE can render a discoverable list, proving governance and discoverability.

### Phase 4 — Frontend improvements (small and targeted)

- [ ] Tool name reliability in UI

  - [ ] Ensure FE reads name from `ev.tool_name`, `ev.data.tool_name`,
        `ev.data.name` (already implemented).
  - [ ] Acceptance: Tool Output card and in-chat “Used [tool]” show correct name in demos.

- [ ] Display executed args and recommended prompts
  - [ ] Show the args payload (compact) with disclosure.
  - [ ] Render recommended prompts as chips; click inserts into input.
  - [ ] Acceptance: Chips insert text into the input; args shown under “Show
        details.”

### Phase 5 — Telemetry and usage

- [ ] Tool usage counts per session
  - [ ] Increment counts when tool_call emitted; display in Usage panel summary (e.g., “Tools called: 3”).
  - [ ] Acceptance: Usage panel shows a nonzero tools counter after calls.

### Phase 6 — Docs and guides

- [ ] Update `target_handoff_plan.md`

  - [ ] Mark items complete (auto-apply, summarizer fallback, routing via FE
        context, UI placement) and add the new tool registry tasks.
  - [ ] Acceptance: Doc reflects current status and next steps.

- [ ] Update `contextual_agent_cohorts.md`

  - [ ] Add “mock data + richer tools” section, describe role gating and cohorts.
  - [ ] Acceptance: Doc includes datasets + tools mapping and role gates.

- [ ] New: `tool_registry_improvements.md` (this plan distilled)
  - [ ] Best practices, envelope spec, schema examples, test matrix.
  - [ ] Acceptance: Added and linked.

## Ideas to broaden demo tool coverage (while staying mock-only)

### 1) JSON as “tables” + lightweight indices => APPROVED

- Backend folder: `backend/data/`
  - `catalog.json`: id, name, category, brand, price, tags, stock, rating
  - `orders.json`: order_id, customer, items[], total, status, created_at
  - `tickets.json`: ticket_id, subject, body, tags, status, assignee
  - `projects.json`: project_id, title, tasks[], status, owner, due_dates
- Startup: load files, build simple in-memory indices for fast filter/sort.
- Benefits: realistic tool behavior and event shapes without external systems.

### 2) Flexible search and listing tools (targets) => TBD

- `catalog_search`: free-text + filters (category, tags, price_range) + sort + paging.
- `ticket_search`: free-text in subject/body; filter by status/tags/assignee.
- `project_task_list`: filter by project/status/assignee; sort by due date.

### 3) Constrained query DSL tool (optional) => TBD

- `generic_query(table, where?, select?, sort?, limit?)` — read-only, safe.
- where supports AND of simple comparisons (=, <, >, IN, CONTAINS); no eval/code.
- Showcases smarter tool chaining (e.g., summarize results after filtering).

### 4) "Transaction-like" mock writes => APPROVED

- `order_create`, `ticket_update`, `project_task_create` modify in-memory store
  and append to a journal.
- Return the new/updated record and a suggested next action.

### 5) Tool-level recommended prompts => let's discuss. should recommended prompts not be done by the agent who hands off?

- Each tool returns `recommended_prompts` tailored to next steps:
  - catalog_search: “Filter by category Accessories”, “Sort by price ascending”.
  - order_lookup: “Create a return”, “Update shipping address”.
  - ticket_search: “Assign to SupportAgent1”, “Escalate to Tier 2”.

### 6) Agents-as-tools patterns => APPROVED

- Summarizer and Estimator as tools in cohorts; return structured outputs
  (summary, bullets, assumptions).

### Acceptance criteria (condensed)

- Tool events: every `tool_call` and `tool_result` has `tool_name` at top-level
  and in data.
- Output envelope: all tools return
  `{ ok, name, args, data, meta?, recommended_prompts? }`.
- Demo tools: catalog, tickets, orders, and PM tasks tools function against JSON
  datasets.
- FE: tool names show reliably; args and recommended prompts visible; prompts
  insertable.
- Tests: assertions for tool_name presence, envelope validity, and basic tool
  flows.
