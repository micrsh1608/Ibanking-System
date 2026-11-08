# Đối chiếu mục 1 — Đăng nhập và thông tin người dùng, 04/11/2026

Ngày 05/11, người dùng yêu cầu xóa dữ liệu demo cũ và để bảng trống để tự tạo
lại. Các số liệu 64 user/69 giao dịch bên dưới thuộc lượt kiểm tra ngày 04/11,
không phải dữ liệu hiện tại. Xem [reset/tạo lại từ đầu](demo-data-reset.md).

Nguồn đối chiếu là ảnh mục 1 người dùng cung cấp: username/password; quản lý
họ tên, số điện thoại, email, số dư khả dụng và lịch sử; sau đăng nhập truy cập
Thanh toán học phí. Theo xác nhận phạm vi của người dùng, đã bỏ chức năng đăng
ký tài khoản mới khỏi giao diện, API và OpenAPI. Dùng tài khoản được cấp; giữ
chức năng cập nhật hồ sơ/email và toàn bộ tài khoản, số dư, lịch sử hiện có.

## Kết quả theo từng yêu cầu

| Yêu cầu đề bài | API / lưu trữ | Giao diện |
|---|---|---|
| Đăng nhập username/password | `POST /auth/login`; so sánh hash Argon2, cấp JWT đúng chủ. Không tồn tại/sai mật khẩu cùng lỗi 401; user vô hiệu hóa 403. | Form tên đăng nhập/mật khẩu; thông báo lỗi, xóa mật khẩu sau yêu cầu; chỉ mở dashboard khi lấy đủ hồ sơ và tài khoản. |
| Họ và tên | `users.full_name`, `GET /users/me` | Thông tin cá nhân, lời chào và người nộp học phí. |
| Số điện thoại | `users.phone`, `GET /users/me` | Thông tin cá nhân và người nộp. Hồ sơ cũ thiếu dữ liệu hiện Chưa cập nhật; có form bổ sung và chặn xác nhận thanh toán khi thiếu/sai định dạng. |
| Địa chỉ email | `users.email`, `GET /users/me` | Thông tin cá nhân và email nhận OTP/biên nhận; giao dịch lấy email snapshot từ Account bằng JWT. |
| Số dư khả dụng | `accounts.balance` NUMERIC(18,2), `GET /accounts/me` theo chủ JWT | Tổng quan và trang thanh toán; hiển thị tiền chính xác từ chuỗi Decimal, có nút ẩn/hiện. Form người dùng không sửa số dư. |
| Lịch sử đã thực hiện | `payments` / `payment_items`, `GET /api/v1/payments` lọc payer theo JWT, có phân trang | Lịch sử giao dịch: thời gian, mã, sinh viên, số tiền, trạng thái và chi tiết. Có thông báo khi chưa có giao dịch; cũng hiển thị giao dịch đang chờ để tiếp tục. |
| Truy cập thanh toán sau đăng nhập | API công khai Payment/Tuition yêu cầu JWT; `/me` chỉ lấy chủ đăng nhập | Menu Đóng học phí xuất hiện trong dashboard, người trả điền tự động và chỉ đọc tại màn hình thanh toán. |

## Sửa trong lượt rà soát

- Chuẩn hóa username trim/lowercase ở backend đăng nhập và tìm không phân biệt
  hoa/thường, không phụ thuộc collation SQL Server.
  Không trim hoặc đổi hoa/thường của mật khẩu. Kiểm thử trước sửa tái hiện lỗi
  trên DB phân biệt hoa/thường và username có khoảng trắng qua API.
- Hash mật khẩu lưu không nhận diện được trước đây làm lỗi server. Hiện từ
  chối bằng lỗi 401 chung và vẫn thực hiện kiểm tra hash giả; không so sánh mật
  khẩu rõ hay tự đổi dữ liệu mật khẩu cũ.
- Khi lưu hồ sơ gặp 401, giao diện xóa token, thông tin cá nhân, số dư và lịch
  sử, rồi yêu cầu đăng nhập lại. Với 403, kiểm tra lại Account: người dùng bị
  vô hiệu hóa được thoát phiên; sai mật khẩu xác nhận vẫn được sửa/thử lại.

