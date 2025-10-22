from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from . import mock_data

logger = logging.getLogger(__name__)

try:
    from supabase import create_client  # type: ignore
except Exception:  # pragma: no cover
    create_client = None  # type: ignore

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


def wrap_envelope(
    name: str, args: Dict[str, Any] | None, data: Any, **kw
) -> Dict[str, Any]:
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


# -----------------------
# Approved demo tools
# -----------------------


def _order_lookup(ctx: RunContextWrapper[Any], order_id: str) -> Dict[str, Any]:
    order = mock_data.find_order(order_id)
    data = order or {"message": f"No order found for id {order_id}"}
    rec = ["Create a return", "Update shipping address"] if order else []
    return wrap_envelope(
        name="order_lookup",
        args={"order_id": order_id},
        data=data,
        recommended_prompts=rec,
    )


def _order_create(
    ctx: RunContextWrapper[Any],
    items: List[Dict[str, Any]],
    customer_info: Dict[str, Any],
) -> Dict[str, Any]:
    order = mock_data.create_order(items, customer_info)
    return wrap_envelope(
        name="order_create",
        args={"items": items, "customer_info": customer_info},
        data=order,
        recommended_prompts=["Send order confirmation", "Add shipping details"],
    )


def _ticket_update(
    ctx: RunContextWrapper[Any],
    ticket_id: str,
    status: Optional[str] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    ticket = mock_data.update_ticket(ticket_id, status=status, note=note)
    data = ticket or {"message": f"No ticket found for id {ticket_id}"}
    return wrap_envelope(
        name="ticket_update",
        args={"ticket_id": ticket_id, "status": status, "note": note},
        data=data,
        recommended_prompts=["Escalate ticket", "Assign to Tier 2"],
    )


def _project_task_create(
    ctx: RunContextWrapper[Any],
    project_id: str,
    title: str,
    assignee: Optional[str] = None,
    due: Optional[str] = None,
) -> Dict[str, Any]:
    task = mock_data.create_project_task(project_id, title, assignee=assignee, due=due)
    data = task or {"message": f"No project found for id {project_id}"}
    return wrap_envelope(
        name="project_task_create",
        args={
            "project_id": project_id,
            "title": title,
            "assignee": assignee,
            "due": due,
        },
        data=data,
        recommended_prompts=["List project tasks", "Assign a teammate"],
    )


# Register approved tools with explicit schemas and role gating
tool_registry["order_lookup"] = ToolSpec(
    name="order_lookup",
    description="Look up an order by order_id",
    func=_order_lookup,
    params_schema={
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Order identifier"}
        },
        "required": ["order_id"],
        "additionalProperties": False,
    },
    infer_schema=False,
    roles_allowed=["sales"],
)

tool_registry["order_create"] = ToolSpec(
    name="order_create",
    description="Create an order in the mock store",
    func=_order_create,
    params_schema={
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "qty": {"type": "integer", "minimum": 1},
                        "price": {"type": "number"},
                    },
                    "required": ["id", "qty"],
                    "additionalProperties": False,
                },
            },
            "customer_info": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "email": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": True,
            },
        },
        "required": ["items", "customer_info"],
        "additionalProperties": False,
    },
    infer_schema=False,
    roles_allowed=["sales"],
)

tool_registry["ticket_update"] = ToolSpec(
    name="ticket_update",
    description="Update a support ticket's status or add a note",
    func=_ticket_update,
    params_schema={
        "type": "object",
        "properties": {
            "ticket_id": {"type": "string"},
            "status": {"type": "string"},
            "note": {"type": "string"},
        },
        "required": ["ticket_id"],
        "additionalProperties": False,
    },
    infer_schema=False,
    roles_allowed=["support"],
)

tool_registry["project_task_create"] = ToolSpec(
    name="project_task_create",
    description="Create a task in a project",
    func=_project_task_create,
    params_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "title": {"type": "string"},
            "assignee": {"type": "string"},
            "due": {"type": "string"},
        },
        "required": ["project_id", "title"],
        "additionalProperties": False,
    },
    infer_schema=False,
    roles_allowed=["planner", "estimator"],
)


