"""Export CP3 metric, log, and trace evidence from the completed local run.

The report contains only challenge metadata and sanitized application output.
It never copies challenge queries or Langfuse credentials into evidence.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from statistics import mean

from dotenv import load_dotenv
from langfuse import get_client

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "submission/evidence"
RUN = EVIDENCE / "12-incident-run.txt"
FIELDS = "core,basic,time,metadata,usage,prompt,trace_context,model"
PROJECT = "day13-k4-l3b-2A202602395"


def percentile(values: list[float], percent: int) -> float:
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * percent / 100) - 1]


def phase_ids(run: str, heading: str) -> list[str]:
    section = run.split(f"\n{heading}\n", 1)[1].split("\n\n", 1)[0]
    ids = re.findall(r"^\[200\] (req-[0-9a-f]{8}) \|", section, re.M)
    assert len(ids) == 5 and len(set(ids)) == 5, (heading, ids)
    return ids


def client_latencies(run: str, heading: str) -> list[float]:
    section = run.split(f"\n{heading}\n", 1)[1].split("\n\n", 1)[0]
    values = [float(value) for value in re.findall(r"^\[200\] req-[0-9a-f]{8} \| monitoring \| ([\d.]+)ms$", section, re.M)]
    assert len(values) == 5
    return values


def page(title: str, subtitle: str, body: str, source: str) -> str:
    return f'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box }} body {{ margin:0; padding:34px 42px; width:1440px; height:900px; overflow:hidden; background:#0e1521; color:#eaf2f7; font:17px system-ui,sans-serif }}
h1 {{ margin:6px 0 10px; font-size:34px }} .eyebrow {{ color:#7ac6bc; font-size:14px; font-weight:700; letter-spacing:.12em }}
.sub {{ color:#acc1d1; margin-bottom:24px; font-size:16px }} .card {{ background:#17283b; border:1px solid #31495c; border-radius:14px; padding:21px 24px; margin:14px 0 }}
table {{ width:100%; border-collapse:collapse; font-size:17px }} th {{ color:#8fc5d2; text-align:left; font-size:14px; text-transform:uppercase }} th,td {{ padding:12px 10px; border-bottom:1px solid #355064; vertical-align:top }}
code,pre {{ font:16px ui-monospace,SFMono-Regular,monospace; color:#b4ead6 }} pre {{ white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.55 }}
.bad {{ color:#ffb080; font-weight:700 }} .good {{ color:#a0ddb7 }} .bar {{ height:25px; background:#243e52; border-radius:5px; position:relative }}
.fill {{ position:absolute; height:25px; background:#6cbdb5; border-radius:5px }} footer {{ color:#8ca9bb; font-size:14px; margin-top:18px }}
</style></head><body><div class="eyebrow">CP3 · CHALLENGE {escape(subtitle)}</div><h1>{escape(title)}</h1>
{body}<footer>Nguồn: {escape(source)}. Ảnh kết xuất từ dữ liệu thật; không phải ảnh chụp giao diện Langfuse.</footer></body></html>'''


def table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{escape(value)}</th>" for value in headers)
    content = "".join("<tr>" + "".join(f"<td>{escape(value)}</td>" for value in row) + "</tr>" for row in rows)
    return f'<div class="card"><table><thead><tr>{head}</tr></thead><tbody>{content}</tbody></table></div>'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path, default=EVIDENCE,
        help="Empty directory for new evidence; existing files are never overwritten.",
    )
    args = parser.parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    run = RUN.read_text(encoding="utf-8")
    challenge_id = re.search(r"^Challenge ID: (.+)$", run, re.M).group(1)
    seed = int(re.search(r"^Seed: (\d+)$", run, re.M).group(1))
    threshold = int(re.search(r"^Latency threshold: (\d+) ms$", run, re.M).group(1))
    baseline_ids = phase_ids(run, "baseline_without_incident")
    incident_ids = phase_ids(run, "incident_workload")
    ids = set(baseline_ids + incident_ids)
    start = datetime.fromisoformat(re.search(r"^baseline_start_utc: (.+)$", run, re.M).group(1))
    end = datetime.fromisoformat(re.search(r"^incident_end_utc: (.+)$", run, re.M).group(1))
    incident_start = datetime.fromisoformat(re.search(r"^incident_start_utc: (.+)$", run, re.M).group(1))
    assert re.search(r"\nincident_disable\n200 .*'rag_slow': False", run)
    assert "Cohort: K4" in run and "Queries: 5" in run

    logs = {}
    line_numbers = {}
    for number, line in enumerate((ROOT / "data/logs.jsonl").read_text(encoding="utf-8").splitlines(), 1):
        record = json.loads(line)
        rid = record.get("correlation_id")
        if rid in ids and record.get("event") == "response_sent":
            assert rid not in logs
            logs[rid] = record
            line_numbers[rid] = number
    assert set(logs) == ids
    assert all(logs[rid]["feature"] == "monitoring" for rid in ids)
    baseline = [float(logs[rid]["latency_ms"]) for rid in baseline_ids]
    incident = [float(logs[rid]["latency_ms"]) for rid in incident_ids]
    assert all(value > threshold for value in incident)
    assert all(logs[rid]["tool_success"] for rid in ids)

    load_dotenv(ROOT / ".env")
    client = get_client()
    projects = client.api.projects.get().data
    assert len(projects) == 1 and projects[0].name == PROJECT
    observations = []
    cursor = None
    for _ in range(5):
        result = client.api.observations.get_many(
            limit=100, cursor=cursor, fields=FIELDS,
            from_start_time=start - timedelta(seconds=2),
            to_start_time=end + timedelta(seconds=2),
        )
        observations.extend(result.data)
        cursor = result.meta.cursor
        if not cursor:
            break
    by_id = {}
    for observation in observations:
        rid = (observation.metadata or {}).get("correlation_id")
        if rid in ids:
            by_id.setdefault(rid, []).append(observation)
    assert set(by_id) == ids
    for rid, items in by_id.items():
        assert {item.name for item in items} == {"lab-agent-run", "retrieval", "generation"}, rid
        assert len({item.trace_id for item in items}) == 1

    target_id = incident_ids[0]
    target_log = logs[target_id]
    line_number = line_numbers[target_id]
    public_log = json.dumps(
        {key: target_log[key] for key in (
            "ts", "level", "event", "correlation_id", "feature", "model", "env",
            "latency_ms", "ttft_ms", "tool_name", "tool_success",
            "tokens_in", "tokens_out", "cost_usd",
        )},
        ensure_ascii=False,
    )
    target_obs = {item.name: item for item in by_id[target_id]}
    root, retrieval, generation = (target_obs[name] for name in ("lab-agent-run", "retrieval", "generation"))
    assert retrieval.parent_observation_id == root.id
    assert generation.parent_observation_id == root.id
    assert 2.4 <= retrieval.latency <= 2.7 and generation.latency < 0.3
    assert root.trace_id == retrieval.trace_id == generation.trace_id
    baseline_retrieval = [next(item for item in by_id[rid] if item.name == "retrieval").latency * 1000 for rid in baseline_ids]
    incident_retrieval = [next(item for item in by_id[rid] if item.name == "retrieval").latency * 1000 for rid in incident_ids]

    interval = f'{incident_start:%Y-%m-%d %H:%M:%S}–{end:%H:%M:%S} UTC'
    subtitle = f'{challenge_id} · seed {seed}'
    metric_rows = [
        ["Số request", "5", "5"],
        ["App latency P95", f"{percentile(baseline,95):,.0f} ms", f"{percentile(incident,95):,.0f} ms"],
        ["Client latency P95", f"{percentile(client_latencies(run,'baseline_without_incident'),95):,.1f} ms", f"{percentile(client_latencies(run,'incident_workload'),95):,.1f} ms"],
        ["Retrieval trung bình (trace)", f"{mean(baseline_retrieval):,.0f} ms", f"{mean(incident_retrieval):,.0f} ms"],
        [f"App latency > {threshold:,} ms", f"{sum(v>threshold for v in baseline)}/5", f"{sum(v>threshold for v in incident)}/5"],
        ["HTTP error / retrieval fail", "0 / 0", "0 / 0"],
    ]
    metric_body = f'<div class="card">Feature: <code>monitoring</code> · Sự cố: <code>{escape(interval)}</code> · Ngưỡng challenge: <span class="bad">{threshold:,} ms</span><br>Baseline: {start:%Y-%m-%d %H:%M:%S}–{incident_start:%H:%M:%S} UTC · nguồn latency: log <code>response_sent</code></div>'
    metric_body += table(["Metric", "Đối chứng", "Khi bật sự cố"], metric_rows)
    metric_body += '<div class="card">P95 tính theo nearest-rank, đúng cách tính của dashboard. Client latency đo tại <code>scripts/load_test.py</code>; app latency lấy từ structured log. Hai số đo có ranh giới khác nhau.</div>'

    log_body = f'<div class="card">Khoảng sự cố: <code>{escape(interval)}</code> · file <code>data/logs.jsonl:{line_number}</code><br>Correlation ID: <code>{target_id}</code> · trace khớp: <code>{root.trace_id}</code></div>'
    log_body += f'<div class="card"><pre>{escape(public_log)}</pre></div>'
    log_body += '<div class="card">Trích đúng các trường từ dòng log; ẩn <code>session_id</code>, <code>user_id_hash</code> và preview vì chúng không cần cho chuỗi điều tra.</div>'
    log_body += f'<div class="card">Log <code>response_sent</code> ghi <span class="bad">latency_ms={target_log["latency_ms"]}</span>, vượt {threshold:,} ms. <code>tool_success=true</code>, <code>ttft_ms={target_log["ttft_ms"]}</code>; chưa đủ để xác định span chậm nếu chỉ xem log.</div>'

    total_ms = root.latency * 1000
    waterfall_rows = []
    for item in (root, retrieval, generation):
        offset = max(0, (item.start_time - root.start_time).total_seconds() * 1000)
        duration = item.latency * 1000
        left = min(100, offset / total_ms * 100)
        width = min(100-left, max(0.5, duration / total_ms * 100))
        bar = f'<div class="bar"><div class="fill" style="left:{left:.1f}%;width:{width:.1f}%"></div></div>'
        waterfall_rows.append((item.name,item.type,f"{duration:,.0f} ms",bar))
    head = '<tr><th>Observation</th><th>Loại</th><th>Thời lượng</th><th>Waterfall</th></tr>'
    body = ''.join(f'<tr><td>{escape(a)}</td><td>{escape(b)}</td><td>{escape(c)}</td><td>{d}</td></tr>' for a,b,c,d in waterfall_rows)
    trace_body = f'<div class="card">Project: <code>{PROJECT}</code><br>Trace ID: <code>{root.trace_id}</code><br>Correlation ID: <code>{target_id}</code> · {escape(interval)}</div>'
    trace_body += f'<div class="card"><table>{head}{body}</table></div>'
    trace_body += f'<div class="card"><span class="bad">Retrieval chiếm {retrieval.latency/root.latency*100:.1f}%</span> thời gian agent; generation chỉ {generation.latency*1000:.0f} ms. Hai child observation có cùng parent ID <code>{root.id}</code>.</div>'

    pages = {
        "12-incident-metric": (page("Metric: latency tăng trong challenge", subtitle, metric_body, "data/logs.jsonl + scripts/load_test.py + Langfuse Observations API v2"),
            "Challenge ID: " + challenge_id + "\nSeed: " + str(seed) + "\nIncident interval: " + interval + "\nMetric | Baseline | Incident\n" + "\n".join(" | ".join(row) for row in metric_rows) + "\n"),
        "13-incident-log-public": (page("Log: request chậm có correlation ID", subtitle, log_body, "data/logs.jsonl, trích các trường cần thiết"),
            f"data/logs.jsonl:{line_number} (selected fields)\n{public_log}\n"),
        "14-incident-trace": (page("Trace: retrieval là span gây chậm", subtitle, trace_body, "Langfuse Public API v2, project cá nhân"),
            f"Project: {PROJECT}\nTrace ID: {root.trace_id}\nCorrelation ID: {target_id}\nRoot observation: {root.id} latency_ms={root.latency*1000:.0f}\nRetrieval: {retrieval.id} parent={retrieval.parent_observation_id} latency_ms={retrieval.latency*1000:.0f}\nGeneration: {generation.id} parent={generation.parent_observation_id} latency_ms={generation.latency*1000:.0f}\n"),
    }
    for stem in pages:
        assert not (output_dir / f"{stem}.txt").exists()
        assert not (output_dir / f"{stem}.png").exists()
    temp = Path(tempfile.mkdtemp(prefix="cp3-evidence-"))
    for stem, (html, plain) in pages.items():
        html_path = temp / f"{stem}.html"
        html_path.write_text(html, encoding="utf-8")
        screenshot = output_dir / f"{stem}.png"
        subprocess.run([
            "google-chrome", "--headless=new", "--no-sandbox", "--disable-gpu",
            "--disable-dev-shm-usage", f"--user-data-dir={temp / 'chrome-profile'}",
            "--window-size=1440,900", "--hide-scrollbars",
            f"--screenshot={screenshot}", html_path.as_uri(),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        assert screenshot.is_file() and screenshot.stat().st_size > 10_000
        with (output_dir / f"{stem}.txt").open("x", encoding="utf-8") as output:
            output.write(plain)
    print("Challenge:", challenge_id, "seed:", seed)
    print("Incident:", interval)
    print("Baseline app P95:", percentile(baseline, 95), "ms")
    print("Incident app P95:", percentile(incident, 95), "ms")
    print("Correlation ID:", target_id, "log line:", line_number)
    print("Trace ID:", root.trace_id, "retrieval:", retrieval.latency * 1000, "ms")
    print("Evidence:", ", ".join(pages))


if __name__ == "__main__":
    main()
