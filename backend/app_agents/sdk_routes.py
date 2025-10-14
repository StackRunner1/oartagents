from __future__ import annotations

import asyncio
import base64
import logging
import time
from uuid import uuid4

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import sdk_manager
## Removed Responses fallback; SDK-only execution path.
from .core.models.event import Event
from .core.store.memory_store import store

router = APIRouter()
logger = logging.getLogger(__name__)


# ---- SDK: Session Create/Delete/Message ----
class SDKSessionCreateRequest(BaseModel):
    session_id: str | None = Field(
        None, description="Client provided session id (optional)"
    )
    agent_name: str = Field("assistant", description="Logical name for the agent")
    instructions: str = Field(
        ..., description="System / developer instructions for the agent"
    )
    model: str = Field("gpt-4.1-mini", description="Model to use for the agent")
    scenario_id: str | None = Field(None, description="Scenario to bind to")
    overlay: str | None = Field(None, description="Optional overlay/instructions tag")


@router.post("/sdk/session/create")
async def sdk_session_create(req: SDKSessionCreateRequest):
    sid = req.session_id or str(uuid4())
    store.create_session(
        sid, active_agent_id=req.agent_name, scenario_id=req.scenario_id
    )
    try:
        payload = await asyncio.wait_for(
            sdk_manager.create_agent_session(
                session_id=sid,
                name=req.agent_name,
                instructions=req.instructions,
                model=req.model,
                scenario_id=req.scenario_id,
                overlay=req.overlay,
            ),
            timeout=6.0,
        )
        return payload
    except asyncio.TimeoutError:
        try:
            seq = store.next_seq(sid)
            store.append_event(
                sid,
                Event(
                    session_id=sid,
                    seq=seq,
                    type="log",
                    role="system",
                    agent_id=req.agent_name,
                    text="create_timeout",
                    final=True,
                    timestamp_ms=int(time.time() * 1000),
                ),
            )
        except Exception:
            pass
        return {
            "session_id": sid,
            "agent_name": req.agent_name,
            "model": req.model,
            "tools": [],
            "overlay": req.overlay,
        }
    except Exception as e:
        try:
            seq = store.next_seq(sid)
            store.append_event(
                sid,
                Event(
                    session_id=sid,
                    seq=seq,
                    type="log",
                    role="system",
                    agent_id=req.agent_name,
                    text=f"create_error: {e}",
                    final=True,
                    timestamp_ms=int(time.time() * 1000),
                ),
            )
        except Exception:
            pass
        return {
            "session_id": sid,
            "agent_name": req.agent_name,
            "model": req.model,
            "tools": [],
            "overlay": req.overlay,
        }


class SDKSessionDeleteRequest(BaseModel):
    session_id: str


@router.post("/sdk/session/delete")
async def sdk_session_delete(req: SDKSessionDeleteRequest):
    try:
        store.delete_session(req.session_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"delete failed: {e}")


# ---- SDK: Session Context ----
@router.get("/sdk/session/context")
async def sdk_session_get_context(session_id: str = Query(...)):
    try:
        return {
            "ok": True,
            "session_id": session_id,
            "context": store.get_context(session_id) or {},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"get context failed: {e}")


@router.post("/sdk/session/context")
async def sdk_session_set_context(session_id: str = Query(...), ctx: dict = Body(...)):
    try:
        store.set_context(session_id, ctx or {})
        return {
            "ok": True,
            "session_id": session_id,
            "context": store.get_context(session_id) or {},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"set context failed: {e}")


class SDKSessionMessageRequest(BaseModel):
    session_id: str
    user_input: str
    agent: dict | None = Field(
        None, description="Optional override of agent spec: name, instructions, model"
    )
    client_message_id: str | None = Field(
        None, description="Client idempotency key for this user message"
    )
    scenario_id: str | None = Field(
        None, description="Scenario binding for tools allowlist"
    )


