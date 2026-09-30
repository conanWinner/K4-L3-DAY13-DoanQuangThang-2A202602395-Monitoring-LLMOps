"""Send one fixed CP2 input under a selected Langfuse prompt label."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INPUT = "Explain why metrics, logs and traces work together"


async def send_request(request_id: str) -> httpx.Response:
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cp2-local") as client:
        return await client.post(
            "/chat",
            json={
                "user_id": "cp2-test-user",
                "session_id": f"cp2-{request_id}",
                "feature": "qa",
                "message": INPUT,
            },
            headers={"x-request-id": request_id},
            timeout=30,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("label", choices=("baseline", "candidate", "production"))
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    os.environ["LANGFUSE_PROMPT_LABEL"] = args.label
    from langfuse import get_client

    managed_prompt = get_client().get_prompt(
        os.environ.get("LANGFUSE_PROMPT_NAME", "day13-chat"),
        label=args.label,
        cache_ttl_seconds=60,
        fetch_timeout_seconds=10,
        max_retries=1,
    )
    if getattr(managed_prompt, "is_fallback", False):
        raise SystemExit(f"Prompt label {args.label} returned a fallback")
    request_id = f"req-{uuid.uuid4().hex[:8]}"

    response = asyncio.run(send_request(request_id))
    get_client().flush()
    if response.status_code != 200:
        raise SystemExit(f"HTTP {response.status_code}: prompt probe failed")
    if response.json()["correlation_id"] != request_id:
        raise SystemExit("Correlation ID mismatch")
    print(
        f"label={args.label} version={managed_prompt.version} "
        f"correlation_id={request_id} status={response.status_code}"
    )


if __name__ == "__main__":
    main()
