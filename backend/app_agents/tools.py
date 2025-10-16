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


class ToolSpec(BaseModel):
    name: str
    description: str = ""
    func: Callable[..., Any]
    params_schema: Dict[str, Any] = Field(default_factory=dict)
    # Prefer SDK to infer schema from signature (needed for ctx-aware tools)
    infer_schema: bool = True
    # Optional roles gating (if non-empty, only sessions with one of these roles see the tool)
    roles_allowed: List[str] = Field(default_factory=list)


tool_registry: Dict[str, ToolSpec] = {}


def _echo_context(ctx: RunContextWrapper[Any], text: str = ""):
    """Simple tool: echoes a provided text for debugging / grounding."""
    # Example of reading session context fields
    meta = getattr(ctx, "context", {}) if ctx else {}
    return {"echo": {"text": text, "ctx_keys": sorted(list(meta.keys()))}}


def _weather(ctx: RunContextWrapper[Any], city: str) -> Dict[str, Any]:
    """Return simple faux weather for a city (demo)."""
    return {"city": city, "forecast": "sunny", "temp_c": 23}


def _product_search(
    ctx: RunContextWrapper[Any], query: str, limit: int = 3
) -> Dict[str, Any]:
    """Search a pretend catalog (demo)."""
    items = [
        {"id": "sku-1", "name": "Widget Pro", "price": 49.99},
        {"id": "sku-2", "name": "Widget Mini", "price": 19.99},
        {"id": "sku-3", "name": "Widget Max", "price": 89.99},
    ]
    return {"query": query, "results": items[: max(1, min(limit, len(items)))]}


# Register initial tools
tool_registry["echo_context"] = ToolSpec(
    name="echo_context",
    description="Echo input args for debugging/grounding",
    func=_echo_context,
    params_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    infer_schema=True,
)
tool_registry["weather"] = ToolSpec(
    name="weather",
    description="Return a demo weather forecast for a city",
    func=_weather,
    params_schema={
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
    infer_schema=True,
    roles_allowed=["support", "assistant"],
)
tool_registry["product_search"] = ToolSpec(
    name="product_search",
    description="Search a demo product catalog",
    func=_product_search,
    params_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        "required": ["query"],
    },
    infer_schema=True,
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
