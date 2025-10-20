from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

try:
    # Context wrapper from Agents SDK for ctx-aware tools
    from agents import RunContextWrapper  # type: ignore
except Exception:  # pragma: no cover - fallback typing if SDK unavailable

    class RunContextWrapper(BaseModel):  # type: ignore
        context: Dict[str, Any] = {}


# Placeholder tool registry. In future, implement real functions (DB lookups, etc.).


class ToolEnvelope(BaseModel):
    """Standard envelope for tool outputs to ensure reliable event shaping.

    Fields:
    - ok: success indicator
    - name: canonical tool name
    - args: the arguments used for execution
    - data: primary tool data payload (dict/list/primitive)
    - meta: optional metadata (timings, source, etc.)
    - recommended_prompts: optional list of next-step suggestions
    """

    ok: bool = True
    name: str
    args: Dict[str, Any] | None = None
    data: Any | None = None
    meta: Dict[str, Any] | None = None
    recommended_prompts: List[str] | None = None


def wrap_envelope(name: str, args: Dict[str, Any] | None, data: Any, **kw) -> Dict[str, Any]:
    """Create a ToolEnvelope as a plain dict to avoid coupling callers to pydantic types."""
    env = ToolEnvelope(name=name, args=args or {}, data=data, **kw)
    return env.model_dump()


class ToolSpec(BaseModel):
    name: str
    description: str = ""
    func: Callable[..., Any]
    params_schema: Dict[str, Any] = Field(default_factory=dict)
    # Prefer explicit schema; set to False to avoid inferring ctx parameter
    infer_schema: bool = False
    # Optional roles gating (if non-empty, only sessions with one of these roles see the tool)
    roles_allowed: List[str] = Field(default_factory=list)


tool_registry: Dict[str, ToolSpec] = {}


def _echo_context(ctx: RunContextWrapper[Any], text: str = ""):
    """Simple tool: echoes a provided text for debugging / grounding."""
    meta = getattr(ctx, "context", {}) if ctx else {}
    data = {"text": text, "ctx_keys": sorted(list(meta.keys()))}
    return wrap_envelope(
        name="echo_context",
        args={"text": text},
        data=data,
        recommended_prompts=[
            "Show my session context keys",
            "Echo back the last user message",
        ],
    )


def _weather(ctx: RunContextWrapper[Any], city: str) -> Dict[str, Any]:
    """Return simple faux weather for a city (demo)."""
    data = {"city": city, "forecast": "sunny", "temp_c": 23}
    return wrap_envelope(
        name="weather",
        args={"city": city},
        data=data,
        recommended_prompts=[f"Do you want a 5-day forecast for {city}?"],
    )


def _product_search(
    ctx: RunContextWrapper[Any], query: str, limit: int = 3
) -> Dict[str, Any]:
    """Search a pretend catalog (demo)."""
    items = [
        {"id": "sku-1", "name": "Widget Pro", "price": 49.99},
        {"id": "sku-2", "name": "Widget Mini", "price": 19.99},
        {"id": "sku-3", "name": "Widget Max", "price": 89.99},
    ]
    results = items[: max(1, min(limit, len(items)))]
    return wrap_envelope(
        name="product_search",
        args={"query": query, "limit": limit},
        data={"query": query, "results": results},
        recommended_prompts=[
            "Filter results by price under $50",
            "Show only accessories",
        ],
    )


# Register initial tools
tool_registry["echo_context"] = ToolSpec(
    name="echo_context",
    description="Echo input args for debugging/grounding",
    func=_echo_context,
    params_schema={
        "type": "object",
        "properties": {"text": {"type": "string", "description": "Text to echo back"}},
        "required": [],
        "additionalProperties": False,
    },
    infer_schema=False,
)
tool_registry["weather"] = ToolSpec(
    name="weather",
    description="Return a demo weather forecast for a city",
    func=_weather,
    params_schema={
        "type": "object",
        "properties": {"city": {"type": "string", "description": "City name"}},
        "required": ["city"],
        "additionalProperties": False,
    },
    infer_schema=False,
    roles_allowed=["support", "assistant"],
)
tool_registry["product_search"] = ToolSpec(
    name="product_search",
    description="Search a demo product catalog",
    func=_product_search,
    params_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 3},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    infer_schema=False,
    roles_allowed=["sales"],
)


async def execute_tool(name: str, **kwargs) -> Any:
    spec = tool_registry.get(name)
    if not spec:
        raise ValueError(f"Unknown tool: {name}")
    func = spec.func
    if callable(func):
        result = func(**kwargs)
        if hasattr(result, "__await__"):
            return await result  # async
        return result
    return func