def _ticket_search(
    ctx: RunContextWrapper[Any],
    query: Optional[str] = None,
    status: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    res = mock_data.search_tickets(query=query, status=status, tags=tags or [])
    return wrap_envelope(
        name="ticket_search",
        args={"query": query, "status": status, "tags": tags},
        data={"results": res},
        recommended_prompts=["Assign to SupportAgent1", "Escalate to Tier 2"],
    )


def _project_task_list(
    ctx: RunContextWrapper[Any],
    project_id: str,
    status: Optional[str] = None,
    assignee: Optional[str] = None,
) -> Dict[str, Any]:
    res = mock_data.list_project_tasks(
        project_id=project_id, status=status, assignee=assignee
    )
    data = (
        {"results": res}
        if res is not None
        else {"message": f"No project found for id {project_id}"}
    )
    return wrap_envelope(
        name="project_task_list",
        args={"project_id": project_id, "status": status, "assignee": assignee},
        data=data,
        recommended_prompts=["Create a follow-up task", "Assign a teammate"],
    )


tool_registry["ticket_search"] = ToolSpec(
    name="ticket_search",
    description="Search support tickets by text, status, and tags",
    func=_ticket_search,
    params_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "status": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": [],
        "additionalProperties": False,
    },
    infer_schema=False,
    roles_allowed=["support"],
)

tool_registry["project_task_list"] = ToolSpec(
    name="project_task_list",
    description="List tasks for a project with optional filters",
    func=_project_task_list,
    params_schema={
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "status": {"type": "string"},
            "assignee": {"type": "string"},
        },
        "required": ["project_id"],
        "additionalProperties": False,
    },
    infer_schema=False,
    roles_allowed=["planner", "estimator"],
)


def _generic_query(
    ctx: RunContextWrapper[Any],
    table: str,
    where: Optional[Dict[str, Any]] = None,
    select: Optional[List[str]] = None,
    sort: Optional[List[Dict[str, str]]] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> Dict[str, Any]:
    res = mock_data.generic_query(
        table=table, where=where, select=select, sort=sort, limit=limit, offset=offset
    )
    return wrap_envelope(
        name="generic_query",
        args={
            "table": table,
            "where": where,
            "select": select,
            "sort": sort,
            "limit": limit,
            "offset": offset,
        },
        data=res,
        recommended_prompts=["Summarize results", "Filter by a different field"],
    )


tool_registry["generic_query"] = ToolSpec(
    name="generic_query",
    description="Run a safe read-only query over mock JSON tables (catalog, orders, tickets, projects).",
    func=_generic_query,
    params_schema={
        "type": "object",
        "properties": {
            "table": {
                "type": "string",
                "enum": ["catalog", "orders", "tickets", "projects"],
            },
            "where": {"type": "object", "additionalProperties": True},
            "select": {"type": "array", "items": {"type": "string"}},
            "sort": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string"},
                        "dir": {"type": "string", "enum": ["asc", "desc"]},
                    },
                    "required": ["field"],
                    "additionalProperties": False,
                },
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
        },
        "required": ["table"],
        "additionalProperties": False,
    },
    infer_schema=False,
    roles_allowed=["planner", "estimator", "support", "sales"],
)


# -----------------------
# Catalog search and facets (Approved)
# -----------------------


def _catalog_search(
    ctx: RunContextWrapper[Any],
    query: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    sort: Optional[str] = None,
    page: Optional[int] = 1,
    page_size: Optional[int] = 10,
) -> Dict[str, Any]:
    res = mock_data.search_catalog(
        query=query,
        filters=filters,
        sort=sort,
        page=page or 1,
        page_size=page_size or 10,
    )
    return wrap_envelope(
        name="catalog_search",
        args={
            "query": query,
            "filters": filters,
            "sort": sort,
            "page": page,
            "page_size": page_size,
        },
        data=res,
        recommended_prompts=[
            "Filter by category Accessories",
            "Sort by price ascending",
            "Show only items in stock",
        ],
    )


