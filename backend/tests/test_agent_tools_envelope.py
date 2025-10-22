import asyncio
from types import SimpleNamespace

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
        self.tools = tools or []
        self.handoffs = handoffs or []
        self.model_settings = model_settings


class DummyRunner:
    @staticmethod
    async def run(agent, user_input, session=None, context=None):  # noqa: ARG002
        return SimpleNamespace(
            final_output="done",
            new_items=[
                SimpleNamespace(
                    tool_name="summarizer_agent_tool",
                    args={"text": "Hello world\n- a\n- b"},
                    tool_output={"summary": "Hello world", "bullets": ["a", "b"]},
                )
            ],
        )


@pytest.mark.asyncio
async def test_summarizer_agent_tool_emits_envelope(monkeypatch: pytest.MonkeyPatch):
    # Ensure clean session
    sid = "test-sess-1"
    store.delete_session(sid)
    store.create_session(sid, active_agent_id="general", scenario_id="default")

    # Monkeypatch SDK surfaces
    monkeypatch.setattr(sdk_manager, "Agent", DummyAgent, raising=True)
    monkeypatch.setattr(sdk_manager, "Runner", DummyRunner, raising=True)

    # Run a turn that produces a summarizer agent-tool result
    result = await sdk_manager.run_agent_turn(
        session_id=sid,
        user_input="summarize this",
        agent_spec={"name": "general", "instructions": "test", "model": "gpt-4.1-mini"},
        scenario_id=None,
    )

    assert isinstance(result, dict)
    # Gather events and locate tool_call and tool_result
    evs = store.list_events(sid)
    tool_calls = [e for e in evs if e.type == "tool_call"]
    tool_results = [e for e in evs if e.type == "tool_result"]
    assert len(tool_calls) == 1, [e.model_dump() for e in evs]
    assert len(tool_results) == 1

    tc = tool_calls[0].model_dump()
    assert tc["data"]["tool_name"] == "summarizer_agent_tool"
    assert tc["data"]["args"] == {"text": "Hello world\n- a\n- b"}

    tr = tool_results[0].model_dump()
    assert tr["tool_name"] == "summarizer_agent_tool"
    # Envelope should be present and include args and summary
    env = tr["data"].get("envelope")
    assert env and env.get("name") == "summarizer_agent_tool"
    assert env.get("ok") is True
    assert env.get("args") == {"text": "Hello world\n- a\n- b"}
    assert "data" in env and isinstance(env["data"], dict)
    assert "summary" in env["data"]
    # Recommended prompts default should be present for summarizer
    rec = env.get("recommended_prompts")
    assert isinstance(rec, list) and len(rec) > 0


class DummyRunnerNonSumm:
    @staticmethod
    async def run(agent, user_input, session=None, context=None):  # noqa: ARG002
        return SimpleNamespace(
            final_output="done",
            new_items=[
                SimpleNamespace(
                    tool_name="support_agent_tool",
                    args={"question": "why?"},
                    tool_output="OK",
                )
            ],
        )


@pytest.mark.asyncio
async def test_non_summarizer_agent_tool_envelope_output(
    monkeypatch: pytest.MonkeyPatch,
):
    sid = "test-sess-2"
    store.delete_session(sid)
    store.create_session(sid, active_agent_id="general", scenario_id="default")

    monkeypatch.setattr(sdk_manager, "Agent", DummyAgent, raising=True)
    monkeypatch.setattr(sdk_manager, "Runner", DummyRunnerNonSumm, raising=True)

    result = await sdk_manager.run_agent_turn(
        session_id=sid,
        user_input="delegate",
        agent_spec={"name": "general", "instructions": "test", "model": "gpt-4.1-mini"},
        scenario_id=None,
    )

    assert isinstance(result, dict)
    evs = store.list_events(sid)
    tool_results = [e for e in evs if e.type == "tool_result"]
    assert len(tool_results) == 1
    tr = tool_results[0].model_dump()
    env = tr["data"].get("envelope")
    assert env and env.get("name") == "support_agent_tool"
    assert env.get("ok") is True
    assert env.get("args") == {"question": "why?"}
    assert env.get("data", {}).get("output") == "OK"
