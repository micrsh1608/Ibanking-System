# Migration và dữ liệu cũ

Mỗi database có bảng `schema_revisions(revision, applied_at)`. Runner ở
`shared/migrations.py` dùng application lock trong transaction SQL Server để
tránh hai tiến trình nâng cấp đồng thời. Các revision đã áp dụng được bỏ qua.
Không có thao tác drop/reset dữ liệu trong migration này.

| Database | Revision | Thay đổi |
|---|---|---|
| account_db | `20261104_account_cancellation` | Tạo các bảng Account còn thiếu và `account_cancellations` |
| tuition_db | `20261102_tuition_reservations` | Tạo bảng nhóm giữ hóa đơn và chi tiết nhóm |
| tuition_db | `20261103_invoice_version` | Thêm `version` mặc định 1 cho bảng hóa đơn cũ nếu chưa có |
| payment_db | `20261102_payment_snapshots` | Tạo `payments` và `payment_items` cho UUID/snapshot/OTP/recovery |
| payment_db | `20261105_email_outbox` | Tạo `email_outbox`, thêm `completed_at`, giữ lịch sử hiện có |

Chạy Windows từ thư mục gốc sau khi cấu hình `.env`:

```powershell
.\.venv\Scripts\python.exe -m services.account.migrate
.\.venv\Scripts\python.exe -m services.tuition.migrate
.\.venv\Scripts\python.exe -m services.payment.migrate
```

Docker tự gọi migration trước seed qua `db-init` khi chạy `start.ps1`.
Seed giữ số dư, trạng thái hóa đơn và dữ liệu đang có. Demo Tuition có hai kỳ,
2 triệu và 3 triệu; chỉ thêm kỳ chưa tồn tại, không chuyển hóa đơn PAID về UNPAID.

Prototype Payment từng có `payment_transactions`, `accounts`, `tuition_fees`
trong `payment_db`. Các bảng này được giữ nguyên nhưng API mới không đọc chúng.
Không tự chuyển lịch sử prototype: payer/student ID cũ không có ánh xạ đáng tin
cậy sang Account/MSSV/hóa đơn thật. Nếu cần nhập lịch sử cũ, phải lập bảng ánh xạ
và kiểm tra ledger/hóa đơn trước khi viết revision nhập dữ liệu riêng.

Khi thay đổi schema lần sau, thêm revision mới; không sửa revision đã chạy.
`create_all()` không tự sửa cột/ràng buộc của bảng hiện có. Khi triển khai ngoài
demo, sao lưu DB và chạy migration trong đợt cập nhật có kiểm soát.

Kiểm tra đã thực thi, trong từng DB:

```sql
SELECT revision, applied_at FROM schema_revisions ORDER BY applied_at;
```

Pytest kiểm tra nâng cấp bảng Tuition cũ, chạy lặp, giữ dữ liệu và giữ các bảng
Payment prototype. Bản nâng cấp cũng đã chạy trên SQL Server Docker đang có dữ liệu.

Revision email không tự gửi biên nhận cho các payment đã thành công trước khi
nâng cấp. Thời gian hoàn tất lịch sử được lấy từ updated_at nếu chưa có.
