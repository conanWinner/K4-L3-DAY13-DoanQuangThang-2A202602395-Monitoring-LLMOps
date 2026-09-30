from __future__ import annotations

import json
import asyncio
from pathlib import Path

import httpx

from app import logging_config
from app.main import app
from app.pii import hash_user_id


def test_chat_response_log_exposes_quality_for_dashboard(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": "Explain observability",
                },
            )

    response = asyncio.run(send_request())

    assert response.status_code == 200
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    response_event = next(event for event in events if event["event"] == "response_sent")
    assert response_event["quality_score"] == response.json()["quality_score"]
    assert response_event["ttft_ms"] == response.json()["ttft_ms"]
    assert response_event["tool_name"] == "retrieval"
    assert response_event["tool_success"] is True


def test_request_ids_context_and_pii_are_safe_across_requests(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_requests() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "user_id": "student-01",
                "session_id": "student@vinuni.edu.vn",
                "feature": "qa",
                "message": "Please call 0901234567 about monitoring",
            }
            supplied = await client.post(
                "/chat", json=payload, headers={"x-request-id": "req-deadbeef"}
            )
            generated = await client.post(
                "/chat",
                json={**payload, "session_id": "session-02"},
                headers={"x-request-id": "invalid"},
            )
            another = await client.post(
                "/chat", json={**payload, "session_id": "session-03"}
            )
            return [supplied, generated, another]

    responses = asyncio.run(send_requests())
    ids = [response.headers["x-request-id"] for response in responses]
    assert ids[0] == "req-deadbeef"
    assert len(set(ids)) == 3
    assert all(response.status_code == 200 for response in responses)
    assert all(response.json()["correlation_id"] == cid for response, cid in zip(responses, ids))
    assert all(float(response.headers["x-response-time-ms"]) >= 0 for response in responses)

    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    assert len(events) == 6
    assert [event["correlation_id"] for event in events] == [cid for cid in ids for _ in range(2)]
    assert all(event["user_id_hash"] == hash_user_id("student-01") for event in events)
    assert all(event["feature"] == "qa" and event["model"] and event["env"] for event in events)
    assert events[0]["session_id"] == "[REDACTED_EMAIL]"
    assert events[2]["session_id"] == "session-02"
    rendered_logs = log_path.read_text(encoding="utf-8")
    assert "student@vinuni.edu.vn" not in rendered_logs
    assert "0901234567" not in rendered_logs
