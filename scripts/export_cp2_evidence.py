"""Export a small, verifiable CP2 snapshot from the Langfuse Public API v2."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

from dotenv import load_dotenv
from langfuse import get_client

ROOT = Path(__file__).resolve().parents[1]
PROMPT_NAME = "day13-chat"
EXPECTED_PROJECT = "day13-k4-l3b-2A202602395"
TRACE_IDS = {
    "baseline": "19ccdc00c2e9edcde74e040e3f2f47ab",
    "candidate": "fb4d97fa85f69881f428bf3e6ed61fc2",
    "promoted": "4b6e95a6ad3058b59941f0ebb49a4d8e",
    "rolled_back": "e2935857263d76f119e6e65a9d6d8cfd",
    "slow_retrieval": "197f92fc2d3a2243fab8c00d6653018b",
}
FIELDS = "core,basic,time,metadata,usage,prompt,trace_context,model"


def _write_new(path: Path, value: str) -> None:
    with path.open("x", encoding="utf-8") as file:
        file.write(value)


def _page(title: str, project: str, body: str, captured: str) -> str:
    return f'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>
:root {{ color-scheme:dark; font-family:Inter,system-ui,sans-serif; background:#0e1521; color:#edf3f7 }}
body {{ margin:0; padding:30px 38px; max-width:1440px; box-sizing:border-box }}
.eyebrow {{ color:#83b6cc; font-size:12px; letter-spacing:.12em; font-weight:750; text-transform:uppercase }}
h1 {{ margin:8px 0 12px; font-size:29px }} .sub {{ color:#a7bacb; font-size:13px; margin-bottom:23px }}
.card {{ border:1px solid #2b4053; border-radius:16px; background:#172538; padding:19px 22px; margin:14px 0 }}
table {{ width:100%; border-collapse:collapse; font-size:13px }} th {{ text-align:left; color:#8db7c9; font-size:11px; letter-spacing:.08em; text-transform:uppercase }}
td,th {{ padding:10px 8px; border-bottom:1px solid #304356; vertical-align:top }}
code,pre {{ font-family:ui-monospace,SFMono-Regular,monospace; color:#aee1cd }} code {{ font-size:12px }}
pre {{ white-space:pre-wrap; font-size:13px; line-height:1.5 }}
.muted {{ color:#9db4c6 }} .good {{ color:#9ce4b8 }} .bar {{ background:#1d3347; height:19px; border-radius:4px; position:relative; min-width:370px }}
.fill {{ position:absolute; height:19px; background:#56b9ad; border-radius:4px }}
footer {{ color:#8199ab; font-size:12px; margin-top:18px }}
</style></head><body><div class="eyebrow">Langfuse Public API v2 · dữ liệu thật từ project cá nhân</div>
<h1>{escape(title)}</h1><div class="sub">Project: <strong>{escape(project)}</strong> · Truy vấn: {escape(captured)} UTC · Không hiển thị API key hoặc nội dung đầu vào thô</div>
{body}<footer>Nguồn: GET /api/public/v2/observations và Prompt Management API. Các ID có thể đối chiếu với structured log trong repository.</footer></body></html>'''


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{escape(value)}</th>" for value in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(value)}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f'<div class="card"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _observation_rows(client, trace_id: str) -> list:
    return client.api.observations.get_many(trace_id=trace_id, limit=20, fields=FIELDS).data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page-dir", type=Path, required=True)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    client = get_client()
    projects = client.api.projects.get().data
    assert len(projects) == 1 and projects[0].name == EXPECTED_PROJECT

    now = datetime.now(timezone.utc)
    captured = now.strftime("%Y-%m-%d %H:%M:%S")
    records = []
    cursor = None
    for _ in range(5):
        page = client.api.observations.get_many(
            limit=100, cursor=cursor, fields=FIELDS,
            from_start_time=now - timedelta(hours=1),
        )
        records.extend(page.data)
        cursor = page.meta.cursor
        if not cursor:
            break
    grouped = defaultdict(list)
    for observation in records:
        grouped[observation.trace_id].append(observation)

    logged_ids = {
        json.loads(line).get("correlation_id")
        for line in (ROOT / "data/logs.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    complete = []
    for trace_id, items in grouped.items():
        names = {item.name for item in items}
        if not {"lab-agent-run", "retrieval", "generation"} <= names:
            continue
        root = next(item for item in items if item.name == "lab-agent-run")
        correlation_id = (root.metadata or {}).get("correlation_id")
        if correlation_id in logged_ids:
            complete.append((root.start_time, trace_id, correlation_id, root))
    complete.sort(reverse=True)
    assert len(complete) >= 10, f"Only {len(complete)} complete linked traces found"

    evidence_dir = ROOT / "submission/evidence"
    page_dir = args.page_dir
    page_dir.mkdir(parents=True, exist_ok=True)

    selected = complete[:10]
    trace_rows = [
        [str(index), trace_id, correlation_id, str((root.metadata or {}).get("prompt_label", "")), str((root.metadata or {}).get("prompt_version", ""))]
        for index, (_, trace_id, correlation_id, root) in enumerate(selected, 1)
    ]
    body = _table(["#", "Trace ID", "Correlation ID", "Label", "Version"], trace_rows)
    _write_new(page_dir / "06-trace-list.html", _page("10 trace hoàn chỉnh", EXPECTED_PROJECT, body, captured))
    _write_new(evidence_dir / "06-trace-list.txt", "Langfuse Public API v2 · " + EXPECTED_PROJECT + "\n" + "\n".join(" | ".join(row) for row in trace_rows) + "\n")

    slow = _observation_rows(client, TRACE_IDS["slow_retrieval"])
    assert {item.name for item in slow} == {"lab-agent-run", "retrieval", "generation"}
    root = next(item for item in slow if item.name == "lab-agent-run")
    assert (root.metadata or {}).get("correlation_id") == "req-9d4c92c6"
    assert next(item for item in slow if item.name == "retrieval").latency >= 2.4
    root_start = root.start_time
    root_ms = (root.end_time - root_start).total_seconds() * 1000
    waterfall_rows = []
    for item in sorted(slow, key=lambda value: value.start_time):
        offset = (item.start_time - root_start).total_seconds() * 1000
        duration = (item.end_time - item.start_time).total_seconds() * 1000
        left = max(0, offset / root_ms * 100)
        width = max(1, duration / root_ms * 100)
        waterfall_rows.append(
            f'<tr><td>{escape(item.name)}</td><td>{escape(item.type)}</td><td>{duration:,.0f} ms</td>'
            f'<td><div class="bar"><div class="fill" style="left:{left:.2f}%;width:{min(width,100-left):.2f}%"></div></div></td></tr>'
        )
    body = (
        f'<div class="card"><p>Trace <code>{TRACE_IDS["slow_retrieval"]}</code> · correlation ID <code>req-9d4c92c6</code> · tổng {root_ms:,.0f} ms</p>'
        '<table><tr><th>Observation</th><th>Loại</th><th>Thời lượng</th><th>Waterfall</th></tr>'
        + "".join(waterfall_rows) + '</table><p class="muted">Retrieval và generation là hai child observation của lab-agent-run.</p></div>'
    )
    _write_new(page_dir / "07-trace-waterfall.html", _page("Trace waterfall · retrieval chậm có kiểm soát", EXPECTED_PROJECT, body, captured))
    _write_new(evidence_dir / "07-trace-waterfall.txt", "Trace " + TRACE_IDS["slow_retrieval"] + " · req-9d4c92c6\n" + "\n".join(f"{item.name} parent={item.parent_observation_id} latency_s={item.latency}" for item in slow) + "\n")

    promoted = _observation_rows(client, TRACE_IDS["promoted"])
    generation = next(item for item in promoted if item.name == "generation")
    assert generation.prompt_name == PROMPT_NAME and generation.prompt_version == 2
    metadata = generation.metadata or {}
    metadata_rows = [
        ["Trace ID", generation.trace_id], ["Correlation ID", str(metadata.get("correlation_id"))],
        ["Parent observation", str(generation.parent_observation_id)], ["Model", str(generation.model)],
        ["Prompt", f"{generation.prompt_name} · {metadata.get('prompt_label')} · v{generation.prompt_version}"],
        ["Tokens", f"input {generation.usage_details.get('input')} · output {generation.usage_details.get('output')}"],
        ["Chi phí", f"USD {generation.cost_details.get('total')}"],
        ["TTFT", f"{metadata.get('ttft_ms')} ms"],
    ]
    _write_new(page_dir / "08-trace-metadata.html", _page("Trace metadata · prompt và chi phí", EXPECTED_PROJECT, _table(["Trường", "Giá trị"], metadata_rows), captured))
    _write_new(evidence_dir / "08-trace-metadata.txt", "Langfuse Public API v2\n" + "\n".join(" | ".join(row) for row in metadata_rows) + "\n")

    versions = [client.api.prompts.get(PROMPT_NAME, version=version) for version in (1, 2)]
    version_rows = [[str(prompt.version), ", ".join(prompt.labels), prompt.type, prompt.name] for prompt in versions]
    body = _table(["Version", "Labels hiện tại", "Loại", "Prompt name"], version_rows)
    body += '<div class="card"><p>Prompt contract:</p><pre>Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}</pre><p class="muted">Version 2 thêm yêu cầu trả lời ngắn và dẫn tài liệu.</p></div>'
    _write_new(page_dir / "09-prompt-versions.html", _page("Prompt versions · baseline và candidate", EXPECTED_PROJECT, body, captured))
    _write_new(evidence_dir / "09-prompt-versions.txt", "Langfuse Prompt Management API\n" + "\n".join(" | ".join(row) for row in version_rows) + "\n")

    current = client.get_prompt(PROMPT_NAME, label="production", cache_ttl_seconds=0)
    assert current.version == 1
    promoted_generation = next(item for item in promoted if item.name == "generation")
    rolled_back = _observation_rows(client, TRACE_IDS["rolled_back"])
    rollback_generation = next(item for item in rolled_back if item.name == "generation")
    assert (promoted_generation.metadata or {}).get("prompt_label") == "production" and promoted_generation.prompt_version == 2
    assert (rollback_generation.metadata or {}).get("prompt_label") == "production" and rollback_generation.prompt_version == 1
    rollback_rows = [
        ["Trước rollback", "production → v2", TRACE_IDS["promoted"], str((promoted_generation.metadata or {}).get("correlation_id"))],
        ["Sau rollback", "production → v1", TRACE_IDS["rolled_back"], str((rollback_generation.metadata or {}).get("correlation_id"))],
        ["Hiện tại", "production → v1", "API get_prompt", "verified"],
    ]
    _write_new(page_dir / "10-prompt-rollback.html", _page("Rollback production · v2 về v1", EXPECTED_PROJECT, _table(["Mốc", "Nhãn", "Bằng chứng", "Correlation ID"], rollback_rows), captured))
    _write_new(evidence_dir / "10-prompt-rollback.txt", "Langfuse API + trace history\n" + "\n".join(" | ".join(row) for row in rollback_rows) + "\n")
    print("project:", EXPECTED_PROJECT)
    print("complete_linked_traces:", len(complete))
    print("selected_trace_ids:", [row[1] for row in trace_rows])
    print("html_dir:", page_dir)


if __name__ == "__main__":
    main()
