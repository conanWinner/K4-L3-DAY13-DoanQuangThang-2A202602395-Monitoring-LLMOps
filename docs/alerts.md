# Alert và runbook CP2

Nguồn số liệu là `data/logs.jsonl`; đối chiếu sáu panel tại `/dashboard`. Cả ba alert gửi tới Slack `#k4-l3b-alerts`, owner `student-2A202602395`. Cấu hình ở `config/alert_rules.yaml` mô tả điều kiện để triển khai trong công cụ cảnh báo; bản lab chưa có dịch vụ gửi Slack tự động.

## Alert 1

- **Tên:** `HighLatencyP95` · warning · duy trì 5 phút.
- **Điều kiện:** P95 của `response_sent.latency_ms` vượt 3000 ms trong cửa sổ 5 phút. Người dùng phải chờ lâu hơn ngưỡng SLO.
- **Kiểm tra:** (1) Xác nhận P95, P99 và TTFT trên panel Latency cùng khoảng thời gian; (2) lọc các dòng `response_sent` chậm, lấy `correlation_id`; (3) mở trace Langfuse cùng ID và so sánh thời gian retrieval với generation.
- **Giảm ảnh hưởng:** Nếu chỉ generation chậm sau khi đổi prompt, rollback label `production`; nếu retrieval chậm, kiểm tra nguồn tra cứu và giảm tải/tắt practice incident sau khi lưu evidence. Đo lại P95 sau xử lý.

## Alert 2

- **Tên:** `HighErrorRate` · critical · duy trì 5 phút.
- **Điều kiện:** `request_failed / request_received * 100` vượt 2% trong cửa sổ 5 phút. Người dùng không nhận được câu trả lời thành công.
- **Kiểm tra:** (1) Xác nhận error rate và loại lỗi trên panel Errors; (2) lọc `request_failed` theo khoảng thời gian, lấy `correlation_id` và `error_type`; (3) mở trace cùng ID, xác định observation lỗi và kiểm tra log trước/sau.
- **Giảm ảnh hưởng:** Khôi phục dependency hoặc cấu hình gây lỗi; nếu lỗi xuất hiện sau một lần thay đổi prompt hay practice scenario, rollback/tắt thay đổi đó. Chạy lại workload nhỏ và xác nhận error rate về dưới 2%.

## Alert 3

- **Tên:** `LowRetrievalSuccess` · warning · duy trì 5 phút.
- **Điều kiện:** Trong các bản ghi `tool_name=retrieval` có `tool_success` không rỗng, tỷ lệ `true` dưới 90% trong cửa sổ 5 phút. Câu trả lời có nguy cơ thiếu ngữ cảnh hoặc request thất bại.
- **Kiểm tra:** (1) Xác nhận retrieval success trên panel Errors cùng error rate; (2) lọc log `tool_success=false`, lấy `correlation_id`; (3) mở observation retrieval của trace tương ứng để xem lỗi/thời gian và đối chiếu query preview đã che PII.
- **Giảm ảnh hưởng:** Kiểm tra kho tài liệu hoặc dịch vụ tra cứu, khôi phục cấu hình truy cập hoặc tắt practice scenario sau khi lưu evidence. Chạy lại mẫu truy vấn và xác nhận tỷ lệ đạt ít nhất 90%.

Với cả ba alert, ghi thời gian bắt đầu, giá trị metric, một dòng log và trace ID vào báo cáo khi xử lý sự cố thật. Không kết luận root cause chỉ từ một panel.
