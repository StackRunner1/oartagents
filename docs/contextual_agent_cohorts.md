# Outline of architecture for a context aware mounting of agent cohorts with relevant tools (dynamic)

Scenarios vs Agent Groups — recommended path
Goal: Align with the official OpenAI Agents SDK and prepare for your main app by making the runtime mount the right “cohort” of agents and tools based on app context and user role.

Short version:

Keep “scenarios” as a compatibility layer.
Introduce “agent groups” as the first-class concept and route all runtime building through it.
Immediately leverage context to mount the correct group and dynamically equip agents (tools and agents‑as‑tools) instead of hard-coding lists.
Suggested sequencing:

Introduce AgentGroupDefinition alongside ScenarioDefinition (compat)

Add a new AgentGroupDefinition type with id, label, description, default_root, agents.
Registry exposes agent_groups; scenarios becomes an alias/shim.
Keep scenario_id params in endpoints; internally map to agent_group_id for now.
Context-driven mounting and dynamic equipping

On session create, derive agent_group_id from app context (page location, projectId, orgId) and user role (admin, project member).
Persist app_location, project_id, org_id, roles in session context.
Gate tools and agents-as-tools with is_enabled(ctx). Mount the correct group automatically.
Catalog expansion and discovery

Extend /api/tools/catalog with metadata (tags, roles_required, cost hints) and group classification.
Optional: add GET /api/tools/search?query= and an LLM discovery tool (behind a feature flag).
Gradual UI migration

Update labels to “Agent Group” in UI first; keep scenario_id API.
Later add a group switcher (if needed) to preview configurations per location.
Finalize migration

Deprecate “scenarios” naming after FE is migrated; keep shim for a release.
Why this order?

You get immediate value (agents-as-tools, dynamic equipping, better catalog) without breaking current flows.
Terminology migrates safely and aligns with the Agents SDK’s mental model.
Prepares for main app export where mounting the right cohort per route/user is essential.
Mapping to your main app use cases
Project page (pages/projects/[projectId]):

Agent group: “Project Management”
Orchestrator: Project Manager
Tools: CRUD project/task/member, attachments, external work ingestion
Agents-as-tools: Task Creator, Assignment Planner, External Researcher
Context: project_id, roles => gates tools and which agents-as-tools are available
Projects overview (pages/projects/):

Agent group: “Strategic Planning”
Orchestrator: Planner/Creator
Tools: Create project, plan scaffolding, org-scoped CRUD
Agents-as-tools: Requirements Analyzer, Estimator, Proposal Generator
My dashboard / My account (org tab):

Agent group: “Org Intelligence”
Orchestrator: Research Coordinator
Tools: Org CRUD, web search, content summarization, report generation
Agents-as-tools: Market Researcher, Data Summarizer
Content engagement:

Agent group: “Content Companion”
Orchestrator: Discussion Partner
Tools: Retrieval, enrichment, apply-to-project/org
Agents-as-tools: Contextual Summarizer, Citation Finder
Assessments (phase 2 voice-first upgrade later):

Agent group: “Assessment Assistant”
Orchestrator: Form Runner
Tools: Form schema loader, answer generator, section context manager
Agents-as-tools: Answer Refiner, Section Coach
UX: Chat-first; agent fills form; user reviews/approves
Admin users:

Agent group: “Admin-Content”
Orchestrator: Content Editor Coordinator
Tools: Content editor integration (tiptap), JSON-schema tool builder, assessment builder
Agents-as-tools: Content Rewriter, Tool Factory, Assessment Designer
Strict is_enabled(ctx) gating by admin role
Each group is mounted based on app context and role. The orchestrator receives specialized agents as tools; tools and agents-as-tools use is_enabled to respect roles and scope.