def _catalog_facets(ctx: RunContextWrapper[Any], field: str) -> Dict[str, Any]:
    data = mock_data.catalog_facets(field)
    return wrap_envelope(
        name="catalog_facets",
        args={"field": field},
        data={"field": field, "counts": data},
        recommended_prompts=[
            "Search catalog for top facet",
            "Filter results by this facet",
        ],
    )


tool_registry["catalog_search"] = ToolSpec(
    name="catalog_search",
    description="Search the product catalog with optional filters, sort, and paging",
    func=_catalog_search,
    params_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "filters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "price_min": {"type": "number"},
                    "price_max": {"type": "number"},
                },
                "additionalProperties": False,
            },
            "sort": {
                "type": "string",
                "enum": ["price_asc", "price_desc", "rating_desc", "price"],
            },
            "page": {"type": "integer", "minimum": 1, "default": 1},
            "page_size": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "default": 10,
            },
        },
        "required": [],
        "additionalProperties": False,
    },
    infer_schema=False,
    roles_allowed=["sales"],
)

tool_registry["catalog_facets"] = ToolSpec(
    name="catalog_facets",
    description="Return facet counts for a catalog field (category, brand, tags)",
    func=_catalog_facets,
    params_schema={
        "type": "object",
        "properties": {
            "field": {"type": "string", "enum": ["category", "brand", "tags"]}
        },
        "required": ["field"],
        "additionalProperties": False,
    },
    infer_schema=False,
    roles_allowed=["sales"],
)


# -----------------------
# Supabase (scaffold example)
# -----------------------


