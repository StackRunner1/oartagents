import asyncio

import httpx
import pytest

BASE_URL = "http://localhost:8000"


@pytest.mark.asyncio
async def test_handoff_override_emits_event():
    async with httpx.AsyncClient(timeout=10) as client:
        # Create session
        r = await client.post(
            f"{BASE_URL}/api/sdk/session/create",
            json={"instructions": "Be terse.", "scenario_id": "default"},
        )
        assert r.status_code == 200, r.text
        sid = r.json()["session_id"]

        # Apply override to sales
        r2 = await client.post(
            f"{BASE_URL}/api/sdk/session/set_active_agent",
            json={"session_id": sid, "agent_name": "sales"},
        )
        assert r2.status_code == 200, r2.text

        # Fetch events and assert handoff_override exists
        r3 = await client.get(f"{BASE_URL}/api/sdk/session/{sid}/events")
        assert r3.status_code == 200, r3.text
        events = r3.json()
        assert any(
            e.get("type") == "handoff_override" and e.get("agent_id") == "sales"
            for e in events
        )
