from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

# Simple in-memory stores + journal for mock writes
CATALOG: List[Dict[str, Any]] = []
ORDERS: List[Dict[str, Any]] = []
TICKETS: List[Dict[str, Any]] = []
PROJECTS: List[Dict[str, Any]] = []
JOURNAL: List[Dict[str, Any]] = []


def _load_json(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_all(data_dir: str | Path) -> None:
    base = Path(data_dir)
    global CATALOG, ORDERS, TICKETS, PROJECTS
    CATALOG = _load_json(base / "catalog.json")
    ORDERS = _load_json(base / "orders.json")
    TICKETS = _load_json(base / "tickets.json")
    PROJECTS = _load_json(base / "projects.json")


def find_order(order_id: str) -> Dict[str, Any] | None:
    for o in ORDERS:
        if o.get("order_id") == order_id:
            return o
    return None


def create_order(
    items: List[Dict[str, Any]], customer_info: Dict[str, Any]
) -> Dict[str, Any]:
    new_id = f"ord-{1000 + len(ORDERS) + 1}"
    total = sum((it.get("price", 0) * it.get("qty", 1) for it in items))
    order = {
        "order_id": new_id,
        "customer": customer_info,
        "items": items,
        "total": round(total, 2),
        "status": "placed",
        "created_at": "2025-10-20",
    }
    ORDERS.append(order)
    JOURNAL.append({"type": "order_create", "order": order})
    return order


def update_ticket(
    ticket_id: str, status: str | None = None, note: str | None = None
) -> Dict[str, Any] | None:
    for t in TICKETS:
        if t.get("ticket_id") == ticket_id:
            if status:
                t["status"] = status
            if note:
                t.setdefault("notes", []).append(note)
            JOURNAL.append(
                {
                    "type": "ticket_update",
                    "ticket_id": ticket_id,
                    "status": status,
                    "note": note,
                }
            )
            return t
    return None


def create_project_task(
    project_id: str, title: str, assignee: str | None = None, due: str | None = None
) -> Dict[str, Any] | None:
    for p in PROJECTS:
        if p.get("project_id") == project_id:
            tasks = p.setdefault("tasks", [])
            new_task = {
                "id": f"task-{len(tasks) + 1}",
                "title": title,
                "assignee": assignee,
                "due": due,
                "status": "todo",
            }
            tasks.append(new_task)
            JOURNAL.append(
                {
                    "type": "project_task_create",
                    "project_id": project_id,
                    "task": new_task,
                }
            )
            return new_task
    return None


# -----------------------
# Search / listing helpers
# -----------------------


def search_catalog(
    query: str | None = None,
    filters: Dict[str, Any] | None = None,
    sort: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> Dict[str, Any]:
    q = (query or "").strip().lower()
    items = CATALOG[:]
    if q:
        items = [
            it
            for it in items
            if q in str(it.get("name", "")).lower()
            or q in str(it.get("category", "")).lower()
            or q in str(it.get("brand", "")).lower()
        ]
    f = filters or {}
    cat = f.get("category")
    if cat:
        items = [it for it in items if str(it.get("category")) == str(cat)]
    tags = f.get("tags") or []
    if isinstance(tags, list) and tags:
        tset = set(str(t).lower() for t in tags)
        items = [
            it
            for it in items
            if set(str(x).lower() for x in (it.get("tags") or [])).intersection(tset)
        ]
    # Numeric filters
    pmin = f.get("price_min")
    pmax = f.get("price_max")
    if pmin is not None:
        items = [it for it in items if float(it.get("price", 0)) >= float(pmin)]
    if pmax is not None:
        items = [it for it in items if float(it.get("price", 0)) <= float(pmax)]
    # Sorting
    s = (sort or "").lower()
    if s in ("price_asc", "price"):
        items.sort(key=lambda it: float(it.get("price", 0)))
    elif s == "price_desc":
        items.sort(key=lambda it: float(it.get("price", 0)), reverse=True)
    elif s == "rating_desc":
        items.sort(key=lambda it: float(it.get("rating", 0)), reverse=True)
    # Paging
    page = max(1, int(page or 1))
    page_size = max(1, min(50, int(page_size or 10)))
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "total": len(items),
        "page": page,
        "page_size": page_size,
        "results": items[start:end],
    }


def catalog_facets(field: str) -> Dict[str, int]:
    """Compute facet counts for the catalog on allowed fields.

    Supported fields: 'category', 'brand', 'tags'.
    Returns a mapping of value -> count. For tags, each tag occurrence is counted.
    """
    key = str(field or "").lower()
    allowed = {"category", "brand", "tags"}
    if key not in allowed:
        return {}
    counts: Dict[str, int] = {}
    for it in CATALOG:
        if key == "tags":
            for tag in it.get("tags") or []:
                k = str(tag)
                counts[k] = counts.get(k, 0) + 1
        else:
            k = str(it.get(key))
            if k and k != "None":
                counts[k] = counts.get(k, 0) + 1
    return counts


def search_tickets(
    query: str | None = None,
    status: str | None = None,
    tags: List[str] | None = None,
) -> List[Dict[str, Any]]:
    q = (query or "").strip().lower()
    items = TICKETS[:]
    if q:
        items = [
            it
            for it in items
            if q in str(it.get("subject", "")).lower()
            or q in str(it.get("body", "")).lower()
        ]
    if status:
        items = [it for it in items if str(it.get("status")) == str(status)]
    if tags:
        tset = set(str(t).lower() for t in tags)
        items = [
            it
            for it in items
            if set(str(x).lower() for x in (it.get("tags") or [])).intersection(tset)
        ]
    return items


def list_project_tasks(
    project_id: str,
    status: str | None = None,
    assignee: str | None = None,
) -> List[Dict[str, Any]] | None:
    for p in PROJECTS:
        if p.get("project_id") == project_id:
            tasks = p.get("tasks") or []
            items = tasks[:]
            if status:
                items = [t for t in items if str(t.get("status")) == str(status)]
            if assignee:
                items = [t for t in items if str(t.get("assignee")) == str(assignee)]
            return items
    return None


# -----------------------
# Generic read-only query DSL
# -----------------------

ALLOWED_TABLES: Dict[str, Any] = {
    "catalog": lambda: CATALOG,
    "orders": lambda: ORDERS,
    "tickets": lambda: TICKETS,
    "projects": lambda: PROJECTS,
}


def _get_table(name: str) -> List[Dict[str, Any]]:
    getter = ALLOWED_TABLES.get(name)
    if not getter:
        return []
    try:
        return list(getter())
    except Exception:
        return []


def _op_compare(val: Any, op: str, rhs: Any) -> bool:
    try:
        if op == "=":
            return val == rhs
        if op == "<":
            return float(val) < float(rhs)
        if op == ">":
            return float(val) > float(rhs)
        if op == "< =" or op == "<=":
            return float(val) <= float(rhs)
        if op == "> =" or op == ">=":
            return float(val) >= float(rhs)
        if op.lower() == "in":
            try:
                coll = rhs if isinstance(rhs, list) else [rhs]
                return val in coll
            except Exception:
                return False
        if op.lower() == "contains":
            if isinstance(val, list):
                return rhs in val
            return str(rhs).lower() in str(val).lower()
    except Exception:
        return False
    return False


def generic_query(
    table: str,
    where: Dict[str, Any] | None = None,
    select: List[str] | None = None,
    sort: List[Dict[str, str]] | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> Dict[str, Any]:
    # Guard: only known tables
    tbl = str(table or "").strip()
    items = _get_table(tbl)
    # Apply filters (AND only)
    w = where or {}

    def item_ok(it: Dict[str, Any]) -> bool:
        for field, cond in w.items():
            if isinstance(cond, dict):
                for op, rhs in cond.items():
                    if not _op_compare(it.get(field), str(op), rhs):
                        return False
            else:
                if it.get(field) != cond:
                    return False
        return True

    if w:
        items = [it for it in items if item_ok(it)]
    # Sorting
    if sort:
        for rule in reversed(sort):
            f = str(rule.get("field", ""))
            d = str(rule.get("dir", "asc")).lower()
            items.sort(key=lambda it: it.get(f), reverse=(d == "desc"))
    total = len(items)
    # Project fields
    if select:
        fields = [str(f) for f in select]

        def project(it: Dict[str, Any]) -> Dict[str, Any]:
            return {k: it.get(k) for k in fields}

        items = [project(it) for it in items]
    # Pagination
    off = max(0, int(offset or 0))
    lim = max(1, min(100, int(limit or 25)))
    return {
        "total": total,
        "items": items[off : off + lim],
        "offset": off,
        "limit": lim,
    }
