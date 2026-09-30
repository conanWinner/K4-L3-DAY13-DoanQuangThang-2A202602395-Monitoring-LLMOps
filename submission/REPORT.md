# Báo cáo cá nhân — K4-L3B Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Doan Quang Thang
- **MSSV:** 2A202602395
- **Lớp:** K4-L3B
- **Repository URL:** https://github.com/conanWinner/K4-L3-DAY13-DoanQuangThang-2A202602395-Monitoring-LLMOps
- **Commit SHA cuối:** Xem SHA gửi kèm URL trên VLearn LMS/Codelabs. Commit không thể tự chứa SHA của chính nó; lấy SHA bằng `git rev-parse HEAD` sau khi push.
- **Challenge ID:** `day13-k4-l3b-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3b-2A202602395`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| CP0 baseline trước CP1 | `evidence/00-cp0-baseline.txt` |
| Pytest CP1 | `evidence/01-pytest.txt` |
| Log validator CP1 | `evidence/02-log-validator.txt` |
| Dashboard validator CP1 | `evidence/03-dashboard-validator.txt` |
| Structured log CP1 | `evidence/04-structured-log.txt` |
| PII redaction CP1 | `evidence/05-pii-redaction.txt` |
| Pytest CP2 | `evidence/01-pytest-cp2.txt` |
| Log validator CP2 | `evidence/02-log-validator-cp2.txt` |
| Dashboard validator CP2 | `evidence/03-dashboard-validator-cp2.txt` |
| Pytest cuối CP4 | `evidence/01-pytest-cp4.txt` |
| Log validator cuối CP4 | `evidence/02-log-validator-cp4.txt` |
| Dashboard validator cuối CP4 | `evidence/03-dashboard-validator-cp4.txt` |
| Rà tệp nộp, secret và PII | `evidence/16-prepush-audit.txt` |
| Trace list | `evidence/06-trace-list.png` (`.txt` cùng tên) |
| Trace waterfall | `evidence/07-trace-waterfall.png` (`.txt` cùng tên) |
| Trace metadata | `evidence/08-trace-metadata.png` (`.txt` cùng tên) |
| Prompt versions | `evidence/09-prompt-versions.png` (`.txt` cùng tên) |
| Prompt rollback | `evidence/10-prompt-rollback.png` (`.txt` cùng tên) |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric và workload | `evidence/12-incident-metric.png`, `evidence/12-incident-metric.txt`, `evidence/12-incident-run.txt` |
| Incident log | `evidence/13-incident-log-public.png`, `evidence/13-incident-log-public.txt` |
| Incident trace | `evidence/14-incident-trace.png`, `evidence/14-incident-trace.txt` |
| Kiểm tra sau khôi phục | `evidence/15-incident-recovery.txt` |

