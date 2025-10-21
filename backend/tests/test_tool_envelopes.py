import pytest

from app_agents.tools import tool_registry, wrap_envelope


def test_tool_registry_has_explicit_schemas():
    # Ensure all registered tools specify explicit schemas and do not infer
    for name, spec in tool_registry.items():
        assert spec.params_schema, f"{name} missing params_schema"
        assert spec.infer_schema is False, f"{name} should have infer_schema=False"


def test_wrap_envelope_shape():
    data = {"k": 1}
    env = wrap_envelope("demo_tool", {"a": 1}, data)
    assert isinstance(env, dict)
    for key in ("ok", "name", "args", "data"):
        assert key in env, f"missing {key}"
    assert env["ok"] is True
    assert env["name"] == "demo_tool"
    assert env["args"] == {"a": 1}
    assert env["data"] == data


def test_registered_tools_return_envelopes():
    # Call a few demo tools with minimal args and assert envelope shape
    # echo_context
    env1 = tool_registry["echo_context"].func(ctx=None, text="hi")
    for key in ("ok", "name", "args", "data"):
        assert key in env1
    assert env1["name"] == "echo_context"

    # weather
    env2 = tool_registry["weather"].func(ctx=None, city="Paris")
    for key in ("ok", "name", "args", "data"):
        assert key in env2
    assert env2["name"] == "weather"
    assert env2["data"]["city"] == "Paris"

    # product_search
    env3 = tool_registry["product_search"].func(ctx=None, query="widget", limit=2)
    for key in ("ok", "name", "args", "data"):
        assert key in env3
    assert env3["name"] == "product_search"
    assert isinstance(env3["data"].get("results"), list)
