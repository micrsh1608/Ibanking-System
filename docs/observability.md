# Truy vết request qua ba service

Ba service dùng `shared/observability.py`. Mỗi HTTP response có `X-Request-ID`.
Header UUID hợp lệ từ client được giữ lại; giá trị thiếu/sai được thay bằng
UUID mới. Gateway và REST client của Payment truyền header này xuống service
đích. ContextVar tách request chạy đồng thời; worker recovery tạo context riêng
và dùng payment_id để nối các lần thử.

Log JSON có timestamp UTC, service, event, request_id, method, route mẫu,
status và duration_ms. Sự kiện payment_state có payment_id/status/phase sau khi
commit. Không đọc request body để log; query, JWT, OTP, email, mật khẩu và nội
dung exception không nằm trong log cấu trúc. Route không khớp ghi `unmatched`.
Access log mặc định của Uvicorn là luồng log riêng, không phải schema JSON này.
Lỗi thiết bị ghi log không thay đổi kết quả nghiệp vụ.

Ví dụ PowerShell để đối chiếu một request, không có thao tác thanh toán:

```powershell
$requestId = [Guid]::NewGuid().ToString()
Invoke-WebRequest http://127.0.0.1:8001/health -Headers @{ 'X-Request-ID'=$requestId }
docker compose --env-file infra/env/docker.env logs --no-color --no-log-prefix account payment tuition | Select-String -SimpleMatch $requestId
```

Trong buổi demo, DevTools → Network → chọn request thanh toán → Response
Headers → sao chép X-Request-ID, rồi lọc log như trên. Có thể lọc payment_id để
theo dõi phase RESERVE/DEBIT/FINALIZE/DONE và các lần recovery. Không xuất token
hoặc mã OTP từ DevTools vào ảnh/bản nộp.

Kiểm thử: `tests/unit/test_observability.py` kiểm tra ba app, header invalid,
isolation tám request đồng thời, error/log redaction, gateway/internal key,
REST propagation và lỗi logger. `tests/integration/observability_acceptance.py`
kiểm tra gateway → Payment → Account/Tuition bằng HTTP thật trên project riêng.
Bài này được gọi tự động bởi release acceptance `--full-checks`.

Đây là request correlation với structured logging; chưa cài collector,
dashboard hoặc chuẩn span W3C/OpenTelemetry. Dùng request_id và payment_id để
giải thích cách truy vết trong phạm vi bài giữa kỳ.