Token và OTP chỉ nằm trong bộ nhớ trình duyệt. Logout xóa dữ liệu hiển thị và
UUID khôi phục trên trình duyệt này; không tuyên bố thu hồi mọi JWT đã phát ở
thiết bị khác. Profile/email/account/balance không được chọn bằng user ID do
client tự gửi. JWT hết hạn/sai chữ ký/sai issuer hoặc audience bị từ chối.

## Kiểm chứng

97 pytest đã đạt, gồm 18 trường hợp mới về đăng nhập, hồ sơ, số dư, JWT và lịch
sử. Đã tái hiện 4 lỗi trước sửa ở bài chuẩn hóa username/hash không hợp lệ;
sau sửa toàn bộ unit test đạt. Bộ mới kiểm tra:

- Username thường/hoa/có khoảng trắng; mật khẩu giữ nguyên khoảng trắng.
- Sai mật khẩu, không có user, hash không hợp lệ, user bị vô hiệu hóa.
- Thiếu token, token hỏng, hết hạn, chữ ký/issuer/audience sai, thiếu exp và sub sai.
- Chỉ xem đúng hồ sơ/số dư/lịch sử của chủ JWT; không mở chi tiết hoặc cursor
  lịch sử của người khác; số dư sau thanh toán phản ánh giao dịch đã hoàn tất.

Bài kiểm tra bỏ đăng ký xác nhận không có form/nút, API trả 404 và không tạo
bản ghi. Bài lưu hồ sơ dùng tài khoản được chuẩn bị sẵn, đối chiếu số dư không
đổi sau khi lưu và đăng nhập lại.

Sáu bài Edge tại `tests/e2e/login-requirements.spec.cjs` kiểm tra đăng nhập
sai/đúng, đủ thông tin và menu thanh toán, user vô hiệu hóa, phiên hết hạn khi
lưu hồ sơ, chuyển tài khoản khi phản hồi cũ về muộn, và lỗi tải số dư lúc đăng
nhập. Toàn bộ nghiệm thu SQL/email/giao diện chạy trên Docker/Mailpit riêng;
không dùng email giả để gửi ra SMTP Internet.

Lượt Docker `d6344264` đã đạt đầy đủ, build dùng cache với volume mới:

| Bộ kiểm tra | Kết quả | Bằng chứng |
|---|---|---|
| Pytest nghiệp vụ và migration | 97 đạt, một cảnh báo thư viện TestClient/httpx | `tests/unit/` |
| Edge toàn bộ luồng tài khoản/thanh toán | 21 đạt, không lỗi hoặc flaky; gồm 6 bài đăng nhập mới | `artifacts/browser-acceptance.json` |
| SQL Server: quyền sở hữu, đồng thời, retry, SMTP lỗi | 8 kịch bản đạt | `artifacts/backend-acceptance.json` |
| SQL Server: OTP và thành công/biên nhận | 7 kịch bản đạt | `artifacts/otp-consistency-acceptance.json` |
| Cài mới, tải và phục hồi sự cố | 7 kịch bản đạt | `artifacts/release/d6344264/acceptance.json` |

Ảnh đối chiếu: `artifacts/account-login-invalid.png` và
`artifacts/account-login-profile.png`. Lượt nghiệm thu tải đồng thời vẫn đối
chiếu trực tiếp số dư, bút toán, học phí và lịch sử ở cả ba DB sau khi kết thúc.

Ứng dụng chính đã cập nhật qua `start.ps1 -Detached`; UI và cả ba `/health/db`
trả HTTP 200. Hash trước/sau của hồ sơ/username/hash mật khẩu, số dư, bút toán,
hóa đơn và lịch sử đều khớp; hash `.env` và cấu hình Docker/SMTP riêng cũng
khớp. Có 64 người dùng và 69 giao dịch được giữ nguyên ở thời điểm kiểm tra.
Các đối chiếu chỉ lưu số lượng/hash tại `artifacts/registration-removal-*.json`,
không đưa dữ liệu người dùng hoặc cấu hình riêng vào source ZIP.

Chạy lại:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m tests.integration.release_acceptance --cached-build --full-checks
```

Mã chính: `services/account/routes.py`, `schemas.py`, `security.py`,
`dependencies.py`, `frontend/app.js`, `frontend/account-forms.js` và
`services/payment/routes.py`. Không đổi schema hoặc reset dữ liệu ở lượt này.
Các số liệu PDF/PPTX cũ thuộc mốc trước; tài liệu đối chiếu này và API/OpenAPI
là phần cập nhật cho mục 1.
