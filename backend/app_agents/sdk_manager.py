from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

# Direct Agents SDK import only
try:
    from agents import RunContextWrapper  # type: ignore
except Exception:
    RunContextWrapper = None  # type: ignore
try:
    from agents import Runner  # type: ignore
except Exception:
    Runner = None  # type: ignore
try:
    from agents import Agent as _Agent  # type: ignore

    Agent = _Agent  # type: ignore
except Exception:
    Agent = None  # type: ignore
try:
    from agents import ModelSettings as _ModelSettings  # type: ignore

    ModelSettings = _ModelSettings  # type: ignore
except Exception:
    ModelSettings = None  # type: ignore
try:
    from agents import SQLiteSession as _SQLiteSession  # type: ignore

    SQLiteSession = _SQLiteSession  # type: ignore
except Exception:
    SQLiteSession = None  # type: ignore
try:
    from agents import function_tool as _function_tool  # type: ignore

    function_tool = _function_tool  # type: ignore
except Exception:
    function_tool = None  # type: ignore

logger = logging.getLogger(__name__)

# Built-in tools (only if Agents SDK is enabled)
FileSearchTool = WebSearchTool = ComputerTool = HostedMCPTool = LocalShellTool = ImageGenerationTool = CodeInterpreterTool = None  # type: ignore


def _ensure_builtin_tools_loaded():
    global FileSearchTool, WebSearchTool, ComputerTool, HostedMCPTool, LocalShellTool, ImageGenerationTool, CodeInterpreterTool
    if FileSearchTool is not None:
        return
    try:
        from agents import CodeInterpreterTool as _CIT  # type: ignore
        from agents import ComputerTool as _CT
        from agents import FileSearchTool as _FST
        from agents import HostedMCPTool as _HMT
        from agents import ImageGenerationTool as _IGT
        from agents import LocalShellTool as _LST
        from agents import WebSearchTool as _WST

        (
            FileSearchTool,
            WebSearchTool,
            ComputerTool,
            HostedMCPTool,
            LocalShellTool,
            ImageGenerationTool,
            CodeInterpreterTool,
        ) = (_FST, _WST, _CT, _HMT, _LST, _IGT, _CIT)
    except Exception:
        FileSearchTool = WebSearchTool = ComputerTool = HostedMCPTool = LocalShellTool = ImageGenerationTool = CodeInterpreterTool = None  # type: ignore


## Removed provider wrappers (LiteLLM, OpenAI Responses); SDK-only
import time

from . import mock_data as _mock
from .core.models.event import Event
from .core.store.memory_store import store
from .registry import get_scenario
from .tools import tool_registry

# In-memory map of active sessions to SQLiteSession objects (file-backed optional later)
# SQLiteSession may be unavailable; store as generic values
_session_cache: Dict[str, Any] = {}
# Optional allowlist for agent-as-tools: { agent_name: [roles...] }
# If an entry exists for an agent, that agent-as-tool will only be enabled when
# the session context roles intersect this set. Leave empty for permissive mode.
AGENT_TOOL_ROLE_ALLOWLIST: Dict[str, list[str]] = {
    # Example:
    # "summarizer": ["agents", "assistant", "supervisor"],
    # "sales": ["supervisor", "general", "agents"],
}

# Load mock data once when module is imported (idempotent)
try:
    import os

    # Data folder is alongside this package: backend/app_agents/data
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "data"))
    _mock.load_all(base)
except Exception:
    pass


class _MinimalSession:
    def __init__(self, session_id: str):
        self.session_id = session_id

    # Match async API shape used by fallbacks
    async def get_items(self):
        return []


def get_or_create_session(session_id: str):
    session = _session_cache.get(session_id)
    if session:
        return session
    try:
        if SQLiteSession is not None:
            session = SQLiteSession(session_id)
        else:
            session = _MinimalSession(session_id)
    except Exception:
        session = _MinimalSession(session_id)
    _session_cache[session_id] = session
    return session


