# Account Service

Dịch vụ quản lý người dùng, tài khoản ngân hàng và biến động số dư
trong hệ thống thanh toán học phí iBanking.

## Công nghệ

- Python, FastAPI
- SQLAlchemy, SQL Server
- Microsoft ODBC Driver 18, pyodbc
- JWT và Argon2
- HTML, CSS, JavaScript

## Chuẩn bị

1. Cài Python và Microsoft ODBC Driver 18 for SQL Server.
2. Tạo database account_db trong SQL Server.
3. Tạo môi trường ảo và cài thư viện:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

4. Copy .env.example thành .env.
5. Điền tên SQL Server.
6. Tạo JWT_SECRET_KEY ngẫu nhiên.
7. Cấu hình INTERNAL_API_KEY thống nhất với Payment Service.

Kết nối SQL Server hiện sử dụng Windows Authentication.
Tài khoản Windows chạy chương trình phải có quyền truy cập database.

## Tạo dữ liệu mẫu

```powershell
.\.venv\Scripts\python.exe -m app.init_db
```

Tài khoản demo:
- Username: huy
- Password: HuyDemo_123!

## Chạy service

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8001
```

- Giao diện: http://127.0.0.1:8001/ui/
- Swagger: http://127.0.0.1:8001/docs
- OpenAPI: http://127.0.0.1:8001/openapi.json
- Kiểm tra DB: http://127.0.0.1:8001/health/db

## API người dùng

| Method | Endpoint | Xác thực |
|---|---|---|
| POST | /auth/login | Không |
| GET | /users/me | Bearer token |
| GET | /accounts/me | Bearer token |

POST /auth/login nhận JSON:

```json
{
  "username": "huy",
  "password": "HuyDemo_123!"
}
```

Các API được bảo vệ nhận header:

```text
Authorization: Bearer <access_token>
```

## API nội bộ

Tất cả API nội bộ yêu cầu header:

```text
X-Internal-Key: <khóa dùng chung với Payment Service>
```

| Method | Endpoint |
|---|---|
| POST | /internal/accounts/debit |
| POST | /internal/accounts/refund |
| GET | /internal/account-operations/{payment_id} |

Request trừ tiền:

```json
{
  "payment_id": "11111111-1111-4111-8111-111111111111",
  "account_id": 1,
  "payer_user_id": 1,
  "amount": "2000000.00"
}
```

Request hoàn tiền:

```json
{
  "payment_id": "11111111-1111-4111-8111-111111111111"
}
```

Response thành công có:
payment_id, account_id, amount, status.

Trạng thái:
- DEBITED: khoản trừ tiền đã được ghi nhận.
- REFUNDED: khoản trừ tiền đã được hoàn.

## Quy tắc tích hợp

- payment_id dùng UUID.
- Gửi lại yêu cầu phải giữ nguyên payment_id và dữ liệu.
- Một payment_id không được dùng cho khoản thanh toán mới.
- Giao dịch đã hoàn không được trừ lại.
- Amount truyền bằng chuỗi thập phân.
- Payment Service kiểm tra OTP và lấy số tiền từ Tuition Service.
- payer_user_id phải lấy từ danh tính đã xác minh.
- Không đưa khóa API nội bộ vào trình duyệt.
- Timeout hoặc HTTP 503: tra cứu, thử lại có giới hạn bằng cùng mã.
- HTTP 404 khi tra cứu chưa chứng minh một yêu cầu đang chạy
  sẽ không hoàn tất sau đó.

## Mã lỗi chính

- 401: thiếu/sai thông tin xác thực.
- 403: người dùng bị vô hiệu hóa hoặc sai chủ tài khoản.
- 404: chưa tìm thấy tài khoản hoặc khoản trừ tiền.
- 409: không đủ số dư, tài khoản khóa hoặc xung đột dữ liệu.
- 422: dữ liệu đầu vào không hợp lệ.
- 503: chưa xác định được kết quả do lỗi database.

## Kiểm thử đồng thời

Giữ server đang chạy, mở terminal khác:

```powershell
.\.venv\Scripts\python.exe -m checks.test_concurrency
```

Chương trình tạo hai tài khoản thử riêng và kiểm tra:
1. Trừ tiền trùng.
2. Cùng mã nhưng khác số tiền.
3. Hoàn tiền trùng và gửi lại giao dịch đã hoàn.
4. Hai giao dịch cùng sử dụng một số dư không đủ cho cả hai.

## Phạm vi hiện tại

- Giao diện đăng nhập và xem tài khoản đã được kết nối API.
- Đăng xuất chỉ xóa token ở trình duyệt, chưa thu hồi JWT trên server.
- Cần kiểm thử phục hồi lỗi khi tích hợp với Payment Service.