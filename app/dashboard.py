"""Live six-panel dashboard backed by the structured JSONL log."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from statistics import mean

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "dashboard.yaml"


def _percentile(values: list[float], percent: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percent / 100) - 1)]


def _number(record: dict, field: str) -> float | None:
    value = record.get(field)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def summarize_logs(
    path: Path, *, now: datetime, minutes: int = 60
) -> dict:
    since = now - timedelta(minutes=minutes)
    records: list[dict] = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
                timestamp = datetime.fromisoformat(record["ts"].replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                if since <= timestamp <= now:
                    record["_timestamp"] = timestamp
                    records.append(record)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue

    requests = [r for r in records if r.get("event") == "request_received"]
    responses = [r for r in records if r.get("event") == "response_sent"]
    failures = [r for r in records if r.get("event") == "request_failed"]
    attempts = [
        r for r in records
        if r.get("tool_name") == "retrieval" and isinstance(r.get("tool_success"), bool)
    ]
    latencies = [v for r in responses if (v := _number(r, "latency_ms")) is not None]
    ttfts = [v for r in responses if (v := _number(r, "ttft_ms")) is not None]
    costs = [v for r in responses if (v := _number(r, "cost_usd")) is not None]
    qualities = [v for r in responses if (v := _number(r, "quality_score")) is not None]
    tokens_in = sum(_number(r, "tokens_in") or 0 for r in responses)
    tokens_out = sum(_number(r, "tokens_out") or 0 for r in responses)

    buckets: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        buckets[record["_timestamp"].strftime("%Y-%m-%dT%H:%MZ")].append(record)
    keys = [
        (now.replace(second=0, microsecond=0) - timedelta(minutes=offset)).strftime("%Y-%m-%dT%H:%MZ")
        for offset in range(minutes - 1, -1, -1)
    ]
    traffic_series: list[float] = []
    latency_series: list[float | None] = []
    errors_series: list[float | None] = []
    cost_series: list[float] = []
    tokens_series: list[float] = []
    quality_series: list[float | None] = []
    cumulative_cost = 0.0
    cumulative_tokens = 0.0
    for key in keys:
        bucket = buckets[key]
        received = [r for r in bucket if r.get("event") == "request_received"]
        sent = [r for r in bucket if r.get("event") == "response_sent"]
        failed = [r for r in bucket if r.get("event") == "request_failed"]
        bucket_latency = [v for r in sent if (v := _number(r, "latency_ms")) is not None]
        bucket_quality = [v for r in sent if (v := _number(r, "quality_score")) is not None]
        cumulative_cost += sum(_number(r, "cost_usd") or 0 for r in sent)
        cumulative_tokens += sum(
            (_number(r, "tokens_in") or 0) + (_number(r, "tokens_out") or 0)
            for r in sent
        )
        traffic_series.append(float(len(received)))
        latency_series.append(_percentile(bucket_latency, 95) if bucket_latency else None)
        errors_series.append(len(failed) / len(received) * 100 if received else None)
        cost_series.append(cumulative_cost)
        tokens_series.append(cumulative_tokens)
        quality_series.append(mean(bucket_quality) if bucket_quality else None)

    good_responses = sum(
        latency is not None and latency <= 3000
        for record in responses
        if (latency := _number(record, "latency_ms")) is not None
    )

    return {
        "since": since,
        "now": now,
        "requests": len(requests),
        "responses": len(responses),
        "latency_p50": _percentile(latencies, 50),
        "latency_p95": _percentile(latencies, 95),
        "latency_p99": _percentile(latencies, 99),
        "ttft_p95": _percentile(ttfts, 95),
        "traffic_last_minute": sum(r["_timestamp"] >= now - timedelta(minutes=1) for r in requests),
        "error_rate_pct": len(failures) / len(requests) * 100 if requests else 0.0,
        "error_breakdown": dict(Counter(str(r.get("error_type") or "unknown") for r in failures)),
        "retrieval_success_pct": sum(r["tool_success"] for r in attempts) / len(attempts) * 100 if attempts else 0.0,
        "retrieval_attempts": len(attempts),
        "cost_total": sum(costs),
        "tokens_in": int(tokens_in),
        "tokens_out": int(tokens_out),
        "quality_mean": mean(qualities) if qualities else 0.0,
        "slo_good_pct": good_responses / len(requests) * 100 if requests else 0.0,
        "series": {
            "latency": latency_series,
            "traffic": traffic_series,
            "errors": errors_series,
            "cost": cost_series,
            "tokens": tokens_series,
            "quality": quality_series,
        },
    }


def _chart(values: list[float | None], threshold: float, color: str) -> str:
    values = values[-20:]
    if not values:
        values = [None]
    present = [(index, value) for index, value in enumerate(values) if value is not None]
    maximum = max([threshold, 0.001] + [value for _, value in present]) * 1.1
    width, height = 320, 76
    points = " ".join(
        f"{index * width / max(1, len(values) - 1):.1f},{height - value / maximum * height:.1f}"
        for index, value in present
    )
    threshold_y = height - threshold / maximum * height
    line = f'<polyline fill="none" stroke="{color}" stroke-width="3" points="{points}" />' if len(present) > 1 else ""
    dots = "".join(
        f'<circle cx="{index * width / max(1, len(values) - 1):.1f}" cy="{height - value / maximum * height:.1f}" r="2.5" fill="{color}" />'
        for index, value in present
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Xu hướng 20 phút gần nhất">'
        f'<line x1="0" y1="{threshold_y:.1f}" x2="{width}" y2="{threshold_y:.1f}" stroke="#e67763" stroke-dasharray="5 4" />'
        f'{line}{dots}'
        '</svg>'
    )


def render_dashboard(
    *, config_path: Path = CONFIG_PATH, log_path: Path | None = None, now: datetime | None = None
) -> str:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["dashboard"]
    if log_path is None:
        log_path = ROOT / config["panels"][0]["source"]
    now = now or datetime.now(timezone.utc)
    summary = summarize_logs(log_path, now=now, minutes=config["time_range_minutes"])
    values = {
        "latency": (f'{summary["latency_p95"]:,.0f}', f'P50 {summary["latency_p50"]:,.0f} · P99 {summary["latency_p99"]:,.0f} · TTFT P95 {summary["ttft_p95"]:,.0f} ms', summary["latency_p95"]),
        "traffic": (f'{summary["traffic_last_minute"]:,.0f}', f'{summary["requests"]} request trong 60 phút', summary["traffic_last_minute"]),
        "errors": (f'{summary["error_rate_pct"]:.1f}', f'Retrieval success {summary["retrieval_success_pct"]:.1f}% ({summary["retrieval_attempts"]} lượt) · Lỗi: {summary["error_breakdown"] or "0"}', summary["error_rate_pct"]),
        "cost": (f'{summary["cost_total"]:.4f}', 'Tổng chi phí 60 phút', summary["cost_total"]),
        "tokens": (f'{summary["tokens_in"] + summary["tokens_out"]:,}', f'Input {summary["tokens_in"]:,} · Output {summary["tokens_out"]:,}', summary["tokens_in"] + summary["tokens_out"]),
        "quality": (f'{summary["quality_mean"]:.2f}', f'{summary["responses"]} phản hồi · SLO tốt {summary["slo_good_pct"]:.1f}%', summary["quality_mean"]),
    }
    colors = {"latency": "#40b9a9", "traffic": "#6596e6", "errors": "#e9a05a", "cost": "#ae8de4", "tokens": "#e1b95a", "quality": "#60b882"}
    cards = []
    for panel in config["panels"]:
        panel_id = panel["id"]
        main, detail, actual = values[panel_id]
        threshold = panel["threshold"]
        limit = float(threshold["value"])
        healthy = actual <= limit if threshold["operator"] == "lte" else actual >= limit
        status = "Đạt ngưỡng" if healthy else "Vượt ngưỡng"
        symbol = "≤" if threshold["operator"] == "lte" else "≥"
        cards.append(
            '<section class="panel">'
            f'<div class="eyebrow">{escape(panel_id.upper())} <span class="status {"ok" if healthy else "bad"}">{status}</span></div>'
            f'<h2>{escape(panel["title"])}</h2>'
            f'<div class="value">{escape(main)} <small>{escape(panel["unit"])}</small></div>'
            f'<p>{escape(detail)}</p>'
            f'{_chart(summary["series"][panel_id], limit, colors[panel_id])}'
            f'<div class="threshold">Ngưỡng {escape(threshold["aggregation"])} {symbol} {limit:g} {escape(panel["unit"])} · đường gạch đỏ</div>'
            '</section>'
        )
    title = escape(config["title"])
    interval = int(config["refresh_seconds"])
    return f'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="{interval}"><title>{title} · Dashboard</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, system-ui, sans-serif; background:#0e1521; color:#edf3f7 }}
* {{ box-sizing:border-box }} body {{ margin:0; padding:24px; max-width:1500px; margin-inline:auto }}
header {{ display:flex; justify-content:space-between; gap:18px; align-items:end; margin-bottom:22px }}
h1 {{ margin:0; font-size:27px; letter-spacing:-.03em }} .subtitle {{ color:#9caec0; margin:8px 0 0; font-size:13px }}
.meta {{ color:#a9bacb; font-size:13px; text-align:right; line-height:1.7 }}
.grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px }}
.panel {{ min-height:285px; padding:20px; border:1px solid #28384c; border-radius:16px; background:linear-gradient(145deg,#192638,#14202f) }}
.eyebrow {{ color:#86a4bb; font-size:11px; font-weight:750; letter-spacing:.13em; display:flex; justify-content:space-between; align-items:center }}
.status {{ letter-spacing:0; font-size:11px; padding:5px 8px; border-radius:20px }} .ok {{ color:#a9efcf; background:#214b3c }} .bad {{ color:#ffd1bb; background:#663a36 }}
h2 {{ margin:12px 0 10px; font-size:17px; font-weight:650 }} .value {{ font-size:32px; font-weight:760; line-height:1.15 }}
.value small {{ font-size:12px; font-weight:500; color:#a3b7c8 }} p {{ color:#afbfcd; font-size:12px; height:30px; margin:8px 0 12px }}
svg {{ width:100%; height:68px; overflow:visible }} .threshold {{ color:#8399ab; font-size:11px; margin-top:9px }}
footer {{ color:#8fa5b9; font-size:12px; margin-top:16px }}
@media(max-width:1000px) {{ .grid {{ grid-template-columns:repeat(2,minmax(0,1fr)) }} }}
@media(max-width:650px) {{ header {{ display:block }} .meta {{ text-align:left; margin-top:8px }} .grid {{ grid-template-columns:1fr }} }}
</style></head><body>
<header><div><h1>{title}</h1><p class="subtitle">6 panel · nguồn dữ liệu: data/logs.jsonl · Metrics → Logs → Traces</p></div>
<div class="meta">Khoảng thời gian: {summary["since"].strftime("%d/%m/%Y %H:%M")}–{summary["now"].strftime("%H:%M UTC")}<br>Tự cập nhật mỗi {interval} giây · {summary["requests"]} request</div></header>
<main class="grid">{''.join(cards)}</main>
<footer>Đường biểu đồ: 20 phút gần nhất. Giá trị chính và ngưỡng lấy từ config/dashboard.yaml; dashboard đọc lại log mỗi lần tải trang.</footer>
</body></html>'''