def _resolve_agent_tools(
    names: list[str], session_context: Dict[str, Any] | None = None
):
    tools = []
    _ensure_builtin_tools_loaded()
    # In-file simple boolean switches (safe defaults). Easier to port later.
    BUILTIN_TOOLS_ENABLED = {
        "FileSearchTool": False,
        "WebSearchTool": True,  # enabled as requested
        "ComputerTool": False,
        "HostedMCPTool": False,
        "LocalShellTool": False,  # keep off unless explicitly audited
        "ImageGenerationTool": False,
        "CodeInterpreterTool": False,
    }

    def add_builtin(name: str):
        # Support canonical names and friendly aliases
        key = name
        if name.lower() in {"file_search", "filesearchtool"}:
            key = "FileSearchTool"
        elif name.lower() in {"web_search", "websearchtool"}:
            key = "WebSearchTool"
        elif name.lower() in {"computer", "computertool"}:
            key = "ComputerTool"
        elif name.lower() in {"hosted_mcp", "hostedmcptool"}:
            key = "HostedMCPTool"
        elif name.lower() in {"local_shell", "localshelltool"}:
            key = "LocalShellTool"
        elif name.lower() in {"image_generation", "imagegenerationtool"}:
            key = "ImageGenerationTool"
        elif name.lower() in {"code_interpreter", "codeinterpretertool"}:
            key = "CodeInterpreterTool"
        if not BUILTIN_TOOLS_ENABLED.get(key, False):
            return None
        cls_map = {
            "FileSearchTool": FileSearchTool,
            "WebSearchTool": WebSearchTool,
            "ComputerTool": ComputerTool,
            "HostedMCPTool": HostedMCPTool,
            "LocalShellTool": LocalShellTool,
            "ImageGenerationTool": ImageGenerationTool,
            "CodeInterpreterTool": CodeInterpreterTool,
        }
        cls = cls_map.get(key)
        if cls is None:
            return None
        try:
            # Instantiate with defaults; TODO: wire provider/config as needed
            return cls()
        except Exception:
            return None

    # First: include built-in tools requested by name
    for n in names or []:
        b = add_builtin(n)
        if b is not None:
            tools.append(b)

    # Then: include custom registry functions
    for n in names or []:
        if function_tool is None:
            break
        spec = tool_registry.get(n)
        if not spec:
            continue
        # Dynamic gating by roles if specified on the tool spec
        try:
            roles_allowed = getattr(spec, "roles_allowed", []) or []
        except Exception:
            roles_allowed = []
        if roles_allowed:
            sess_roles = set((session_context or {}).get("roles", []) or [])
            if not sess_roles.intersection(set(roles_allowed)):
                # Skip tool if no intersection between session roles and allowed roles
                continue
        # Try modern signature first; fall back to variants while preserving schema
        # If infer_schema is True, let SDK derive from signature; else pass provided schema
        infer = getattr(spec, "infer_schema", True)
        params = None if infer else (spec.params_schema or None)
        try:
            ft = function_tool(
                spec.func,
                name=spec.name,
                description=spec.description,
                parameters=params,
            )
        except TypeError:
            try:
                # Older signature may accept positional schema arg
                ft = function_tool(spec.func, params)  # type: ignore[arg-type]
            except TypeError:
                try:
                    # Or keyword-only parameters
                    ft = function_tool(spec.func, parameters=params)  # type: ignore[call-arg]
                except TypeError:
                    # Last resort: no schema (may auto-generate); less strict
                    ft = function_tool(spec.func)
        tools.append(ft)
    return tools


# SDK-only mode; no provider toggles


def _build_model_provider(model_name: str):
    # Use raw model string with Agents SDK
    return model_name


def build_agent_network_for_viz(scenario_id: str, root_agent: str | None = None):
    """Construct Agents with tools and native handoffs for visualization.
    Returns (root_agent_obj, name_to_agent_dict).
    This does not modify runtime state; used only for graph viz.
    """
    sc = get_scenario(scenario_id)
    if not sc:
        return None, {}
    try:
        from agents import Agent  # type: ignore
        from agents.extensions.handoff_prompt import \
            prompt_with_handoff_instructions  # type: ignore
    except Exception:
        return None, {}

    # Pre-create all agents without handoffs, then wire handoffs referencing instances
    name_to_agent: Dict[str, Any] = {}
    for ad in sc.agents:
        # For visualization, use a permissive context so role-gated tools appear
        tools = _resolve_agent_tools(
            ad.tools,
            session_context={
                "roles": [ad.name, "agents", "assistant", "sales", "support", "general"]
            },
        )
        prov = _build_model_provider(ad.model)
        instructions = ad.instructions
        try:
            if ad.handoff_targets:
                instructions = prompt_with_handoff_instructions(instructions)
        except Exception:
            pass
        name_to_agent[ad.name] = Agent(
            name=ad.name,
            instructions=instructions,
            model=prov,
            tools=tools,
        )

    # Wire native handoffs using actual Agent instances
    for ad in sc.agents:
        src = name_to_agent.get(ad.name)
        if not src:
            continue
        try:
            from agents import handoff  # type: ignore
        except Exception:
            continue
        handoffs = []
        for tgt_name in ad.handoff_targets or []:
            tgt = name_to_agent.get(tgt_name)
            if tgt is None:
                continue
            # Minimal handoff; customize later with on_handoff/input_type if desired
            try:
                handoffs.append(handoff(agent=tgt))
            except Exception:
                # Fallback: pass agent directly (SDK allows Agent or Handoff)
                handoffs.append(tgt)
        # Recreate with handoffs to avoid mutating internal state
        if handoffs:
            base = src
            name_to_agent[ad.name] = Agent(
                name=base.name,
                instructions=base.instructions,
                model=base.model,
                tools=list(base.tools or []),
                handoffs=handoffs,
            )

    # Determine root for viz: explicit param (case-insensitive), else supervisor, else default_root, else any
    root_candidate = (root_agent or "").strip()
    root_agent_obj = None
    if root_candidate:
        # Case-insensitive match by name
        root_agent_obj = name_to_agent.get(root_candidate)
        if root_agent_obj is None:
            lower_map = {k.lower(): v for k, v in name_to_agent.items()}
            root_agent_obj = lower_map.get(root_candidate.lower())
    if root_agent_obj is None:
        # Try supervisor by role
        sup_name = next(
            (
                a.name
                for a in sc.agents
                if getattr(a, "role", "").lower() == "supervisor"
            ),
            None,
        )
        if sup_name:
            root_agent_obj = name_to_agent.get(sup_name)
    if root_agent_obj is None:
        # Try scenario default_root (case-insensitive)
        if sc.default_root:
            root_agent_obj = name_to_agent.get(sc.default_root) or next(
                (
                    v
                    for k, v in name_to_agent.items()
                    if k.lower() == sc.default_root.lower()
                ),
                None,
            )
    if root_agent_obj is None and name_to_agent:
        # Fallback to first agent defined
        root_agent_obj = next(iter(name_to_agent.values()))

    # Also expose agents-as-tools to the orchestrator for visualization parity
    try:
        orchestrator_name = sc.default_root
        sup = next(
            (
                a.name
                for a in sc.agents
                if getattr(a, "role", "").lower() == "supervisor"
            ),
            None,
        )
        if sup:
            orchestrator_name = sup
        orch = name_to_agent.get(orchestrator_name)
        if orch is not None:
            extra_tools = []
            for ad in sc.agents:
                if ad.name == orchestrator_name:
                    continue
                tgt = name_to_agent.get(ad.name)
                if not tgt:
                    continue
                try:
                    extra_tools.append(
                        tgt.as_tool(
                            tool_name=f"{ad.name}_agent_tool",
                            tool_description=f"Call the {ad.name} agent for a subtask and return the result.",
                            # Visualization: show all agent-tools
                            is_enabled=lambda *_args, **_kwargs: True,
                        )
                    )
                except Exception:
                    pass
            if extra_tools:
                base = orch
                name_to_agent[orchestrator_name] = Agent(
                    name=base.name,
                    instructions=base.instructions,
                    model=base.model,
                    tools=list(base.tools or []) + extra_tools,
                    handoffs=getattr(base, "handoffs", None),
                )
        # If the requested root_agent is different and present, mirror the agent-as-tools for that root too
        if root_agent:
            ra = root_agent
            # Case-insensitive lookup for the provided root agent string
            if ra not in name_to_agent:
                lower_map = {k.lower(): k for k in name_to_agent.keys()}
                ra = lower_map.get(root_agent.lower(), root_agent)
            if ra in name_to_agent and ra != orchestrator_name:
                base = name_to_agent[ra]
                extra_tools2 = []
                for ad in sc.agents:
                    if ad.name == ra:
                        continue
                    tgt = name_to_agent.get(ad.name)
                    if tgt is None:
                        continue
                    try:
                        extra_tools2.append(
                            tgt.as_tool(
                                tool_name=f"{ad.name}_agent_tool",
                                tool_description=f"Call the {ad.name} agent for a subtask and return the result.",
                                is_enabled=lambda *_args, **_kwargs: True,
                            )
                        )
                    except Exception:
                        pass
                if extra_tools2:
                    name_to_agent[ra] = Agent(
                        name=base.name,
                        instructions=base.instructions,
                        model=base.model,
                        tools=list(base.tools or []) + extra_tools2,
                        handoffs=getattr(base, "handoffs", None),
                    )
    except Exception:
        pass
    return root_agent_obj, name_to_agent