Các ảnh `06`–`10` được kết xuất từ dữ liệu thật trả về bởi Langfuse Public API v2 và Prompt Management API của project cá nhân; chúng không phải ảnh chụp giao diện Langfuse. File `.txt` cùng tên giữ các giá trị để đối chiếu. Ảnh `11` là ảnh chụp trang `/dashboard` đang chạy.
Ảnh `12`–`14` cũng là bản kết xuất từ log ứng dụng, đầu ra `load_test.py` và Langfuse Observations API v2. `12` lọc đúng 10 request của challenge để tránh cộng lẫn workload CP1–CP2 trong dashboard 60 phút; ảnh không phải ảnh chụp trực tiếp dashboard hay giao diện Langfuse. `13` chỉ trích các trường log cần thiết, không công bố session ID/preview của challenge. Script tái tạo bằng chứng: `scripts/export_cp3_evidence.py` (xuất vào thư mục trống bằng `--output-dir`).

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 trên 107 dòng log cũ | 100/100 trên 121 dòng log CP4 | 55 correlation ID duy nhất; 0 PII leak; `evidence/02-log-validator-cp4.txt` |
| `validate_dashboard.py` | 6/6 panel | 6/6 panel | `evidence/03-dashboard-validator-cp4.txt`; dashboard runtime tại `evidence/11-dashboard-overview.png` |
| `pytest` | 22 passed | 26 passed | Chạy bằng `.venv/bin/python`; `evidence/01-pytest-cp4.txt` |
| Số traces hợp lệ | Chỉ có root observation | 22 trace hoàn chỉnh tại CP2; thêm 10 trace đối chứng/sự cố được kiểm tra tại CP3 | 10 trace ID CP2 trong `evidence/06-trace-list.txt`; một trace CP3 trong `evidence/14-incident-trace.txt` |
| Số PII leak | 0 | 0 | Validator kiểm tra email, điện thoại, CCCD, thẻ |
| Latency P95 / TTFT P95 | 1038 / 50 ms trên 21 request baseline CP2 | 3696 / 50 ms trong ảnh dashboard CP2 | P99 18577 ms; tail latency tăng ở một số request |
| Retrieval success rate | 100% trên 21 request baseline CP2 | 100% trên 38 request trong ảnh dashboard | Panel Errors hiển thị tỷ lệ này cùng error rate |
| Incident latency P95 | 1132 ms trên 5 request đối chứng | 2652 ms trên 5 request sự cố | 5/5 vượt ngưỡng 2000 ms; `evidence/12-incident-metric.png` |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** Middleware nhận `x-request-id` nếu đúng dạng `req-<8-hex>`; trường hợp khác sinh ID mới. Đầu mỗi request xóa context cũ rồi bind ID vào log; ID đi vào agent, response body và header `x-request-id`. Header `x-response-time-ms` ghi thời gian xử lý.
- **Các metadata được ghi vào structured log:** `correlation_id`, `user_id_hash`, `session_id`, `feature`, `model`, `env`, cùng timestamp, event và các số đo của response. Không ghi `user_id` nguyên văn.
- **Cách bảo đảm PII được scrub trước khi ghi:** Processor duyệt mọi giá trị chuỗi, kể cả trong dict/list lồng nhau, để che email, số điện thoại Việt Nam, CCCD và thẻ trước JSON renderer và file writer. `session_id` và `feature` cũng được scrub trước khi đưa vào metadata trace Langfuse.
- **Cách kiểm chứng kết quả:** `evidence/01-pytest.txt` đến `evidence/05-pii-redaction.txt`. Đã chạy 10 request mẫu, thêm một request có ID do client cấp; validator đạt 100/100 và không phát hiện PII nguyên văn. Log baseline được giữ trong `data/logs.cp0-baseline-20260930T032907Z.jsonl` (không commit).

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** Key trong `.env` xác thực vào project `day13-k4-l3b-2A202602395`. Chạy workload bằng `scripts/load_test.py`; Langfuse Observations API v2 trả 22 trace có đủ ba observation và `correlation_id` khớp log local. Mười trace ID đại diện: `6ac4d445c48e2da1a0af3dd129da7f0d`, `59f3afdc7681b4474d564b58add91d86`, `a9022f3e0d06d6d8450efa3be310e0b1`, `dc35da63723b1f5b393c9a4140c45a28`, `ba56284754b12156bcab176eab1dd3e8`, `4b2882d684172aecf36d5df9a89873f7`, `c4baabef76225e3350574d3da82e9b0e`, `197f92fc2d3a2243fab8c00d6653018b`, `e2935857263d76f119e6e65a9d6d8cfd`, `4b6e95a6ad3058b59941f0ebb49a4d8e`.
- **Cấu trúc root/retrieval/generation observations:** `lab-agent-run` là root; `retrieval` (`RETRIEVER`) và `generation` (`GENERATION`) là hai child. Trace `197f92fc2d3a2243fab8c00d6653018b` có tổng 2652 ms: retrieval 2500 ms, generation 150 ms. Generation ghi model, token input/output, cost, TTFT và liên kết prompt managed.
- **Cách nối trace với log:** Metadata trace có `correlation_id`. Ví dụ trace chậm trên mang `req-9d4c92c6`; dòng `response_sent` trong log có cùng ID và `latency_ms=2651`.
- **Prompt name:** `day13-chat`; template giữ `{{feature}}`, `{{docs}}`, `{{message}}`.
- **Version/label baseline:** version 1 có `baseline`, hiện cũng có `production` sau rollback.
- **Version/label candidate:** version 2 có `candidate`; thêm yêu cầu trả lời ngắn và dẫn tài liệu.
- **Trace ID của mỗi version:** Cùng input: baseline v1 `19ccdc00c2e9edcde74e040e3f2f47ab` (`req-de5be466`), candidate v2 `fb4d97fa85f69881f428bf3e6ed61fc2` (`req-d1ebace1`).
- **Cách promote và rollback `production`:** Chuyển `production` sang v2, trace `4b6e95a6ad3058b59941f0ebb49a4d8e` (`req-8a0489ea`) ghi version 2. Sau đó chuyển lại v1, trace `e2935857263d76f119e6e65a9d6d8cfd` (`req-243cb89e`) ghi version 1; API hiện trả `production → v1`. Một lần fetch prompt bị timeout đã dùng local fallback; trace lỗi đó không được dùng làm bằng chứng version managed.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** `/dashboard` đọc `data/logs.jsonl`, hiển thị Latency (P50/P95/P99, TTFT P95), Traffic, Errors (error rate và retrieval success), Cost, Tokens, Quality. Trang dùng time range 60 phút, tự refresh 30 giây và hiện đơn vị/ngưỡng từ `config/dashboard.yaml`. Ảnh CP2 có 38 request, 11 request/phút gần nhất, cost 0.0820 USD, 6530 token và quality trung bình 0.87.
- **SLO và lý do chọn:** 99.5% request trong 28 ngày phải trả thành công với `latency_ms ≤ 3000`. Baseline CP2 có 21 request, P95 1038 ms và P99 1473 ms; ngưỡng 3000 ms cho khoảng đệm khi tải tăng nhưng vẫn cảnh báo tail latency. Ảnh sau workload có P95 3696 ms và 94.7% request đạt ngưỡng trong mẫu 38 request; đây là mẫu ngắn, không phải kết quả SLO 28 ngày.
- **Cách tính error budget:** `100% - 99.5% = 0.5%`. Nếu cửa sổ 28 ngày có 10.000 request, tối đa `10.000 × 0.005 = 50` request được phép lỗi hoặc chậm hơn 3000 ms.
- **Ba alert và runbook tương ứng:** `HighLatencyP95` (>3000 ms trong 5 phút), `HighErrorRate` (>2% trong 5 phút), `LowRetrievalSuccess` (<90% trong 5 phút). Cả ba cấu hình `duration: 5m`, Slack `#k4-l3b-alerts`, owner `student-2A202602395`; bước kiểm tra Metrics → Logs → Traces và cách giảm ảnh hưởng ở `config/alert_rules.yaml` và `docs/alerts.md`. Lab mới có cấu hình và runbook, chưa có dịch vụ tự gửi Slack.

