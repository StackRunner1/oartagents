from __future__ import annotations

from typing import Dict, List

from .schemas import AgentDefinition, ScenarioDefinition

# Minimal starter scenarios mirroring current FE placeholders.

_default_agents: List[AgentDefinition] = [
    AgentDefinition(
        name="supervisor",
        role="supervisor",
        model="gpt-4.1-mini",
        instructions=(
            "You are a routing supervisor. Read the user's last message and choose the best specialist."
            " Prefer Sales for product discovery and recommendations; Support for troubleshooting; General otherwise."
            " Only switch agents when you have high confidence it benefits the user; avoid flip-flopping."
            " When suggesting a handoff, include a short reason (3-8 words)."
        ),
        voice=None,
        tools=[],
        handoff_targets=["general", "sales", "support"],
    ),
    AgentDefinition(
        name="general",
        model="gpt-4.1-mini",  # use a text-capable model for SDK runs; realtime model is for Realtime API only
        instructions=(
            "General purpose assistant. If the user explicitly asks to speak to Sales or Support, call the handoff tool to that agent immediately and provide a short reason."
        ),
        voice="alloy",
        tools=["echo_context", "weather", "WebSearchTool"],
        handoff_targets=["sales", "support"],
    ),
    AgentDefinition(
        name="sales",
        model="gpt-4.1-mini",
        instructions=(
            "You are a sales assistant. Ask concise clarifying questions; recommend items from the catalog using product_search."
        ),
        voice=None,
        tools=["product_search"],
        handoff_targets=["support", "general"],
    ),
    AgentDefinition(
        name="support",
        model="gpt-4.1-mini",
        instructions=(
            "You are a support assistant. Diagnose issues methodically; request minimal repro info; keep steps numbered."
        ),
        voice=None,
        tools=["echo_context"],
        handoff_targets=["sales", "general"],
    ),
    AgentDefinition(
        name="summarizer",
        model="gpt-4.1-mini",
        instructions=(
            "You are a concise text summarizer. Given user content or context, return a brief, factual summary with key points."
        ),
        voice=None,
        tools=[],
        handoff_targets=["general"],
    ),
]

scenarios: Dict[str, ScenarioDefinition] = {
    "default": ScenarioDefinition(
        id="default",
        label="Default",
        default_root="general",
        agents=_default_agents,
        description="Supervisor + General/Sales/Support agents",
    ),
    "project_planning": ScenarioDefinition(
        id="project_planning",
        label="Project Planning",
        default_root="planner",
        agents=[
            AgentDefinition(
                name="planner",
                model="gpt-4.1-mini",
                instructions=(
                    "You are a project planning assistant. Break down tasks, identify dependencies, and suggest timelines."
                ),
                voice=None,
                tools=["echo_context"],
                handoff_targets=["estimator", "general"],
            ),
            AgentDefinition(
                name="estimator",
                model="gpt-4.1-mini",
                instructions=(
                    "You are a work effort estimator. Provide rough order-of-magnitude estimates and assumptions."
                ),
                voice=None,
                tools=["echo_context"],
                handoff_targets=["planner", "general"],
            ),
            AgentDefinition(
                name="general",
                model="gpt-4.1-mini",
                instructions=(
                    "General helper for planning context. If the user requests planner or estimator explicitly, call handoff accordingly."
                ),
                voice=None,
                tools=["echo_context"],
                handoff_targets=["planner", "estimator"],
            ),
        ],
        description="Planner/Estimator + General",
    ),
}


def list_scenarios():
    return [s for s in scenarios.values()]


def get_scenario(sid: str) -> ScenarioDefinition | None:
    return scenarios.get(sid)