def build_agent_network_for_runtime(scenario_id: str, session_id: str | None = None):
    """Construct a name->Agent mapping with tools, native handoffs, and agents-as-tools.
    - Applies handoff prompt to agents that can handoff.
    - Uses session context for tool gating.
    - Adds on_handoff callback that logs a handoff event (UI can apply/dismiss).
    - Exposes other agents as tools to the orchestrator (supervisor or default_root).
    """
    sc = get_scenario(scenario_id)
    if not sc:
        return {}
    try:
        from agents import handoff  # type: ignore
        from agents.extensions.handoff_prompt import \
            prompt_with_handoff_instructions  # type: ignore
    except Exception:
        return {}

    session_context = store.get_context(session_id) if session_id else {}

    # First pass: create agents with tools and (if applicable) handoff prompt
    name_to_agent: Dict[str, Any] = {}
    for ad in sc.agents:
        # Enrich context roles per-agent so role-gated tools (e.g., product_search for Sales) are enabled
        ctx_roles = set((session_context.get("roles") or []))
        ctx_roles.update(
            {ad.name, getattr(ad, "role", "") or "", "agents", "assistant"}
        )
        per_agent_ctx = {**session_context, "roles": list({r for r in ctx_roles if r})}
        tools = _resolve_agent_tools(ad.tools, session_context=per_agent_ctx)
        prov = _build_model_provider(ad.model)
        instructions = ad.instructions
        try:
            if ad.handoff_targets:
                instructions = prompt_with_handoff_instructions(instructions)
        except Exception:
            pass
        ms = ModelSettings(include_usage=True)
        name_to_agent[ad.name] = Agent(
            name=ad.name,
            instructions=instructions,
            model=prov,
            tools=tools,
            model_settings=ms,
        )

    # Second pass: wire native handoffs
    for ad in sc.agents:
        src = name_to_agent.get(ad.name)
        if not src:
            continue

        handoffs = []
        for tgt_name in ad.handoff_targets or []:
            tgt = name_to_agent.get(tgt_name)
            if tgt is None:
                continue

            def _make_cb(target: str):
                def _cb(input: Any | None = None):
                    try:
                        sid = session_id or ""
                        seq = store.next_seq(sid) if sid else 0
                        # Try to extract recommended prompts if present in SDK handoff input
                        rec_prompts = None
                        try:
                            # Common attribute names to probe
                            for k in (
                                "recommended_prompts",
                                "recommendations",
                                "suggested_prompts",
                            ):
                                v = (
                                    getattr(input, k, None)
                                    if input is not None
                                    else None
                                )
                                if v:
                                    rec_prompts = v
                                    break
                        except Exception:
                            rec_prompts = None
                        store.append_event(
                            sid,
                            Event(
                                session_id=sid,
                                seq=seq,
                                # Suggestion emitted by the SDK (not yet applied)
                                type="handoff_suggestion",
                                role="system",
                                agent_id=target,
                                text=None,
                                final=True,
                                reason=(
                                    getattr(input, "reason", None)
                                    if input is not None
                                    else "llm_handoff"
                                ),
                                data={
                                    "from_agent": ad.name,
                                    "to_agent": target,
                                    **(
                                        {"recommended_prompts": rec_prompts}
                                        if rec_prompts
                                        else {}
                                    ),
                                },
                                timestamp_ms=int(time.time() * 1000),
                            ),
                        )
                    except Exception:
                        pass

                return _cb

            try:
                handoffs.append(handoff(agent=tgt, on_handoff=_make_cb(tgt_name)))
            except TypeError:
                try:
                    handoffs.append(handoff(agent=tgt))
                except Exception:
                    handoffs.append(tgt)
        if handoffs:
            base = src
            name_to_agent[ad.name] = Agent(
                name=base.name,
                instructions=base.instructions,
                model=base.model,
                tools=list(base.tools or []),
                handoffs=handoffs,
                model_settings=getattr(base, "model_settings", None),
            )

    # Agents-as-tools for orchestrator (supervisor preferred) and also mirror to default_root
    try:
        orchestrator_name = sc.default_root
        sup = next(
            (
                a.name
                for a in sc.agents
                if getattr(a, "role", "").lower() == "supervisor"
            ),
            None,
        )
        if sup:
            orchestrator_name = sup
        orch = name_to_agent.get(orchestrator_name)
        if orch is not None:
            extra_tools = []
            for ad in sc.agents:
                if ad.name == orchestrator_name:
                    continue
                tgt = name_to_agent.get(ad.name)
                if not tgt:
                    continue

                def _is_enabled(ctx: Any | None = None, agent_name: str = ad.name):
                    """Gate agent-as-tool availability by session context roles.
                    Defaults to enabled when no roles are provided to make the
                    feature work out-of-the-box; can be restricted by setting
                    context.roles to a list that omits the agent name and the
                    special "agents" flag.
                    """
                    try:
                        roles = set(((ctx or {}).get("roles") or []))
                        # If there's a specific allowlist configured for this agent, enforce it
                        allow = AGENT_TOOL_ROLE_ALLOWLIST.get(agent_name)
                        if isinstance(allow, list) and allow:
                            return bool(roles.intersection(set(allow)))
                        # If no roles provided, default to enabled for better UX
                        if not roles:
                            return True
                        return agent_name in roles or "agents" in roles
                    except Exception:
                        return True

                try:
                    extra_tools.append(
                        tgt.as_tool(
                            tool_name=f"{ad.name}_agent_tool",
                            tool_description=f"Call the {ad.name} agent for a subtask and return the result.",
                            is_enabled=_is_enabled,
                        )
                    )
                except Exception:
                    pass
            if extra_tools:
                base = orch
                name_to_agent[orchestrator_name] = Agent(
                    name=base.name,
                    instructions=base.instructions,
                    model=base.model,
                    tools=list(base.tools or []) + extra_tools,
                    handoffs=getattr(base, "handoffs", None),
                    model_settings=getattr(base, "model_settings", None),
                )

        # Mirror agents-as-tools to the scenario default_root as well so the initial active agent
        # can perform subroutine calls (e.g., summarizer) without switching to supervisor.
        if sc.default_root and sc.default_root in name_to_agent:
            root_name = sc.default_root
            base = name_to_agent[root_name]
            extra_tools2 = []
            for ad in sc.agents:
                if ad.name == root_name:
                    continue
                tgt = name_to_agent.get(ad.name)
                if not tgt:
                    continue

                def _is_enabled_root(ctx: Any | None = None, agent_name: str = ad.name):
                    try:
                        roles = set(((ctx or {}).get("roles") or []))
                        allow = AGENT_TOOL_ROLE_ALLOWLIST.get(agent_name)
                        if isinstance(allow, list) and allow:
                            return bool(roles.intersection(set(allow)))
                        if not roles:
                            return True
                        return agent_name in roles or "agents" in roles
                    except Exception:
                        return True

                try:
                    extra_tools2.append(
                        tgt.as_tool(
                            tool_name=f"{ad.name}_agent_tool",
                            tool_description=f"Call the {ad.name} agent for a subtask and return the result.",
                            is_enabled=_is_enabled_root,
                        )
                    )
                except Exception:
                    pass
            if extra_tools2:
                name_to_agent[root_name] = Agent(
                    name=getattr(base, "name", root_name),
                    instructions=getattr(base, "instructions", None),
                    model=getattr(base, "model", None),
                    tools=list(getattr(base, "tools", []) or []) + extra_tools2,
                    handoffs=getattr(base, "handoffs", None),
                    model_settings=getattr(base, "model_settings", None),
                )
    except Exception:
        pass

    return name_to_agent