> Ví dụ cách viết error budget: "SLO 99.5% trong 28 ngày nghĩa là error budget 0.5%. Nếu workload có 10,000 request thì tối đa 50 request được phép lỗi hoặc chậm hơn ngưỡng SLO."

## 7. Điều tra challenge

- **Challenge ID và seed:** `day13-k4-l3b-monitoring-llmops-v1`, seed `1312`, cohort K4, feature `monitoring`; 5 truy vấn được lấy bằng `scripts/load_test.py --challenge --concurrency 5`. Không đưa nội dung query hoặc file `config/challenge.json` vào repo/evidence.
- **Khoảng thời gian điều tra:** Đối chứng `2026-09-30 04:22:05–04:22:07 UTC`; sự cố `04:22:07–04:22:21 UTC` cùng ngày. Evidence: `evidence/12-incident-run.txt` và `evidence/12-incident-metric.png`.
- **Triệu chứng từ metrics:** P95 thời gian xử lý trong ứng dụng, tính từ `response_sent` theo nearest-rank như dashboard, tăng từ `1132` lên `2652 ms`; cả `5/5` request sự cố vượt ngưỡng challenge `2000 ms`, đối chứng `0/5`. P95 từ client tăng từ `1843.8` lên `13291.2 ms`. Retrieval trung bình trong Langfuse tăng từ khoảng `0` lên `2501 ms`. HTTP error và retrieval failure đều `0/5`, TTFT của log đại diện là `50 ms`. Đây là sự cố latency, không phải lỗi HTTP.
- **Log line và correlation ID liên quan:** `data/logs.jsonl:98`, event `response_sent`, `correlation_id=req-6d5f7eaf`, `feature=monitoring`, `latency_ms=2651`, `tool_success=true`, `ttft_ms=50`; các trường được trích tại `evidence/13-incident-log-public.txt` và ảnh `evidence/13-incident-log-public.png`.
- **Trace ID và span gây ảnh hưởng:** Trace trong project `day13-k4-l3b-2A202602395` có ID `cc48a6da99ffdf932d305172bb24810e` và cùng `correlation_id=req-6d5f7eaf`. Root `lab-agent-run` mất `2653 ms`; child `retrieval` mất `2500 ms` (94.2% thời gian root), child `generation` mất `150 ms`. Hai child cùng parent ID của root. Xem `evidence/14-incident-trace.png` và `.txt` cùng tên.
- **Root cause:** Scenario `rag_slow` làm `retrieve()` trong `app/mock_rag.py` chờ đồng bộ 2,5 giây. Span retrieval xác nhận phần chậm này; generation/TTFT vẫn bình thường. Với 5 request đồng thời, `app/main.py` gọi `agent.run()` đồng bộ từ route `async`, nên các lượt xử lý tuần tự trên event loop; điều này phù hợp với P95 client khoảng 13,29 giây. Kết luận về điểm chậm dựa trên trace; phần event loop dựa thêm trên đường gọi trong mã và thứ tự timestamp log.
- **Fix action:** Đã tắt `rag_slow` bằng `scripts/inject_incident.py --disable` và xác nhận `/health` báo ba incident đều `false`. Chạy lại cùng 5 query ở concurrency 5: `5/5` app latency dưới `2000 ms`, ghi tại `evidence/15-incident-recovery.txt`. Khi triển khai thật, chuyển retrieval đồng bộ sang I/O bất đồng bộ hoặc chạy trong thread pool; giữ scenario injection để có thể tái hiện bài lab.
- **Preventive measure:** Cảnh báo P95 latency của retrieval và tỷ lệ request vượt `2000 ms` cho feature `monitoring`, nối alert tới runbook Metrics → Logs → Traces. Bổ sung phép đo HTTP end-to-end ngoài `agent.run`: app latency sau khôi phục dưới 2 giây nhưng client vẫn khoảng 2,16 giây do overhead/tắc nghẽn ngoài phần đo hiện tại. Theo dõi cả hai để không bỏ sót thời gian chờ ở hàng đợi/event loop.