@router.post("/sdk/session/message")
async def sdk_session_message(req: SDKSessionMessageRequest):
    if not req.user_input.strip():
        raise HTTPException(status_code=400, detail="user_input cannot be empty")
    agent_spec = req.agent or {}
    try:
        logger.info(
            "/sdk/session/message start sid=%s len=%s",
            req.session_id,
            len(req.user_input),
        )
        if req.client_message_id:
            prior = store.get_by_client_message_id(
                req.session_id, req.client_message_id
            )
            if prior:
                return {
                    "final_output": prior.text,
                    "new_items_len": 0,
                    "tool_calls": [],
                    "events": [prior.model_dump()],
                }
        if not store.get_session(req.session_id):
            store.create_session(
                req.session_id, active_agent_id=agent_spec.get("name", "assistant")
            )

        now_ms = int(time.time() * 1000)
        user_seq = store.next_seq(req.session_id)
        user_event = Event(
            session_id=req.session_id,
            seq=user_seq,
            type="message",
            message_id=req.client_message_id,
            role="user",
            agent_id=None,
            text=req.user_input,
            final=True,
            timestamp_ms=now_ms,
        )
        store.append_event(req.session_id, user_event)

        try:
            seq0 = store.next_seq(req.session_id)
            store.append_event(
                req.session_id,
                Event(
                    session_id=req.session_id,
                    seq=seq0,
                    type="log",
                    role="system",
                    agent_id=agent_spec.get("name", "Assistant"),
                    text="turn_start",
                    final=True,
                    timestamp_ms=int(time.time() * 1000),
                ),
            )
        except Exception:
            pass

        async def _sdk_path():
            return await sdk_manager.run_agent_turn(
                session_id=req.session_id,
                user_input=req.user_input,
                agent_spec=agent_spec,
                scenario_id=req.scenario_id,
            )

        try:
            result = await asyncio.wait_for(_sdk_path(), timeout=15.0)
        except asyncio.TimeoutError:
            try:
                seqt = store.next_seq(req.session_id)
                store.append_event(
                    req.session_id,
                    Event(
                        session_id=req.session_id,
                        seq=seqt,
                        type="log",
                        role="system",
                        agent_id=agent_spec.get("name", "Assistant"),
                        text="turn_timeout",
                        final=True,
                        timestamp_ms=int(time.time() * 1000),
                    ),
                )
            except Exception:
                pass
            result = {
                "final_output": "",
                "new_items_len": 0,
                "tool_calls": [],
                "used_tools": [],
                "usage": None,
                "used_fallback": False,
            }

        # No Responses fallback; if empty, we still append assistant event for visibility.

        if not (result.get("final_output") or "").strip():
            try:
                seqnt = store.next_seq(req.session_id)
                store.append_event(
                    req.session_id,
                    Event(
                        session_id=req.session_id,
                        seq=seqnt,
                        type="log",
                        role="system",
                        agent_id=agent_spec.get("name", "Assistant"),
                        text="assistant_no_text",
                        final=True,
                        timestamp_ms=int(time.time() * 1000),
                    ),
                )
            except Exception:
                pass

        message_id = req.client_message_id or str(uuid4())
        seq = store.next_seq(req.session_id)
        asst_event = Event(
            session_id=req.session_id,
            seq=seq,
            type="message",
            message_id=message_id,
            role="assistant",
            agent_id=agent_spec.get("name", "Assistant"),
            text=result.get("final_output") or "",
            final=True,
            timestamp_ms=int(time.time() * 1000),
        )
        store.append_event(req.session_id, asst_event)
        if req.client_message_id:
            store.remember_client_message(
                req.session_id, req.client_message_id, asst_event
            )

        try:
            seq1 = store.next_seq(req.session_id)
            store.append_event(
                req.session_id,
                Event(
                    session_id=req.session_id,
                    seq=seq1,
                    type="log",
                    role="system",
                    agent_id=agent_spec.get("name", "Assistant"),
                    text="turn_end",
                    final=True,
                    timestamp_ms=int(time.time() * 1000),
                ),
            )
        except Exception:
            pass
        return {**result, "events": [user_event.model_dump(), asst_event.model_dump()]}
    except Exception as e:
        logger.exception("/sdk/session/message error: %s", e)
        try:
            seqe = store.next_seq(req.session_id)
            store.append_event(
                req.session_id,
                Event(
                    session_id=req.session_id,
                    seq=seqe,
                    type="log",
                    role="system",
                    agent_id=agent_spec.get("name", "Assistant"),
                    text=f"turn_error: {e}",
                    final=True,
                    timestamp_ms=int(time.time() * 1000),
                ),
            )
            seq2 = store.next_seq(req.session_id)
            store.append_event(
                req.session_id,
                Event(
                    session_id=req.session_id,
                    seq=seq2,
                    type="message",
                    role="assistant",
                    agent_id=agent_spec.get("name", "Assistant"),
                    text="",
                    final=True,
                    message_id=req.client_message_id or str(uuid4()),
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
            "used_fallback": False,
            "events": [],
        }


# ---- SDK: Set Active Agent ----
class SetActiveAgentRequest(BaseModel):
    session_id: str
    agent_name: str


@router.post("/sdk/session/set_active_agent")
async def set_active_agent(req: SetActiveAgentRequest):
    try:
        store.set_active_agent(req.session_id, req.agent_name)
        seq = store.next_seq(req.session_id)
        ev = Event(
            session_id=req.session_id,
            seq=seq,
            type="handoff",
            role="system",
            agent_id=req.agent_name,
            text=None,
            final=True,
            reason="manual_switch",
            timestamp_ms=int(time.time() * 1000),
        )
        store.append_event(req.session_id, ev)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"set_active_agent failed: {e}")