## Removed Responses payload extraction helper


def providers_probe() -> Dict[str, bool]:
    # SDK-only: report Agents SDK availability; others false
    return {"openai_responses": False, "litellm": False, "agents_sdk": True}


def _extract_usage(result: Any) -> Dict[str, Any] | None:
    """Best-effort extraction of token usage from Agents SDK result."""
    # Common shapes to probe without strict coupling
    cand = getattr(result, "usage", None) or getattr(result, "meta", None)
    if not cand and hasattr(result, "response"):
        cand = getattr(result.response, "usage", None)
    if not cand:
        return None
    # Normalize to {input_tokens, output_tokens, total_tokens}
    in_tok = (
        getattr(cand, "input_tokens", None) or cand.get("input_tokens")
        if isinstance(cand, dict)
        else None
    )
    out_tok = (
        getattr(cand, "output_tokens", None) or cand.get("output_tokens")
        if isinstance(cand, dict)
        else None
    )
    total = (
        getattr(cand, "total_tokens", None) or cand.get("total_tokens")
        if isinstance(cand, dict)
        else None
    )
    if in_tok is None and out_tok is None and total is None:
        return None
    return {
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "total_tokens": (
            total if total is not None else ((in_tok or 0) + (out_tok or 0))
        ),
    }


async def create_agent_session(
    session_id: str,
    name: str,
    instructions: str,
    model: str = "gpt-4.1-mini",
    scenario_id: str | None = None,
    overlay: str | None = None,
) -> Dict[str, Any]:
    # Ensure SDK is loaded before session creation so we don't return a sentinel
    session = get_or_create_session(session_id)
    # Pull allowlist from scenario if provided
    tools = []
    if scenario_id:
        sc = get_scenario(scenario_id)
        if sc:
            ad = next(
                (
                    a
                    for a in sc.agents
                    if a.name == name or a.name.lower() == str(name).lower()
                ),
                None,
            )
            if ad:
                tools = _resolve_agent_tools(
                    ad.tools, session_context=store.get_context(session_id)
                )
    # Apply handoff prompt if extension available and agent participates in handoffs
    try:
        from agents.extensions.handoff_prompt import \
            prompt_with_handoff_instructions  # type: ignore

        sc = get_scenario(scenario_id) if scenario_id else None
        ad = None
        if sc:
            ad = next((a for a in sc.agents if a.name == name), None)
        instr = (
            prompt_with_handoff_instructions(instructions)
            if ad and ad.handoff_targets
            else instructions
        )
    except Exception:
        instr = instructions

    # Guard against realtime-only models when not in Realtime API flow
    try:
        if isinstance(model, str) and "realtime" in model:
            model = "gpt-4.1-mini"
    except Exception:
        pass
    prov = _build_model_provider(model)
    if Agent is not None:
        ms = ModelSettings(include_usage=True)
        Agent(name=name, instructions=instr, model=prov, tools=tools, model_settings=ms)
    # Optionally run a priming turn (not required)
    return {
        "session_id": session_id,
        "agent_name": name,
        "model": model,
        "tools": [t.name for t in tools],
        "overlay": overlay,
    }


