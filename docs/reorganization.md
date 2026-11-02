# Sắp xếp mã nguồn

Thực hiện ngày 01/11/2026. Phân chia theo quyền sở hữu nghiệp vụ, không chia theo
những tên thư mục chung như `app/db` dùng lẫn nhiều service.

| Trước | Sau |
|---|---|
| `app/main.py`, models, routes, security và dependencies của Account | `services/account/` |
| `app/init_db.py` | `services/account/seed.py` |
| `main.py` chứa Payment app | `services/payment/main.py` |
| `app/api/payments.py` | `services/payment/routes.py` |
| `app/db/database.py`, `app/db/init_db.py` | `services/payment/database.py`, `init_db.py` |
| `app/payment_models/` | `services/payment/models/` |
| `app/payment_schemas/payment.py` | `services/payment/schemas.py` |
| `app/services/otp_service.py` | `services/payment/otp.py` |
| `tuition_service/` | `services/tuition/` |
| `Front-end/` | `frontend/` |
| `checks/test_concurrency.py` | `tests/integration/account_concurrency.py` |
| `tests/test_tuition_api.py` | `tests/unit/test_tuition_api.py` |
| `scripts/create_tuition_db.sql` | `infra/sql/003_create_tuition_db.sql` |
| `.env.tuition.example` | `infra/env/tuition.env.example` |
| README cũ của Account/Tuition | `docs/services/account.md`, `tuition.md` |

Import, đường dẫn đọc `.env`, đường dẫn static và hướng dẫn chạy đã đổi theo cấu trúc mới.
`main.py` ở gốc chỉ giữ entry point tương thích `uvicorn main:app` cho Payment.
Các entry point `app.main:app` và `tuition_service.main:app` phải đổi theo bảng trên.

`shared/` chỉ chứa cấu hình/kết nối; mỗi service giữ engine, session và metadata riêng.
Kết nối bổ sung SQL Authentication cho Linux/Docker; Windows Authentication tiếp tục
hoạt động khi không đặt `DB_USER`. Không di chuyển hay sửa giá trị trong `.env` riêng.

Dependency runtime được rút về những thư viện dùng trực tiếp, ghim phiên bản theo
môi trường đã cài. Dependency kiểm thử nằm trong `requirements-dev.txt`.
Các cache Python từng nằm trong Git được bỏ khỏi cây mã nguồn.
Những lỗi nghiệp vụ Payment được ghi vào kế hoạch, chưa thay đổi luồng thanh toán ở bước này.
