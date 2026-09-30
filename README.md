# TV2 - Tuition & OTP Microservice

Phần hiện thực của thành viên TV2 trong đề tài:

> Phân hệ đóng học phí của ứng dụng iBanking

## 1. Chức năng

TV2 phụ trách:

- UC04 - Xem thông tin học phí.
- UC05 - Chọn khoản học phí (phía dữ liệu/UI hỗ trợ; không cần API riêng).
- UC07 - Gửi OTP.
- UC08 - Xác thực OTP.
- UC10 - Cập nhật trạng thái học phí.

## 2. Công nghệ

- Python 3.12
- FastAPI
- SQLAlchemy
- SQLite cho demo
- SMTP cho email thật
- Docker

## 3. Chạy local

### Windows

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Tạo `.env`:

```bash
copy .env.example .env
```

Tạo dữ liệu mẫu:

```bash
python seed.py
```

Chạy:

```bash
uvicorn app.main:app --reload --port 8002
```

Mở:

```text
http://localhost:8002/docs
```

Demo UI:

```text
http://localhost:8002/demo/index.html
```

## 4. OTP demo

Nếu chưa cấu hình SMTP, hệ thống chạy DEMO mode.

Sau khi gọi `/api/v1/otp/send`, OTP sẽ được in ở terminal:

```text
[DEMO EMAIL] to=an@gmail.com | transaction=TX001 | OTP=123456 | expires=300s
```

Dùng mã đó để gọi `/api/v1/otp/verify`.

## 5. Docker

```bash
copy .env.example .env
docker compose up --build
```

API:

```text
http://localhost:8002/docs
```

## 6. Test

```bash
pytest -q
```

## 7. Dữ liệu mẫu

```text
52200001 / an@gmail.com / 12,500,000
52200002 / binh@gmail.com / 9,800,000
52200003 / cuong@gmail.com / 15,000,000
```

## 8. Khi ghép với TV3

TV3 gọi:

```http
PATCH /api/v1/internal/tuition/{mssv}/paid
```

Body:

```json
{
  "transaction_id": "TX001"
}
```

TV2 chỉ chuyển:

```text
UNPAID -> PAID
```

một lần. Nếu học phí đã PAID, trả HTTP 409.

## 9. Lưu ý tích hợp API Gateway

API Gateway của nhóm có thể route:

```text
/api/v1/tuition/* -> TV2:8002
/api/v1/otp/*     -> TV2:8002
```

API internal:

```text
/api/v1/internal/tuition/*/paid -> TV2:8002
```

Nên giới hạn API internal để chỉ Payment Service của TV3 gọi được trong hệ thống thật.
