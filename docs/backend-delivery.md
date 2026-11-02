# Bàn giao công việc ngày 02–04/11

Tài liệu lưu mốc backend ban đầu. OTP console và phần UI/email mô tả bên dưới
đã được thay bằng SMTP/giao diện thật ở [mốc 05–06/11](ui-email-delivery.md).
Hợp đồng đang chạy xem tại [API](api.md).

Thực hiện ngày 02/11/2026, hoàn thành sớm các đầu việc của ba ngày đầu.

| Mốc kế hoạch | Đã thực hiện | Vị trí chính |
|---|---|---|
| 02/11 — Hợp đồng/schema/thiết kế | UUID chung, PaymentItem, snapshot một/tất cả hóa đơn, tiền tính tại server; Use Case/ERD/API và Docker | `services/payment/models`, `schemas.py`, `docs/architecture.md`, `docs/api.md` |
| 03/11 — Tuition/concurrency/migration | Reserve/finalize/release/status nhóm nguyên tử; khóa SQL Server; fingerprint/version; dấu hủy chặn request muộn; migration tiến lên | `services/tuition/internal_routes.py`, `models.py`, `migrate.py`, `shared/locking.py` |
| 04/11 — Payment tích hợp/phục hồi | JWT/ownership; REST Account/Tuition; bỏ model giả; lưu phase; worker phục hồi; cancel/refund có fence | `services/payment/routes.py`, `clients.py`, `coordinator.py`, `recovery.py`, `services/account/internal_routes.py` |

## Cách thử qua Swagger

1. Chạy `.\start.ps1` hoặc `.\start.ps1 -Detached`.
2. Account Swagger `http://127.0.0.1:8001/docs`: đăng nhập `huy` / `HuyDemo_123!`.
3. Tuition Swagger `http://127.0.0.1:8003/docs`: Authorize bằng JWT, tra MSSV `SV2026001` để lấy ID/phiên bản hiện tại.
4. Payment Swagger `http://127.0.0.1:8002/docs`: Authorize bằng cùng JWT. Tạo payment với `Idempotency-Key` UUID mới, MSSV và SELECTED/ALL_UNPAID.
5. Kiểm tra danh sách và tổng tiền trả về, gọi send-otp. Docker hiện dùng OTP demo ở log Payment; xem bằng `docker compose --env-file infra/env/docker.env logs --tail 30 payment`.
6. Gọi verify-otp với `challenge_id` được trả về và mã demo, sau đó gọi process cùng UUID.
7. Đọc trạng thái/lịch sử. Gửi lại process cùng mã không trừ tiền lần hai.

Tạo UUID bằng `[guid]::NewGuid().ToString()` trong PowerShell. Khi timeout hoặc
202, tra cứu/retry cùng mã; không tạo giao dịch khác để thử lại khoản đang xử lý.
Nếu đã đóng hết demo, dùng dữ liệu IT hoặc tạo sinh viên/hóa đơn demo mới, không
reset thủ công hóa đơn đã trả vì sẽ làm sai lịch sử.

## Kiểm thử đã đạt

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m tests.integration.backend_acceptance
```

Pytest: **21 passed**, một cảnh báo Starlette/TestClient về httpx. SQLite trong
bộ nhớ dùng cho các service; kiểm thử logic không chứng minh locking của SQL Server.

Nghiệm thu SQL Server Docker: **7/7 đạt**:

| Kịch bản | Kết quả đối chiếu |
|---|---|
| JWT/ownership, trả một hóa đơn rồi toàn bộ còn lại | Người khác không xem được UUID; balance giảm đúng các khoản chọn; retry không trừ thêm |
| Hai giao dịch 7 triệu trên cùng số dư 10 triệu | Một SUCCEEDED, một FAILED; balance 3 triệu; một DEBIT |
| Hai người cùng trả một hóa đơn | Một người thành công; người còn lại không mất tiền |
| Hai nhóm có hóa đơn giao nhau | Chỉ một nhóm thành công toàn bộ; phần riêng của nhóm thua vẫn UNPAID |
| 5 process cùng UUID đồng thời | Một khoản DEBIT và một nhóm PAID; các request đọc cùng kết quả cuối |
| Cancel/release đến trước request gốc | Debit/reserve đến muộn bị fence, balance không đổi |
| Restart Payment sau các remote commit | Tiếp tục từ RESERVE/DEBIT/FINALIZE đã lưu; mỗi payment chỉ một DEBIT và đúng tổng |

JSON kết quả: `artifacts/backend-acceptance.json` (bị Git bỏ qua). Integration chỉ
dùng SQL Server Docker `127.0.0.1,14330`, đọc cấu hình demo riêng; tạo dữ liệu IT_*
và giữ lại ledger để đối chiếu. Kịch bản restart dừng/chạy lại riêng container
Payment; không chạy khi có giao dịch demo khác đang được trình diễn.

Unit test mất phản hồi sau commit được mô phỏng tại lớp REST. Integration dựng
trạng thái crash từ side effect đã commit rồi restart Payment thật; chưa phải
thử mọi dạng phân hoạch mạng hay SQL Server bị tắt giữa transaction.

## Phạm vi còn lại

- **05/11:** SMTP thật/Mailpit và outbox email xác nhận. OTP hiện chỉ demo console,
  có ràng buộc snapshot, hạn, giới hạn gửi/sai và dùng một lần.
- **06/11:** giao diện đóng học phí và lịch sử; UI hiện vẫn là trang đăng nhập/tài khoản.
- **07–08/11:** thử tải/lỗi hạ tầng/email, xuất sơ đồ và chuẩn bị báo cáo/slides.

Không tự đổi trạng thái tài chính sang thành công/thất bại nếu kết quả upstream
chưa rõ. Dữ liệu bị sửa thủ công hoặc lỗi cấu hình lâu dài có thể giữ giao dịch ở
PENDING_RECONCILIATION; cần xem UUID/phase/log, sửa nguyên nhân rồi cho worker thử lại.
