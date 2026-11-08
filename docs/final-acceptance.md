# Nghiệm thu và bàn giao hiện hành — 05/11/2026

Đã đồng bộ bộ nộp với quy tắc trả toàn bộ công nợ, email đã xác minh và không
đăng ký công khai. Báo cáo PDF 14 trang, slide v3 14 trang, Use Case, kiến trúc,
ba ERD và sequence đã xuất lại. Nguồn và builder đi kèm để cập nhật thông tin nhóm.

## Kết quả mới

| Kiểm tra | Kết quả |
|---|---|
| Unit/startup/validation/tracing | 152 passed, một cảnh báo deprecation TestClient |
| Edge desktop/mobile | 26 passed, 0 failed/skipped/flaky |
| Backend SQL concurrency | 8/8 kịch bản đạt |
| OTP và nhất quán sau thành công | 7/7 kịch bản đạt |
| Xác minh quyền sở hữu email | 5/5 kịch bản đạt |
| Tracing qua HTTP thật | 3/3 kiểm tra: một ID xuyên gateway/ba service, log an toàn, ID sai được thay |
| Cài mới/tải/mất reply/ngắt mạng/crash | 7/7 kịch bản đạt |

Project riêng: `ibanking-acceptance-e8467f48`. Image:
`sha256:5bcdeb605378742e19c7a8c1fbdfdf0fa395f251d3ff8aea22d0dcf948daf5c5`. Build dùng cache; volume acceptance mới và giữ lại
sau khi dừng container để đối chiếu. Bằng chứng cũ vẫn nằm ở thư mục từng run;
lượt 3c4a1d9b phát hiện proxy kiểm thử bỏ header tracing, đã sửa và chạy lại.

## Tải và hai tình huống bắt buộc

32 payment trên 8 tài khoản, 16 request process đồng thời,
64 hóa đơn: đúng một debit/UUID, đủ hóa đơn PAID, đúng số dư và
một receipt event. HTTP p50 3.188 giây; p95 5.4
giây; tối đa 5.428 giây. Không dùng phép đo ngắn trên một máy làm SLA.

- Hai khoản 7 triệu tranh số dư 10 triệu: chỉ một debit, cuối 3 triệu.
- Hai người cùng trả công nợ một MSSV: chỉ một giao dịch hoàn tất nhóm hóa đơn.
- Mất reply sau debit/finalize, ngắt mạng, SIGKILL Payment và SQL đều được audit.

## Trình diễn và giới hạn còn lại

Dùng `start.ps1 -PrepareDemo -Detached` để chạy ứng dụng và bổ sung catalog còn thiếu, giữ dữ
liệu hiện có. Xác minh email trước nếu dùng tài khoản mới; không tự công nhận
email seed là đã xác minh. Kịch bản: `demo-script.md`, `pre-submit.md`.
Header X-Request-ID và log JSON: `observability.md`.

Thông tin hai thành viên và phân công cần nhóm điền. PDF đã render đủ từng
trang; PPTX qua kiểm tra cấu trúc/geometry/font/import và xem từng slide. Chưa
mở trên PowerPoint của máy trình chiếu. SMTP test chỉ vào Mailpit riêng; cấu
hình SMTP Internet của demo được giữ. Correlation ID chưa phải full W3C tracing.
SQL login tối thiểu quyền/TLS/rate limit là phần triển khai công khai ngoài bài.

Kết quả tổng hợp: `artifacts/acceptance-summary.json` và
`artifacts/acceptance-summary.json`; source ZIP có manifest,
hash và kiểm tra không chứa bí mật cấu hình.
