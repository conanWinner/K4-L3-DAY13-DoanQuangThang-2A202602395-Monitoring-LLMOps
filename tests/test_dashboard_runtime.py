from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.dashboard import render_dashboard, summarize_logs


def test_dashboard_aggregates_recent_log_events(tmp_path: Path) -> None:
    now = datetime(2026, 9, 30, 3, 40, tzinfo=timezone.utc)
    recent = (now - timedelta(seconds=30)).isoformat()
    old = (now - timedelta(hours=2)).isoformat()
    records = [
        {"ts": old, "event": "request_received"},
        {"ts": recent, "event": "request_received"},
        {"ts": recent, "event": "response_sent", "latency_ms": 1200, "ttft_ms": 80,
         "cost_usd": 0.02, "tokens_in": 20, "tokens_out": 100, "quality_score": 0.8,
         "tool_name": "retrieval", "tool_success": True},
        {"ts": recent, "event": "request_received"},
        {"ts": recent, "event": "request_failed", "error_type": "RuntimeError",
         "tool_name": "retrieval", "tool_success": False},
    ]
    path = tmp_path / "logs.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    summary = summarize_logs(path, now=now)
    assert summary["requests"] == 2
    assert summary["latency_p95"] == 1200
    assert summary["ttft_p95"] == 80
    assert summary["error_rate_pct"] == 50
    assert summary["retrieval_success_pct"] == 50
    assert summary["error_breakdown"] == {"RuntimeError": 1}
    assert summary["tokens_in"] == 20 and summary["tokens_out"] == 100
    assert summary["quality_mean"] == 0.8
    assert summary["slo_good_pct"] == 50

    page = render_dashboard(log_path=path, now=now)
    assert page.count('<section class="panel">') == 6
    assert "TTFT P95" in page
    assert "Retrieval success 50.0%" in page
    assert "data/logs.jsonl" in page