# ---- SDK: Transcript ----
@router.get("/sdk/session/transcript")
async def sdk_session_transcript(session_id: str):
    try:
        return await sdk_manager.get_session_transcript(session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"transcript retrieval failed: {e}")


# ---- SDK: Usage ----
class UsageResponse(BaseModel):
    requests: int
    input_tokens: int
    output_tokens: int
    total_tokens: int


@router.get("/sdk/session/usage", response_model=UsageResponse)
async def get_session_usage(session_id: str = Query(...)):
    try:
        u = store.get_usage(session_id)
        return UsageResponse(**u)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"usage retrieval failed: {e}")


# ---- SDK: Events + SSE ----
@router.get("/sdk/session/{session_id}/events")
async def list_session_events(session_id: str, since: int | None = Query(None)):
    try:
        events = store.list_events(session_id, since_seq=since)
        return [e.model_dump() for e in events]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"events retrieval failed: {e}")


@router.get("/sdk/session/{session_id}/stream")
async def stream_sdk_session_events(session_id: str, since: int | None = Query(None)):
    async def event_gen():
        last = since or 0
        try:
            while True:
                evs = store.list_events(session_id, since_seq=last)
                if evs:
                    for ev in evs:
                        last = max(last, ev.seq)
                        yield f"data: {ev.model_dump()}\n\n"
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            return

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# ---- SDK: Audio ingestion (placeholder) ----
class AudioChunkRequest(BaseModel):
    session_id: str
    seq: int
    pcm16_base64: str = Field(
        ..., description="Little-endian 16-bit PCM mono @16k base64 encoded"
    )
    sample_rate: int = 16000
    frame_samples: int | None = None


