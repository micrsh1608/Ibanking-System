# iBanking — Thanh toán học phí

Dự án giữa kỳ dùng FastAPI, SQLAlchemy, SQL Server và HTML/CSS/JavaScript.
Mã nguồn được tổ chức theo ba service: Account, Payment và Tuition.

**Hiện trạng:** đã hoàn thành sớm các mốc 02–08/11: thanh toán một/toàn bộ hóa đơn,
OTP qua email, xác nhận thành công, outbox retry và giao diện lịch sử. Payment
có JWT/ownership, tích hợp REST và phục hồi giao dịch; UI dùng gateway cùng origin.
Docker mặc định nhận thư tại Mailpit để demo, có thể cấu hình SMTP thật.
Đã nghiệm thu tải, mất mạng, mất phản hồi sau commit, restart Payment/SQL Server
trên project riêng. Báo cáo PDF, slide PPTX và source ZIP nằm trong `submission/`;
hai thành viên còn lại cần bổ sung trước khi nộp.

## Cấu trúc

```text
services/
  account/           # Xác thực, người dùng, số dư, bút toán
  payment/           # Snapshot, SMTP/OTP, điều phối REST, recovery và outbox
  tuition/           # Sinh viên, hóa đơn học phí
shared/              # Đọc .env và tạo kết nối SQL Server; không chia sẻ model
frontend/            # Giao diện do Account phục vụ tại /ui/
tests/
  unit/              # Kiểm thử tự động, SQLite và kiểm tra khởi động
  integration/       # Kịch bản đồng thời trên SQL Server, chạy chủ động
infra/
  docker/            # Dockerfile và khởi tạo dữ liệu demo
  env/               # Mẫu cấu hình Docker/Tuition
  sql/               # Tạo ba database
scripts/             # Lệnh hỗ trợ phát triển
docs/                # Đánh giá, kế hoạch, thiết kế, API và vận hành
submission/          # Báo cáo, slide, bằng chứng và bản nguồn dự phòng
compose.yaml
start.ps1            # Chạy toàn bộ dự án bằng một lệnh
.env.example
requirements.txt
requirements-dev.txt
```

## Bắt đầu

Chạy toàn bộ dự án bằng **một lệnh** trong PowerShell:

```powershell
.\start.ps1
```

Lệnh tự tạo cấu hình Docker nếu thiếu, khởi động Docker Desktop nếu cần, tạo
DB/dữ liệu demo và chạy SQL Server, ba API cùng Mailpit. Log gom vào terminal
hiện tại; nhấn **Ctrl+C** để dừng. Cần cài Docker Desktop và dùng Linux containers.
Không cần cài Python trên máy nếu chỉ chạy bằng Docker.

Nếu PowerShell chặn script, dùng một lệnh sau (chỉ áp dụng cho tiến trình này):

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Chạy nền bằng `.\start.ps1 -Detached`; kiểm tra môi trường bằng `.\start.ps1 -Check`.
Docker giữ dữ liệu trong volume riêng, không dùng SQL Server cài trên Windows.

### Phát triển bằng Python trên Windows

Lệnh chạy từ thư mục gốc bằng PowerShell. Giữ nguyên `.env` riêng nếu đã có.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Chạy trên Windows với SQL Server: xem [hướng dẫn cài đặt](docs/runbook.md#windows-và-sql-server).

| Thành phần | Địa chỉ cục bộ |
|---|---|
| Giao diện đăng nhập/tài khoản | http://127.0.0.1:8001/ui/ |
| Account Swagger | http://127.0.0.1:8001/docs |
| Payment Swagger | http://127.0.0.1:8002/docs |
| Tuition Swagger | http://127.0.0.1:8003/docs |
| Hộp thư demo Mailpit | http://127.0.0.1:8025 |

Demo Account: `huy` / `HuyDemo_123!`. Demo MSSV: `SV2026001`.
Payment lấy dữ liệu qua REST; tạo giao dịch cần header `Idempotency-Key` UUID.
MSSV demo có hai học kỳ. Mở **Đóng học phí**, tra MSSV, chọn hóa đơn, xác nhận và
lấy OTP trong Mailpit. Biên nhận được gửi sau thành công. **Lịch sử giao dịch**
cho phép tra kết quả hoặc tiếp tục giao dịch đang chờ.

## Tài liệu

- [Đối chiếu yêu cầu và những phần còn thiếu](docs/assessment.md)
- [Kế hoạch bảy ngày, 02–08/11/2026](docs/implementation-plan.md)
- [Kiến trúc hiện tại, kiến trúc mục tiêu, Use Case và ERD](docs/architecture.md)
- [API đã triển khai và hợp đồng request/response](docs/api.md)
- [Bàn giao backend 02–04/11 và kiểm thử SQL Server](docs/backend-delivery.md)
- [Migration và dữ liệu cũ](docs/migrations.md)
- [Bàn giao UI/email ngày 05–06/11 và cách trình diễn](docs/ui-email-delivery.md)
- [Cài đặt, Docker, SMTP và kiểm thử](docs/runbook.md)
- [Nghiệm thu và bàn giao 07–08/11](docs/final-acceptance.md)
- [Báo cáo nguồn có thể biên tập](docs/final-report.md), [kịch bản demo](docs/demo-script.md)
- [Checklist trước khi nộp](docs/submission-checklist.md)
- [Thay đổi đường dẫn sau khi sắp xếp](docs/reorganization.md)
- [Account Service](docs/services/account.md), [Payment Service](docs/services/payment.md), [Tuition Service](docs/services/tuition.md)
