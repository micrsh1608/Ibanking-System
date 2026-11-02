# Payment Service

Sở hữu `payments`, `payment_items` và trạng thái điều phối trong `payment_db`.
Không đọc DB Account/Tuition; model giả đã bỏ khỏi mã chạy. Các bảng prototype
cũ được giữ nguyên trong DB theo [chính sách migration](../migrations.md).

```powershell
.\.venv\Scripts\python.exe -m services.payment.init_db
.\.venv\Scripts\python.exe -m uvicorn services.payment.main:app --reload --port 8002
```

Cách chạy chung: `.\start.ps1`. JWT Account bảo vệ toàn bộ API nghiệp vụ; UUID và
idempotency key nối snapshot, ledger Account và reservation Tuition. Mọi lần
đọc/gửi OTP/process đều kiểm tra đúng chủ; tiền và người trả không do client nhập.

Worker recovery chạy trong lifespan của app, quét mỗi 5 giây và tiếp tục từ
phase đã commit. Tắt trong unit test bằng `PAYMENT_RECOVERY_ENABLED=false`.
Có thể chạy đối soát một lượt bằng `python -m services.payment.recovery --once`.
SQL session application lock theo UUID ngăn hai coordinator chạy cùng lúc.

OTP được gửi bằng SMTP; mã HMAC chỉ dùng một lần và không in ra log. Worker
email độc lập gửi biên nhận từ email_outbox, retry khi lỗi mà không chạy lại
thanh toán. Cấu hình qua SMTP_HOST/PORT/USERNAME/PASSWORD/SSL/STARTTLS/FROM,
Docker mặc định trỏ Mailpit. PAYMENT_MAIL_ENABLED=false chỉ dùng trong unit test.
Xem [API](../api.md) và [UI/email](../ui-email-delivery.md).
