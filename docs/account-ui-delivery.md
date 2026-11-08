# Hồ sơ người dùng, email và truy cập thanh toán

Phạm vi theo đề bài: đăng nhập bằng username/password của tài khoản đã được cấp.
Không có đăng ký tài khoản mới trên giao diện, API hay OpenAPI. Không xóa các
người dùng/tài khoản đã có. Đối chiếu chi tiết và số liệu nghiệm thu hiện tại ở
[đăng nhập và thông tin người dùng](login-user-requirements-review.md).

## Mở và sử dụng

Chạy `powershell -ExecutionPolicy Bypass -File .\start.ps1`, mở
**http://127.0.0.1:8001/ui/**. Dùng tài khoản demo `huy` / `HuyDemo_123!`,
hoặc thông tin đã được cấp. Không mở HTML trực tiếp từ ổ đĩa.

- **Tổng quan:** số tài khoản, trạng thái, số dư khả dụng và ẩn/hiện số dư.
- **Thông tin cá nhân:** họ tên, username, email, điện thoại, CCCD. Chọn Cập nhật
  thông tin và nhập mật khẩu hiện tại để lưu; không sửa username, số tài khoản,
  trạng thái hoặc số dư qua form này. Mật khẩu xác nhận được xóa sau yêu cầu.
- **Đóng học phí:** tra MSSV, kiểm tra toàn bộ công nợ, đồng ý điều khoản và xác
  nhận. Hệ thống tự gửi OTP; nhập mã để thanh toán và xem kết quả/biên nhận.
- **Lịch sử giao dịch:** chỉ của chủ đang đăng nhập, có chi tiết và tiếp tục
  giao dịch đang chờ. Đăng xuất xóa thông tin hiển thị và UUID khôi phục cục bộ.

`POST /auth/register` trả 404 và không ghi dữ liệu. Tài khoản mới cho môi trường
trình diễn được chuẩn bị qua seed/quản trị dữ liệu, không do người dùng tự tạo
trong ứng dụng. Không có API tự nạp tiền; số dư và hóa đơn đã trả giữ qua restart.

## Email và cập nhật hồ sơ

`PUT /users/me` xác thực đúng chủ JWT và mật khẩu hiện tại. Sai mật khẩu trả
403 và cho thử lại. Hết phiên trả 401, giao diện xóa phiên và yêu cầu đăng nhập.
Điện thoại/email sai định dạng hoặc trường ID/tiền/trạng thái ngoài whitelist
bị từ chối. Hồ sơ thiếu điện thoại phải bổ sung trước khi xác nhận học phí.

Đổi email hoặc xác minh địa chỉ hiện tại: nhấn Lưu → nhận mã ở địa chỉ đó →
nhập trong mục Xác minh địa chỉ email → Xác minh và lưu hồ sơ. Trước bước cuối,
hồ sơ/email đang dùng chưa đổi. Có gửi lại mã, hủy yêu cầu và khôi phục yêu cầu
chờ sau đăng nhập lại. Chi tiết tại [xác minh email](email-verification.md).

Chỉ email đã xác minh được dùng cho thanh toán. Giao dịch chờ dùng địa chỉ cũ
sau khi đổi email cần tạo lại; lịch sử đã hoàn tất được giữ nguyên.

Docker mặc định nhận thư ở **Mailpit http://127.0.0.1:8025**. Hồ sơ có thông báo
chế độ gửi thư qua `GET /app-config`; API này không trả host, tài khoản hay mật
khẩu SMTP. Gửi Internet cần cấu hình riêng theo [runbook](runbook.md), giữ tệp
`infra/env/docker.env` ngoài Git/ZIP. Các kiểm thử hư cấu luôn dùng Mailpit riêng.

Kiểm thử hiện tại xác nhận không có form/API đăng ký, lưu hồ sơ qua đăng nhập
lại, số dư giữ nguyên, từ chối sửa tiền/ID, cách ly hai người dùng, layout mobile
và OTP/biên nhận gửi đúng email sau cập nhật.
