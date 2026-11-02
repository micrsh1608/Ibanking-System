# Checklist bàn giao mốc 07–08/11

## Đã hoàn thiện

- [x] Thử tải thực trên SQL Server và kiểm toán Payment/ledger/hóa đơn/outbox.
- [x] Mất phản hồi sau debit và finalize qua proxy HTTP thực; đối soát cùng UUID.
- [x] Docker network partition, SIGKILL Payment sau debit, SIGKILL SQL giữa transaction.
- [x] Sửa guard kết nối riêng, khắc phục nghẽn pool ORM phát hiện từ thử tải.
- [x] Cài mới trên project/volume riêng; luồng một kỳ và tất cả qua SMTP thật vào Mailpit.
- [x] Seed chạy lặp không reset số dư hoặc PAID; demo chính giữ dữ liệu hiện có.
- [x] Báo cáo PDF và nguồn Markdown; slide PPTX có đối tượng/sơ đồ/bảng có thể sửa.
- [x] Xuất Use Case, kiến trúc, ba ERD và sequence PNG trong `docs/diagrams/exported`.
- [x] API đầy đủ, migration, Docker/SMTP, kịch bản demo, JSON/ảnh bằng chứng.
- [x] Backup source ZIP có manifest hash và loại cấu hình riêng/thư mục phụ thuộc.

## Nhóm hoàn thiện trước khi nộp

- [ ] Điền họ tên/MSSV của hai thành viên còn lại và phân công thực tế.
- [ ] Xác nhận yêu cầu tên file/định dạng và nơi nộp của giảng viên.
- [ ] Mở PPTX trên máy trình chiếu, kiểm tra font và thử cổng/mạng Docker tại đó.
- [ ] Chép PDF/PPTX/ZIP/ảnh sang USB; so sánh SHA256SUMS.txt sau khi chép.

`docs/team.json` là nguồn thông tin bìa. Sau khi sửa, cập nhật PDF/Markdown đã
xuất và slide; các builder trong scripts dành cho môi trường authoring có sẵn
ReportLab/Artifact Tool, không bắt buộc để chạy ứng dụng. Có thể sửa PPTX trực
tiếp bằng PowerPoint; báo cáo nguồn Markdown luôn đi kèm để nhóm biên tập.

## Vị trí tám yêu cầu đề bài

| Yêu cầu | Vị trí |
|---|---|
| Phân tích nghiệp vụ, Use Case, ERD | docs/architecture.md, final-report.md, diagrams |
| Kiến trúc Microservices | architecture.md, compose.yaml, services/ |
| REST API, method, URI, input/output/status | docs/api.md, OpenAPI ba service |
| SQL/NoSQL phù hợp | SQL Server, models và migration từng service |
| Hiện thực luồng nghiệp vụ | services/, frontend/, tests/integration/ |
| Transaction và concurrency | shared/locking.py, account ledger, tuition reservations, payment coordinator |
| Web tích hợp API | frontend/, Account gateway, tests/e2e/ |
| Hướng dẫn cài/chạy/sử dụng và trình diễn | README, start.ps1, runbook, demo-script, submission/ |

## Phân biệt phạm vi nghiệm thu

Bộ release chạy trên project riêng `ibanking-acceptance-<8hex>`, cổng 810x,
SQL 14331 và Mailpit 8026; kết thúc dừng container, giữ volume test để đối chiếu.
Backend/E2E thông thường tạo dữ liệu IT_* trong demo Docker 800x/14330, không dùng
SQL Server Windows ở `.env`. Không chạy các bài kill/disconnect trên dữ liệu thật.

Các giới hạn triển khai công khai được ghi trong báo cáo; không suy ra khả năng
production từ số liệu tải ngắn trên một máy. SMTP thật chưa được cấu hình bằng
tài khoản của nhóm; Mailpit đã kiểm tra đầy đủ giao thức gửi OTP/biên nhận.