async def run_agent_turn(
    session_id: str,
    user_input: str,
    agent_spec: Dict[str, Any],
    scenario_id: str | None = None,
) -> Dict[str, Any]:
    session = get_or_create_session(session_id)
    # Reconstruct lightweight agent each call (cheap); could cache if instructions stable
    name = agent_spec.get("name", "Assistant")
    tools = []
    runtime_agent = None
    if scenario_id:
        try:
            network = build_agent_network_for_runtime(
                scenario_id, session_id=session_id
            )
        except Exception as e:
            # Log but continue with a single agent so we still produce a reply
            try:
                seq = store.next_seq(session_id)
                store.append_event(
                    session_id,
                    Event(
                        session_id=session_id,
                        seq=seq,
                        type="log",
                        role="system",
                        agent_id=name,
                        text=f"runtime_network_error: {e}",
                        final=True,
                        timestamp_ms=int(time.time() * 1000),
                    ),
                )
            except Exception:
                pass
            network = None
        if network:
            runtime_agent = network.get(name)
            try:
                tools = list(getattr(runtime_agent, "tools", []) or [])
            except Exception:
                tools = []
    # Handoff instructions if applicable
    base_instr = agent_spec.get("instructions", "You are a helpful assistant.")
    try:
        from agents.extensions.handoff_prompt import \
            prompt_with_handoff_instructions  # type: ignore

        sc = get_scenario(scenario_id) if scenario_id else None
        ad = None
        if sc:
            ad = next((a for a in sc.agents if a.name == name), None)
        instr = (
            prompt_with_handoff_instructions(base_instr)
            if ad and ad.handoff_targets
            else base_instr
        )
    except Exception:
        instr = base_instr
    # Fallback if Agents SDK not available: use single-turn helper
    mdl = agent_spec.get("model", "gpt-4.1-mini")
    try:
        if isinstance(mdl, str) and "realtime" in mdl:
            mdl = "gpt-4.1-mini"
    except Exception:
        pass
    prov = _build_model_provider(mdl)
    if not (Agent is not None and Runner is not None):
        # SDK not available; return empty response while logging
        try:
            seq = store.next_seq(session_id)
            store.append_event(
                session_id,
                Event(
                    session_id=session_id,
                    seq=seq,
                    type="log",
                    role="system",
                    agent_id=name,
                    text="agents_sdk_unavailable",
                    final=True,
                    timestamp_ms=int(time.time() * 1000),
                ),
            )
        except Exception:
            pass
        return {
            "final_output": "",
            "new_items_len": 0,
            "tool_calls": [],
            "used_tools": [],
            "usage": None,
        }
    # Agents SDK path
    if runtime_agent is None:
        ms = ModelSettings(include_usage=True)
        agent = Agent(
            name=name, instructions=instr, model=prov, tools=tools, model_settings=ms
        )
    else:
        agent = runtime_agent
    try:
        ctx = RunContextWrapper(store.get_context(session_id)) if RunContextWrapper else None  # type: ignore
        result = await Runner.run(
            agent, user_input, session=session, context=(ctx.context if ctx else None)
        )
    except Exception as e:
        # Emit a log event and continue to fallback
        try:
            seq = store.next_seq(session_id)
            store.append_event(
                session_id,
                Event(
                    session_id=session_id,
                    seq=seq,
                    type="log",
                    role="system",
                    agent_id=name,
                    text=f"agents_sdk_error: {e}",
                    final=True,
                    timestamp_ms=int(time.time() * 1000),
                ),
            )
        except Exception:
            pass

        # Synthesize minimal result shape to drive fallback
        class _Empty:
            final_output = ""
            new_items: list[Any] = []

        result = _Empty()
    # Emit tool_call/tool_result events opportunistically
    try:
        last_tool_name: Any = None
        for i in getattr(result, "new_items", []) or []:
            # Tool call
            def _extract_name(item: Any) -> Any:
                try:
                    v = getattr(item, "tool_name", None) or getattr(item, "name", None)
                    if v:
                        return v
                    if isinstance(item, dict):
                        call = item.get("call") or {}
                        return (
                            item.get("tool_name")
                            or item.get("tool")
                            or item.get("name")
                            or (call.get("name") if isinstance(call, dict) else None)
                        )
                except Exception:
                    return None
                return None

            tname = _extract_name(i)
            if tname:
                last_tool_name = tname
                seq = store.next_seq(session_id)
                ev = Event(
                    session_id=session_id,
                    seq=seq,
                    type="tool_call",
                    role="tool",
                    agent_id=name,
                    text=None,
                    final=False,
                    data={
                        "tool": tname,
                        "tool_name": tname,
                        "args": getattr(i, "args", None)
                        or getattr(i, "tool_arguments", None),
                    },
                    timestamp_ms=int(time.time() * 1000),
                    # Duplicate for easier FE resolution
                    tool=tname,  # type: ignore[arg-type]
                    tool_name=tname,  # type: ignore[arg-type]
                )
                store.append_event(session_id, ev)
            # Tool result (best-effort)
            tout = getattr(i, "tool_output", None) or getattr(i, "output", None)
            if tout is not None:
                seq = store.next_seq(session_id)
                res_tool = _extract_name(i) or tname or last_tool_name
                # Optional specialized shaping for agent-as-tool outputs, especially summarizer
                text_out = None
                extra: Dict[str, Any] = {}
                recommended_prompts: list[str] | None = None
                # First, check if the output already matches our ToolEnvelope contract
                try:
                    if isinstance(tout, dict) and (
                        "ok" in tout
                        and "name" in tout
                        and ("data" in tout or "args" in tout)
                    ):
                        # Use envelope fields directly
                        res_tool = tout.get("name") or res_tool
                        recommended_prompts = tout.get("recommended_prompts") or None
                        # Prefer a concise textual summary from data if present
                        data_field = tout.get("data")
                        if isinstance(data_field, dict) and data_field.get("summary"):
                            text_out = str(data_field.get("summary"))
                        elif isinstance(data_field, dict) and data_field.get("message"):
                            text_out = str(data_field.get("message"))
                        else:
                            # fallback later to str(tout)
                            pass
                        # Ensure extra captures raw envelope
                        extra["envelope"] = tout
                except Exception:
                    recommended_prompts = None
                try:
                    # Summarizer agent-as-tool uses tool name like "summarizer_agent_tool"
                    if isinstance(res_tool, str) and res_tool.lower().startswith(
                        "summarizer_"
                    ):
                        # Try to parse structured JSON first
                        raw = tout
                        parsed = None
                        if isinstance(raw, str):
                            import json as _json  # local import to avoid overhead when unused

                            try:
                                parsed = _json.loads(raw)
                            except Exception:
                                parsed = None
                        elif isinstance(raw, (dict, list)):
                            parsed = raw
                        # Build a concise text if we have structured fields
                        if isinstance(parsed, dict):
                            summ = (
                                parsed.get("summary")
                                or parsed.get("synopsis")
                                or parsed.get("brief")
                            )
                            bullets = parsed.get("bullets") or parsed.get("key_points")
                            if isinstance(bullets, list):
                                bullets_txt = "\n".join(
                                    [
                                        f"• {str(b).strip()}"
                                        for b in bullets
                                        if str(b).strip()
                                    ]
                                )
                            else:
                                bullets_txt = None
                            pieces = []
                            if isinstance(summ, str) and summ.strip():
                                pieces.append(summ.strip())
                            if bullets_txt:
                                pieces.append(bullets_txt)
                            if pieces:
                                text_out = "\n".join(pieces)
                                extra["parsed"] = parsed
                        # If still no text_out, try to extract bullets from plain text
                        if not text_out:
                            s = raw if isinstance(raw, str) else str(raw)
                            # Keep it concise
                            text_out = s.strip()
                    # Default path for other tools (or if envelope didn't supply concise text)
                    if text_out is None:
                        text_out = str(tout)
                except Exception:
                    text_out = str(tout)
                # Cap very long outputs for UI safety; raw is preserved in extra if parsed
                safe_text = (text_out or "")[:4000]
                # Attach structured/raw output for Tool Outputs panel
                data_payload = {"tool": res_tool, "tool_name": res_tool}
                # Preserve raw output for JSON view
                try:
                    data_payload["output"] = tout
                except Exception:
                    pass
                if isinstance(tout, (dict, list)):
                    data_payload.setdefault("raw", tout)
                if extra:
                    data_payload["extra"] = extra
                if recommended_prompts:
                    data_payload["recommended_prompts"] = recommended_prompts
                evr = Event(
                    session_id=session_id,
                    seq=seq,
                    type="tool_result",
                    role="tool",
                    agent_id=name,
                    text=safe_text,
                    final=True,
                    data=data_payload,
                    timestamp_ms=int(time.time() * 1000),
                    # Duplicate for easier FE resolution
                    tool=res_tool,  # type: ignore[arg-type]
                    tool_name=res_tool,  # type: ignore[arg-type]
                )
                store.append_event(session_id, evr)
    except Exception:
        pass
    # Extract token usage and accumulate per session
    usage = None
    try:
        # Agents SDK guidance: result.context_wrapper.usage
        ctx = getattr(result, "context_wrapper", None)
        if ctx is not None:
            u = getattr(ctx, "usage", None)
            if u is not None:
                # normalize
                usage = {
                    "requests": getattr(u, "requests", None),
                    "input_tokens": getattr(u, "input_tokens", None),
                    "output_tokens": getattr(u, "output_tokens", None),
                    "total_tokens": getattr(u, "total_tokens", None),
                }
        if not usage:
            usage = _extract_usage(result)
        if usage:
            totals = store.add_usage(session_id, usage)
            usage = {**usage, "aggregated": totals}
        else:
            # Fallback: count the request so Usage panel isn't stuck at zero
            totals = store.add_usage(
                session_id,
                {
                    "requests": 1,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                },
            )
            usage = {
                "requests": 1,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "aggregated": totals,
            }
    except Exception:
        pass

    # Try to extract assistant text from the Agents SDK result
    def _extract_text_from_result(res: Any) -> str | None:
        try:
            for attr in ("final_output", "output_text", "text", "message"):
                v = getattr(res, attr, None)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            # Try new_items content text
            items = getattr(res, "new_items", None)
            if isinstance(items, list) and items:
                parts: list[str] = []
                for it in items:
                    # favor assistant-like outputs
                    seg = getattr(it, "output", None) or getattr(it, "content", None)
                    if isinstance(seg, list):
                        for c in seg:
                            try:
                                t = (
                                    c.get("text")
                                    if isinstance(c, dict)
                                    else getattr(c, "text", None)
                                )
                                if isinstance(t, str) and t.strip():
                                    parts.append(t.strip())
                            except Exception:
                                continue
                    elif isinstance(seg, str) and seg.strip():
                        parts.append(seg.strip())
                if parts:
                    return "\n".join(parts).strip()
            r = getattr(res, "response", None)
            # dict-like response object support
            if isinstance(r, dict):
                # direct output_text/content on response
                for k in ("output_text", "content", "message", "text"):
                    if isinstance(r.get(k), str) and r.get(k).strip():
                        return r.get(k).strip()
                out = r.get("output")
                if isinstance(out, list):
                    parts: list[str] = []
                    for item in out:
                        if not isinstance(item, dict):
                            continue
                        content = item.get("content")
                        if isinstance(content, list):
                            for c in content:
                                if (
                                    isinstance(c, dict)
                                    and c.get("type")
                                    in ("output_text", "text", "input_text")
                                    and c.get("text")
                                ):
                                    parts.append(str(c.get("text")))
                        elif isinstance(item.get("text"), str):
                            parts.append(item.get("text"))
                    if parts:
                        return "\n".join(parts).strip()
        except Exception:
            return None
        return None

    # If Agents SDK produced no assistant text, try to read from session items
    final_text = _extract_text_from_result(result)
    if not final_text and hasattr(session, "get_items"):
        try:
            items = await session.get_items()

            # Items may be dicts or objects; find the latest assistant message-like item
            def _getitem(d, k, default=None):
                try:
                    return (
                        d.get(k, default)
                        if isinstance(d, dict)
                        else getattr(d, k, default)
                    )
                except Exception:
                    return default

            for itm in reversed(items or []):
                role = str(_getitem(itm, "role", "") or "").lower()
                text = _getitem(itm, "text", None) or _getitem(itm, "content", None)
                typ = str(_getitem(itm, "type", "") or "").lower()
                if (
                    (role in ("assistant", "assistant_reply") or typ == "message")
                    and isinstance(text, str)
                    and text.strip()
                ):
                    final_text = text.strip()
                    break
        except Exception:
            pass
    used_fallback = False
    # As a last resort, provide a tiny placeholder so UI sees a visible assistant reply
    safe_text = final_text or getattr(result, "final_output", None) or ""
    if not safe_text:
        safe_text = ""
    return {
        "final_output": safe_text,
        "new_items_len": len(getattr(result, "new_items", []) or []),
        "tool_calls": [
            getattr(i, "tool_name", None)
            for i in (getattr(result, "new_items", []) or [])
            if hasattr(i, "tool_name")
        ],
        "used_tools": [getattr(t, "name", None) or str(t) for t in (tools or [])],
        "usage": usage,
        "used_fallback": used_fallback,
    }


