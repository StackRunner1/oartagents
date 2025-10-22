import sys
from types import ModuleType, SimpleNamespace

import pytest

from app_agents import sdk_manager
from app_agents.core.store.memory_store import store


class DummyAgent:
    def __init__(
        self,
        name: str,
        instructions: str,
        model: str,
        tools=None,
        handoffs=None,
        model_settings=None,
    ):
        self.name = name
        self.instructions = instructions
        self.model = model
        self.tools = list(tools or [])
        self.handoffs = list(handoffs or [])
        self.model_settings = model_settings

    def as_tool(
        self, tool_name: str, tool_description: str, is_enabled
    ):  # noqa: D401, ARG002
        # Return a simple tool object carrying name and is_enabled callback
        return SimpleNamespace(
            name=tool_name, is_enabled=is_enabled, description=tool_description
        )


def _install_fake_agents_module(monkeypatch: pytest.MonkeyPatch):
    # Create a fake 'agents' module surface required by build_agent_network_for_runtime
    fake_agents = ModuleType("agents")

    def handoff(agent, on_handoff=None):  # noqa: ARG001
        # Represent a handoff wrapper; unused in assertions
        return SimpleNamespace(target=agent, on_handoff=on_handoff)

    # Minimal extensions.handoff_prompt submodule
    ext_mod = ModuleType("agents.extensions")
    hp_mod = ModuleType("agents.extensions.handoff_prompt")

    def prompt_with_handoff_instructions(text: str) -> str:
        return text

    hp_mod.prompt_with_handoff_instructions = prompt_with_handoff_instructions  # type: ignore[attr-defined]
    ext_mod.handoff_prompt = hp_mod  # type: ignore[attr-defined]

    fake_agents.handoff = handoff  # type: ignore[attr-defined]
    # Also provide placeholders for types used elsewhere if imported
    sys.modules["agents"] = fake_agents
    sys.modules["agents.extensions"] = ext_mod
    sys.modules["agents.extensions.handoff_prompt"] = hp_mod

    # Patch sdk_manager globals to use our DummyAgent/ModelSettings
    monkeypatch.setattr(sdk_manager, "Agent", DummyAgent, raising=True)

    class DummyModelSettings:
        def __init__(self, include_usage: bool = True):  # noqa: ARG002
            self.include_usage = include_usage

    monkeypatch.setattr(sdk_manager, "ModelSettings", DummyModelSettings, raising=True)


def test_summarizer_agent_tool_role_gating(monkeypatch: pytest.MonkeyPatch):
    _install_fake_agents_module(monkeypatch)

    sid = "gating-sess-1"
    store.delete_session(sid)
    store.create_session(sid, active_agent_id="general", scenario_id="default")

    # Set session context with an unrelated role -> should DISABLE summarizer agent-tool
    store.set_context(sid, {"roles": ["unrelated"]})
    network = sdk_manager.build_agent_network_for_runtime("default", session_id=sid)
    assert isinstance(network, dict) and network
    # Orchestrator is supervisor in default scenario
    orch = network.get("supervisor")
    assert orch is not None
    tools = getattr(orch, "tools", [])
    # Find summarizer agent-tool and probe is_enabled
    s_tool = next(
        (t for t in tools if getattr(t, "name", "") == "summarizer_agent_tool"), None
    )
    assert s_tool is not None
    assert callable(getattr(s_tool, "is_enabled", None))
    # With no allowed roles -> expect False
    assert s_tool.is_enabled({"roles": ["unrelated"]}) is False

    # Now set roles that intersect allowlist (e.g., 'agents' or 'support' or 'general') -> expect True
    assert s_tool.is_enabled({"roles": ["agents"]}) is True
    assert s_tool.is_enabled({"roles": ["support"]}) is True
    assert s_tool.is_enabled({"roles": ["general"]}) is True