def _get_supabase():  # pragma: no cover - simple runtime getter
    # Accept common env names; prefer explicit server-side service key variants
    url = os.getenv("SUPABASE_URL")
    raw_key = (
        os.getenv("SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or None
    )
    # Normalize accidental quotes/whitespace in .env
    if isinstance(url, str):
        url = url.strip().strip('"').strip("'")
    key = None
    if isinstance(raw_key, str):
        key = raw_key.strip().strip('"').strip("'")
    if not (url and key and create_client):
        try:
            logger.debug(
                "supabase_get_client_missing url=%s key_present=%s create_client=%s",
                bool(url),
                bool(key),
                bool(create_client),
            )
        except Exception:
            pass
        return None
    try:
        return create_client(url, key)
    except Exception as e:
        try:
            logger.debug("supabase_create_client_error: %s", str(e))
        except Exception:
            pass
        return None


def _supabase_select(
    ctx: RunContextWrapper[Any],
    table: str,
    filters: Optional[Dict[str, Any]] = None,
    limit: Optional[int] = 25,
) -> Dict[str, Any]:
    """Read-only select from a Supabase table with simple equality filters.

    Notes:
    - Uses env SUPABASE_URL + SUPABASE_ANON_KEY/SUPABASE_SERVICE_KEY.
    - Equality filters only (safe default). Extend cautiously.
    """
    sb = _get_supabase()
    if not sb:
        # Provide a slightly more actionable error if client isn't available
        return wrap_envelope(
            name="supabase_select",
            args={"table": table, "filters": filters, "limit": limit},
            data={
                "error": "Supabase client not configured",
                "hint": "Ensure SUPABASE_URL and SUPABASE_SERVICE_KEY (or SUPABASE_SERVICE_ROLE_KEY) are set in backend/.env and the server was restarted.",
            },
        )
    q = sb.table(table).select("*")
    f = filters or {}
    for k, v in f.items():
        q = q.eq(k, v)
    try:
        lim = max(1, min(100, int(limit or 25)))
    except Exception:
        lim = 25
    q = q.limit(lim)
    try:
        resp = q.execute()
        # supabase-py v2 returns a dict-like response with .data
        rows = (
            getattr(resp, "data", None) or resp.get("data")
            if isinstance(resp, dict)
            else None
        )
        # Best-effort debug log (no secrets): include host, table, filters, row_count
        try:
            host = None
            url = os.getenv("SUPABASE_URL")
            if url:
                host = urlparse(url).netloc
            logger.debug(
                "supabase_select ok host=%s table=%s filters=%s limit=%s row_count=%s",
                host,
                table,
                f,
                lim,
                len(rows or []),
            )
        except Exception:
            pass
        return wrap_envelope(
            name="supabase_select",
            args={"table": table, "filters": filters, "limit": lim},
            data={"rows": rows or []},
            meta={
                "row_count": len(rows or []),
                "table": table,
                "filters": f or {},
                "limit": lim,
            },
            recommended_prompts=["Filter by another field", "Increase the limit"],
        )
    except Exception as e:
        # Log error for troubleshooting; avoid leaking secrets
        try:
            host = None
            url = os.getenv("SUPABASE_URL")
            if url:
                host = urlparse(url).netloc
            logger.debug(
                "supabase_select error host=%s table=%s filters=%s limit=%s err=%s",
                host,
                table,
                filters,
                limit,
                str(e),
            )
        except Exception:
            pass
        return wrap_envelope(
            name="supabase_select",
            args={"table": table, "filters": filters, "limit": lim},
            data={"error": str(e)},
        )


tool_registry["supabase_select"] = ToolSpec(
    name="supabase_select",
    description="Read rows from a Supabase table with simple equality filters (env-configured)",
    func=_supabase_select,
    params_schema={
        "type": "object",
        "properties": {
            "table": {"type": "string", "description": "Table name"},
            # Keep filters flexible but avoid explicit additionalProperties to satisfy viz/Pydantic
            "filters": {"type": "object"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
        },
        "required": ["table"],
        # Omit additionalProperties at the root level for compatibility in viz path
    },
    infer_schema=False,
    roles_allowed=["assistant", "support", "sales", "planner", "estimator"],
)


# -----------------------
# Supabase proxy (graph-safe)
# -----------------------


def _supabase_select_proxy(
    ctx: RunContextWrapper[Any],
    table: str,
    filter_key: Optional[str] = None,
    filter_value: Optional[str] = None,
    limit: Optional[int] = 25,
) -> Dict[str, Any]:
    """Graph-safe proxy for Supabase select with simple key/value filter.

    This avoids nested object schemas by accepting a single filter pair. It delegates to
    the underlying supabase_select implementation and then adjusts the envelope to
    reflect the proxy name for UI consistency.
    """
    filters: Optional[Dict[str, Any]] = None
    if filter_key:
        filters = {filter_key: filter_value}
    ret = _supabase_select(ctx=ctx, table=table, filters=filters, limit=limit)
    # Keep the underlying envelope (name = supabase_select) for purist alignment.
    # Optionally annotate meta to indicate the proxy path was used, without changing args/name.
    try:
        if isinstance(ret, dict):
            meta = ret.get("meta") or {}
            meta.setdefault("proxy_for", "supabase_select_proxy")
            # Optionally capture the flat proxy inputs
            meta.setdefault(
                "proxy_args",
                {"filter_key": filter_key, "filter_value": filter_value},
            )
            ret["meta"] = meta
    except Exception:
        pass
    return ret


tool_registry["supabase_select_proxy"] = ToolSpec(
    name="supabase_select_proxy",
    description="Proxy for Supabase select with a simple key/value filter (graph-safe schema)",
    func=_supabase_select_proxy,
    params_schema={
        "type": "object",
        "properties": {
            "table": {"type": "string", "description": "Table name"},
            "filter_key": {"type": "string", "description": "Column to match"},
            "filter_value": {"type": "string", "description": "Value to match"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
        },
        "required": ["table"],
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