async def run_supervisor_orchestrate(
    scenario_id: str,
    last_user_text: str,
    session_id: str | None = None,
) -> Dict[str, Any]:
    """Run a supervisor agent (if defined in scenario) that can call a `handoff` tool
    to select a target agent and provide a reason. Falls back to heuristic if missing.
    Returns { chosen_root, reason, changed } and persists handoff if session_id provided.
    """
    sc = get_scenario(scenario_id)
    if not sc:
        return {"chosen_root": None, "reason": "no_such_scenario", "changed": False}
    sup = next(
        (
            a
            for a in sc.agents
            if getattr(a, "role", "").lower() == "supervisor" or a.name == "supervisor"
        ),
        None,
    )
    # If Agents SDK isn't available, skip supervisor and use heuristic
    if False:
        text = (last_user_text or "").lower()

        def pick_agent() -> str:
            if any(
                k in text
                for k in ["buy", "price", "recommend", "product", "catalog", "purchase"]
            ):
                return (
                    "sales"
                    if any(a.name == "sales" for a in sc.agents)
                    else sc.default_root
                )
            if any(
                k in text
                for k in [
                    "error",
                    "issue",
                    "problem",
                    "troubleshoot",
                    "not working",
                    "help",
                ]
            ):
                return (
                    "support"
                    if any(a.name == "support" for a in sc.agents)
                    else sc.default_root
                )
            return sc.default_root

        chosen = pick_agent()
        reason = "heuristic_router"
        changed = False
        if session_id:
            try:
                sess = store.get_session(session_id)
                if not sess:
                    store.create_session(session_id, active_agent_id=chosen)
                    sess = store.get_session(session_id)
                if sess and sess.active_agent_id != chosen:
                    changed = True
                    store.set_active_agent(session_id, chosen)
                    seq = store.next_seq(session_id)
                    ev = Event(
                        session_id=session_id,
                        seq=seq,
                        type="handoff",
                        role="system",
                        agent_id=chosen,
                        text=None,
                        final=True,
                        reason=reason,
                        timestamp_ms=int(time.time() * 1000),
                    )
                    store.append_event(session_id, ev)
            except Exception:
                pass
        return {"chosen_root": chosen, "reason": reason, "changed": changed}
    if not sup:
        # LLM-only mode: no supervisor => do not change active agent here.
        return {
            "chosen_root": sc.default_root,
            "reason": "no_supervisor",
            "changed": False,
        }

    # Build supervisor with a `handoff` function tool
    decision: Dict[str, Any] = {"target": sc.default_root, "reason": "no_call"}
    try:
        valid_targets = [a.name for a in sc.agents]

        def handoff(target: str, reason: str | None = None):
            nonlocal decision
            valid = set(valid_targets)
            if target not in valid:
                decision = {
                    "target": decision.get("target", sc.default_root),
                    "reason": f"invalid_target:{target}",
                }
            else:
                decision = {"target": target, "reason": reason or "supervisor_choice"}
            return {"ok": True, **decision}

        handoff_schema = {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Agent name to activate (one of: %s)"
                    % ", ".join(valid_targets),
                    "enum": valid_targets,
                },
                "reason": {"type": "string"},
            },
            "required": ["target"],
        }
        # Create handoff tool with compatibility across SDK versions
        try:
            handoff_tool = function_tool(
                handoff,
                name="handoff",
                description="Select the best agent to handle the user.",
                parameters=handoff_schema,
            )
        except TypeError:
            try:
                handoff_tool = function_tool(handoff, handoff_schema)  # type: ignore[arg-type]
            except TypeError:
                try:
                    handoff_tool = function_tool(handoff, parameters=handoff_schema)  # type: ignore[call-arg]
                except TypeError:
                    handoff_tool = function_tool(handoff)

        # Apply model provider
        prov = _build_model_provider(sup.model)
        ms = None
        try:
            if getattr(prov, "__class__", type("_", (), {})).__name__.lower() == "litellmmodel":  # type: ignore[attr-defined]
                ms = ModelSettings(include_usage=True)
        except Exception:
            pass

        instr = sup.instructions
        try:
            from agents.extensions.handoff_prompt import \
                prompt_with_handoff_instructions  # type: ignore

            instr = prompt_with_handoff_instructions(instr)
        except Exception:
            pass

        if ms is not None:
            supervisor = Agent(
                name=sup.name,
                instructions=instr,
                model=prov,
                tools=[handoff_tool],
                model_settings=ms,
            )
        else:
            supervisor = Agent(
                name=sup.name, instructions=instr, model=prov, tools=[handoff_tool]
            )
        session = get_or_create_session(session_id or f"sup-{sc.id}")
        try:
            await Runner.run(supervisor, last_user_text or "", session=session)
        except Exception as e:
            # Log a supervisor error event for debugging
            try:
                seq = store.next_seq(session_id or f"sup-{sc.id}")
                store.append_event(
                    session_id or f"sup-{sc.id}",
                    Event(
                        session_id=(session_id or f"sup-{sc.id}"),
                        seq=seq,
                        type="log",
                        role="system",
                        agent_id=sup.name,
                        text=f"supervisor_error: {e}",
                        final=True,
                        timestamp_ms=int(time.time() * 1000),
                    ),
                )
            except Exception:
                pass
    except Exception:
        # Entire supervisor setup failed; fall back
        pass

    chosen = decision.get("target", sc.default_root)
    reason = decision.get("reason", "supervisor_default")

    # If supervisor didn't call the handoff tool, do not change active agent.
    if reason == "no_call":
        return {
            "chosen_root": sc.default_root,
            "reason": "supervisor_no_call",
            "changed": False,
        }
    changed = False
    if session_id:
        try:
            sess = store.get_session(session_id)
            if not sess:
                store.create_session(session_id, active_agent_id=chosen)
                sess = store.get_session(session_id)
            if sess and sess.active_agent_id != chosen:
                changed = True
                store.set_active_agent(session_id, chosen)
                seq = store.next_seq(session_id)
                ev = Event(
                    session_id=session_id,
                    seq=seq,
                    type="handoff",
                    role="system",
                    agent_id=chosen,
                    text=None,
                    final=True,
                    reason=reason,
                    timestamp_ms=int(time.time() * 1000),
                )
                store.append_event(session_id, ev)
        except Exception:
            pass
    return {"chosen_root": chosen, "reason": reason, "changed": changed}


async def get_session_transcript(session_id: str) -> Dict[str, Any]:
    session = get_or_create_session(session_id)
    # If Agents SDK session not available, synthesize transcript from event store
    if not hasattr(session, "get_items"):
        events = store.list_events(session_id)
        items = [e.model_dump() for e in events]
        return {"session_id": session_id, "items": items, "length": len(items)}
    items = await session.get_items()
    return {"session_id": session_id, "items": items, "length": len(items)}