@router.post("/sdk/session/audio")
async def sdk_session_audio(req: AudioChunkRequest):
    try:
        raw = base64.b64decode(req.pcm16_base64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64")
    if len(raw) % 2 != 0:
        raise HTTPException(status_code=400, detail="PCM byte length not even")
    sample_count = len(raw) // 2
    return {
        "accepted": True,
        "session_id": req.session_id,
        "seq": req.seq,
        "samples": sample_count,
        "sample_rate": req.sample_rate,
        "ts": time.time(),
    }


# ---- SDK: Agent visualization ----
class VizRequest(BaseModel):
    scenario_id: str = Field(...)
    root_agent: str | None = Field(None, description="Optional root agent name for viz")
    filename: str | None = Field(
        None, description="Optional file base name to save on server"
    )
    return_dot: bool = Field(
        False,
        description="If true, include DOT source in response (no Graphviz needed)",
    )


@router.post("/sdk/agents/visualize")
async def visualize_agents(req: VizRequest):
    try:
        root, mapping = sdk_manager.build_agent_network_for_viz(
            req.scenario_id, root_agent=req.root_agent
        )
        if not root:
            # Return ok:false with a helpful message rather than 400 to avoid noisy UI errors
            return JSONResponse(
                {
                    "ok": False,
                    "error": "No scenario/agents to visualize",
                    "scenario_id": req.scenario_id,
                },
                status_code=200,
            )
        try:
            from agents.extensions.visualization import \
                draw_graph  # type: ignore
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"viz unavailable: {e}")

        # Helper: attempt to ensure Graphviz 'dot' is discoverable on Windows/conda
        def _ensure_dot_available() -> str | None:
            try:
                import os
                import shutil

                # If already on PATH or GRAPHVIZ_DOT is set and exists, we're good
                if shutil.which("dot"):
                    return None
                dot_env = os.environ.get("GRAPHVIZ_DOT")
                if dot_env and os.path.exists(dot_env):
                    return dot_env
                # Try conda prefix locations
                conda = os.environ.get("CONDA_PREFIX")
                candidates: list[str] = []
                if conda:
                    candidates.extend(
                        [
                            os.path.join(conda, "Library", "bin", "dot.exe"),
                            os.path.join(
                                conda, "Library", "bin", "graphviz", "dot.exe"
                            ),
                            os.path.join(conda, "bin", "dot"),
                        ]
                    )
                # Common Windows installs
                candidates.extend(
                    [
                        r"C:\\Program Files\\Graphviz\\bin\\dot.exe",
                        r"C:\\Program Files (x86)\\Graphviz2.38\\bin\\dot.exe",
                    ]
                )
                for p in candidates:
                    if os.path.exists(p):
                        os.environ["GRAPHVIZ_DOT"] = p
                        return p
            except Exception:
                return None
            return None

        _ensure_dot_available()

        # draw_graph returns a graphviz.Digraph
        g = draw_graph(root)
        # If explicitly requested, include DOT source (doesn't require Graphviz binaries)
        if getattr(req, "return_dot", False):
            try:
                dot_src = getattr(g, "source", None)
                if not isinstance(dot_src, str):
                    dot_src = str(g)
            except Exception:
                dot_src = None
            # Continue with PNG path too if available; frontend can prefer DOT if needed
            # but at least the caller gets the DOT to verify/inspect elsewhere.
            dot_payload = {"dot_source": dot_src}
        else:
            dot_payload = {}
        # Graphviz Digraph has .pipe to get bytes when format is set
        try:
            g.format = "png"  # type: ignore[attr-defined]
            png_bytes = g.pipe(format="png")  # type: ignore[call-arg]
            payload = base64.b64encode(png_bytes).decode("ascii")
            return JSONResponse(
                {
                    "ok": True,
                    "format": "png",
                    "image_base64": payload,
                    **dot_payload,
                }
            )
        except Exception as e1:
            # Fallback: try saving to a temp file and re-open
            fname = (req.filename or "agent_graph") + ".png"
            try:
                g.render(filename=req.filename or "agent_graph", format="png", cleanup=True)  # type: ignore[call-arg]
            except Exception as e2:
                # Write DOT source to a safe path for troubleshooting (usually missing Graphviz system binaries)
                try:
                    import os
                    from uuid import uuid4 as _uuid4

                    backend_dir = os.path.dirname(os.path.dirname(__file__))
                    out_root = os.path.join(backend_dir, "agent_graph_out")
                    # If a file exists with this name, fallback to backend_dir
                    if os.path.exists(out_root) and not os.path.isdir(out_root):
                        out_root = backend_dir
                    os.makedirs(out_root, exist_ok=True)
                    dot_path = os.path.join(out_root, f"agent_graph_{_uuid4().hex}.dot")
                    # graphviz.Digraph exposes 'source'
                    dot_src = getattr(g, "source", None)
                    if not isinstance(dot_src, str):
                        try:
                            dot_src = str(g)
                        except Exception:
                            dot_src = "// (no source available)"
                    with open(dot_path, "w", encoding="utf-8") as f:
                        f.write(dot_src or "")
                    # Try to include discovered dot path in hint
                    dot_hint = os.environ.get("GRAPHVIZ_DOT") or "dot (not found)"
                    hint = (
                        f"viz render failed: {e2}; wrote DOT to {dot_path}. "
                        f"Set GRAPHVIZ_DOT to a valid dot.exe or install Graphviz and add it to PATH. Using: {dot_hint}"
                    )
                except Exception as ewrite:
                    hint = f"viz render failed: {e2}; additionally failed to write DOT: {ewrite}"
                return JSONResponse(
                    {"ok": False, "error": hint},
                    status_code=200,
                )
            try:
                with open(fname, "rb") as f:
                    payload = base64.b64encode(f.read()).decode("ascii")
                return JSONResponse(
                    {
                        "ok": True,
                        "format": "png",
                        "image_base64": payload,
                        **dot_payload,
                    }
                )
            except Exception as e3:
                return JSONResponse(
                    {"ok": False, "error": f"viz read failed: {e3}"},
                    status_code=200,
                )
    except HTTPException:
        raise
    except Exception as e:
        # Return ok:false as JSON to help the UI
        return JSONResponse(
            {"ok": False, "error": f"visualize failed: {e}"}, status_code=200
        )