> Gợi ý cách viết ngắn, không thay cho evidence thực tế: "Metric cho thấy `[latency/error/cost/quality]` bất thường trong `[khoảng thời gian]`. Log line `[event]` có `correlation_id=[...]` đại diện cho request bị ảnh hưởng. Trace cùng `correlation_id` cho thấy span `[retrieval/generation/prompt/tool]` có dấu hiệu `[chậm/lỗi/token tăng]`. Root cause là `[nguyên nhân suy ra từ evidence]`. Fix action là `[hành động khôi phục]`; preventive measure là `[alert/runbook/test/guardrail để ngăn tái diễn]`."

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** Dùng cùng 5 query/seed với và không có incident, rồi lọc metric theo correlation ID của hai lượt; như vậy không lẫn workload CP1–CP2 trong cửa sổ dashboard 60 phút.
- **Một lỗi/blocker đã gặp:** P95 client khi bật sự cố gần 13,3 giây, lớn hơn nhiều so với `latency_ms` khoảng 2,65 giây trong app.
- **Cách tìm nguyên nhân và xử lý:** Đối chiếu timestamp các dòng `request_received` và trace: retrieval mất 2,5 giây mỗi lượt; route `async` gọi hàm đồng bộ nên các request concurrent bị xử lý tuần tự. Tắt incident và chạy lại 5 query để xác nhận phục hồi trong phạm vi app latency.
- **Cách hiểu luồng Metrics → Logs → Traces:** Metric chỉ ra 5/5 request vượt 2 giây; log chọn `req-6d5f7eaf`; Langfuse trace cùng ID cô lập retrieval, khác với generation 150 ms.
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** TTFT và generation không tăng trong incident này, nên đổi prompt hoặc model không phải hành động đầu tiên; SLO/alert theo latency cần thêm metric từ phía client để thấy thời gian chờ ngoài agent.
- **Điều quan trọng nhất đã học:** Một metric tổng hợp chưa đủ để kết luận root cause; phải nối request ID đến span và kiểm tra chênh lệch giữa app latency với end-to-end latency.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** Chưa đưa bản sửa non-blocking retrieval vào runtime vì đây là scenario injection phục vụ bài lab; alert vẫn là YAML/runbook, chưa được nối đến dịch vụ Slack thật. Chủ tài khoản cần nộp URL repo và commit SHA trên LMS/Codelabs.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
