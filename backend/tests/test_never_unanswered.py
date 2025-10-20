import asyncio

import httpx
import pytest

BASE_URL = "http://localhost:8000"


@pytest.mark.asyncio
async def test_never_unanswered_final_output_not_empty():
    async with httpx.AsyncClient(timeout=10) as client:
        # Create session without scenario to hit default path
        r = await client.post(
            f"{BASE_URL}/api/sdk/session/create", json={"instructions": "Be terse."}
        )
        assert r.status_code == 200, r.text
        sid = r.json()["session_id"]

        # Send message that's unlikely to produce output if things go wrong
        r2 = await client.post(
            f"{BASE_URL}/api/sdk/session/message",
            json={"session_id": sid, "user_input": "Ping"},
        )
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert "final_output" in data
        assert isinstance(data["final_output"], str)
        assert len(data["final_output"].strip()) >= 1
