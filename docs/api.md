# REST API — thanh toán toàn bộ, email đã xác minh và OTP, cập nhật 07/11/2026

Ba service độc lập, mỗi service có `/docs` và `/openapi.json`.
Money dùng chuỗi thập phân; ngày giờ Payment trả ISO 8601 UTC.
JWT: `Authorization: Bearer <token>`. API nội bộ: `X-Internal-Key`.
Mọi response có `X-Request-ID` UUID để đối chiếu; client có thể gửi UUID hợp lệ
để gateway và các cuộc gọi REST giữ cùng mã. Xem [truy vết](observability.md).

## Account — cổng 8001

| Method/URI | Input | Auth | Output | HTTP lỗi chính |
|---|---|---|---|---|
| `POST /auth/login` | `{username,password}` | Không | 200 `{access_token,token_type}` | 401, 403, 422 |
| `GET /users/me` | Không | JWT | 200 UserResponse gồm hồ sơ, trạng thái email và yêu cầu xác minh chờ | 401, 403 |
| `PUT /users/me` | ProfileUpdate | JWT + mật khẩu hiện tại | 202 UserResponse; lưu bản nháp và gửi mã, hồ sơ đang dùng chưa thay đổi | 401, 403, 409, 422, 429, 503 |
| `POST /users/me/email-verification/confirm` | `{challenge_id,code}` | JWT | 200 UserResponse sau khi xác minh và lưu | 400 sai/hết hạn, 401, 403, 409 đã dùng/sai chủ, 422, 429 |
| `POST /users/me/email-verification/resend` | `{current_password}` | JWT | 202 UserResponse có challenge mới | 401, 403, 409, 422, 429, 503 |
| `DELETE /users/me/email-verification` | Không | JWT | 200, hủy yêu cầu chờ, giữ hồ sơ hiện tại | 401, 403, 409 |
| `GET /app-config` | Không | Không | 200 `{email_delivery:smtp/not_configured,account_email_routing:true}` | Không chứa thông tin đăng nhập SMTP |
| `GET /accounts/me` | Không | JWT | 200 `{id,account_number,balance,status}` | 401, 403, 404 |
| `POST /internal/accounts/debit` | DebitRequest | Internal | 200 Operation | 401, 403 sai chủ, 404, 409 số dư/khóa/dữ liệu, 422, 503 |
| `POST /internal/accounts/refund` | `{payment_id}` | Internal | 200 Operation | 401, 404, 409, 422, 503 |
| `POST /internal/accounts/cancel` | DebitRequest | Internal | 200 Operation | 401, 403, 404, 409 sai dữ liệu, 422, 503 |
| `GET /internal/account-operations/{payment_id}` | UUID | Internal | 200 Operation | 401, 404, 422, 503 |
| `GET /health`, `GET /health/db` | Không | Không | 200 trạng thái app/DB | 503 với DB |

Login trim khoảng trắng đầu/cuối và không phân biệt hoa/thường ở username,
không phụ thuộc collation của database. Mật khẩu giữ nguyên từng ký tự, kể cả
khoảng trắng. Username không tồn tại, mật khẩu sai hoặc hash lưu không được hỗ
trợ đều trả cùng lỗi 401, không cấp token. Người dùng bị vô hiệu hóa trả 403.
JWT có sub/iat/exp/iss/aud; Account xác thực chữ ký, hạn và trạng thái user khi
đọc/cập nhật `/me`. UI chỉ hiện tài khoản sau khi lấy đủ hồ sơ và số dư.
Khi lưu hồ sơ gặp 401, xóa phiên và yêu cầu đăng nhập; 403 được kiểm tra lại với
Account để phân biệt user bị vô hiệu hóa với sai mật khẩu xác nhận.

Không có API đăng ký tài khoản mới. `POST /auth/register` trả 404; dùng tài
khoản được cấp hoặc seed demo. Hồ sơ/số dư/lịch sử đã có được giữ nguyên.
ProfileUpdate ví dụ:

```json
{"current_password":"YourPassword_123!","full_name":"Nguyễn Minh An","email":"your-address@example.com","phone":"0900000001","identity_number":"000000000001"}
```

ProfileUpdate gồm `full_name`, `email`, `phone`, `identity_number` như trên và
`current_password`. PUT thay các trường hồ sơ có thể sửa của **chủ JWT**, không
nhận username/user ID/account number/balance/status; trường lạ trả 422.
Mật khẩu xác nhận sai trả 403, không lưu thay đổi. Không trả password/hash.
Mọi PUT hợp lệ chỉ lưu bản nháp và gửi mã đến email được nhập trong yêu cầu;
trả 202, kể cả chỉ sửa tên/điện thoại và giữ nguyên email đã xác minh.
Email/họ tên/điện thoại/CCCD đang dùng chưa thay đổi.
Confirm đúng mã mới lưu cả hồ sơ và email_verified_at trong cùng transaction.
UserResponse có `email_verified`, `email_delivery` (`smtp` hoặc `not_configured`),
`pending_email`, `email_verification` (UUID,
expires_at UTC, thời gian chờ gửi lại, địa chỉ che bớt). Không trả hash hoặc mã rõ.
Mã 6 số, 5 phút, 5 lần sai, một lần sử dụng; gửi lại sau 60 giây thay mã/challenge.
Đã có email được xác minh thì địa chỉ đó vẫn hoạt động trong khi chờ địa chỉ khác.

Payment yêu cầu `email_verified=true` khi tạo giao dịch và kiểm tra lại khi
gửi/xác minh OTP hoặc bắt đầu process. Email hiện tại phải trùng snapshot;
nếu đã đổi sang email mới, tạo payment mới thay vì gửi đến địa chỉ cũ. Lịch sử
hoàn tất giữ nguyên; giao dịch đã PROCESSING/đối soát tiếp tục khôi phục tài chính.
Xem [luồng xác minh email](email-verification.md).

`GET /app-config` chỉ báo chế độ gửi thư; không lộ SMTP host, user hoặc password.
Ứng dụng chính chỉ dùng SMTP thật. `SMTP_USERNAME`/`SMTP_FROM` cấu hình người
gửi; người nhận lấy từ email của chính user, không được thay bằng địa chỉ SMTP.
Migration `20261107_smtp_only_accounts` chuyển route cũ sang SMTP, yêu cầu các
tài khoản từng xác minh qua Mailpit chứng minh lại hộp thư thật. Không tự gửi thư.

DebitRequest:

```json
{
  "payment_id": "11111111-1111-4111-8111-111111111111",
  "account_id": 1,
  "payer_user_id": 1,
  "amount": "2000000.00"
}
```

Operation: `{payment_id,account_id,amount,status}` với status `DEBITED`, `REFUNDED`
hoặc `CANCELLED`. Cùng UUID khác account/payer/amount trả 409.
`cancel` hoàn khoản đã trừ nếu khớp dữ liệu, hoặc lưu dấu hủy nếu chưa trừ;
request debit đến muộn nhận kết quả CANCELLED/REFUNDED và không trừ lại.
`refund` cũ chỉ áp dụng khi đã có khoản trừ. Coordinator dùng `cancel` để đóng cả cửa sổ request đến muộn.

## Tuition công khai — cổng 8003

`GET /api/v1/tuition/{mssv}` yêu cầu JWT; MSSV dài 1–24 ký tự.
Trả 200, hoặc 401/404/422. `/health` và `/health/db` không yêu cầu JWT.

```json
{
  "mssv": "SV20261013",
  "full_name": "Lê Minh Khang",
  "total_unpaid": "5000000.00",
  "invoices": [
    {"id": 1, "semester": "2026-2027-HK1", "amount_due": "2000000.00", "status": "UNPAID", "version": 1},
    {"id": 2, "semester": "2026-2027-HK2", "amount_due": "3000000.00", "status": "UNPAID", "version": 1}
  ]
}
```

ID ví dụ có thể khác DB đang dùng. `total_unpaid` chỉ cộng UNPAID;
RESERVED là đang xử lý, PAID là đã trả. Người trả có thể đóng cho MSSV khác mình.

## Tuition nội bộ

Tất cả endpoint dưới đây dùng internal key. Mỗi thao tác ghi là một transaction SQL Server.

| Method/URI | Input | Output | HTTP lỗi |
|---|---|---|---|
| `GET /internal/tuition/invoices` | Query `mssv` | 200 TuitionView như trên | 401, 404, 422, 503 |
| `POST /internal/tuition/reservations` | ReserveRequest | 200 ReservationView mới/lặp | 401, 404, 409, 422, 503 |
| `GET /internal/tuition/reservations/{payment_id}` | UUID | 200 ReservationView | 401, 404, 422, 503 |
| `POST /internal/tuition/reservations/{payment_id}/finalize` | Không | 200 cả nhóm PAID, mới/lặp | 401, 404, 409 đã hủy/trạng thái sai, 422, 503 |
| `POST /internal/tuition/reservations/{payment_id}/release` | Không | 200 cả nhóm RELEASED, mới/lặp | 401, 409 đã PAID/trạng thái sai, 422, 503 |

ReserveRequest:

```json
{
  "payment_id": "11111111-1111-4111-8111-111111111111",
  "mssv": "SV20261013",
  "items": [{"invoice_id": 1, "version": 1}, {"invoice_id": 2, "version": 1}],
  "expected_total": "5000000.00"
}
```

ReservationView: `{payment_id,status,mssv,total_amount,invoice_ids}`.
Status: `RESERVED`, `PAID`, `RELEASED`. Release trước reserve tạo dấu hủy với
`mssv=null`, tổng 0 và danh sách rỗng; reserve/finalize đến muộn bị từ chối.
Dấu hủy và thông tin nhóm đã trả được giữ bền vững để retry có kết quả xác định.

Chỉ giữ khi tất cả hóa đơn thuộc cùng MSSV, UNPAID, đúng phiên bản và đúng tổng.
Cùng UUID và cùng payload trả kết quả cũ, kể cả đã PAID. Khác payload trả 409.
Không tự hết hạn/nhả reservation trong khi chưa xác định được kết quả trừ tiền.

## Payment — cổng 8002

Mọi endpoint nghiệp vụ yêu cầu JWT; mọi thao tác với UUID kiểm tra đúng chủ.
Không tìm thấy và không thuộc chủ đều trả 404. Các endpoint prototype nhận
`payer_id`, `student_id` số và `amount` đã được thay thế.

| Method/URI | Input | Output/status | HTTP lỗi chính |
|---|---|---|---|
| `POST /api/v1/payments` | PaymentCreate + header `Idempotency-Key` UUID | 201 PaymentView; 200 nếu lặp cùng dữ liệu | 401, 403 từ Account, 404, 409, 422, 503 |
| `GET /api/v1/payments` | `limit=20` (1–100), `cursor` UUID tùy chọn | 200 `{items:PaymentView[],next_cursor}` | 401, 404 cursor sai chủ, 422, 503 |
| `GET /api/v1/payments/{payment_id}` | UUID | 200 PaymentView | 401, 404, 422, 503 |
| `POST /api/v1/payments/{payment_id}/send-otp` | Không | 202 `{challenge_id,expires_at,resend_after_seconds,delivery_address,demo_mode:false}` | 401, 404, 409, 422, 429, 503 |
| `POST /api/v1/payments/{payment_id}/verify-otp` | `{challenge_id,otp}` | 200 `{payment_id,status:OTP_VERIFIED}` | 400 sai/hết hạn, 401, 404, 409 đã dùng, 422, 429, 503 |
| `POST /api/v1/payments/{payment_id}/process` | Không | 200 SUCCEEDED; 202 đang xử lý/đối soát; 409 FAILED/REFUNDED | 401, 404, 409 chưa xác minh/OTP hết hạn, 422, 503 DB |
| `GET /`, `GET /health`, `GET /health/db` | Không | 200 thông tin/trạng thái | 503 với DB |

PaymentCreate: toàn bộ hóa đơn UNPAID của MSSV và đồng ý điều khoản:

```json
{"mssv": "SV20261013", "selection_mode": "ALL_UNPAID", "terms_accepted": true}
```

Không được gửi thêm `payer_id`, `payer_user_id`, `account_id`, `amount`, `invoice_ids`
hoặc trường khác. `SELECTED` đã bỏ và trả 422. `terms_accepted` bắt buộc là boolean
true; thiếu/false/chuỗi/số đều trả 422. Backend lấy
người trả/tài khoản từ Account bằng JWT, MSSV/hóa đơn/tiền từ Tuition qua REST.
Trước khi tạo, kiểm tra họ tên/điện thoại/email người trả hợp lệ, account ACTIVE,
có 1–100 hóa đơn UNPAID, không có hóa đơn RESERVED và số dư >= tổng tiền; sai điều
kiện trả 409, không tạo payment. MSSV không tồn tại trả 404.
Không tự thêm hóa đơn mới vào giao dịch đã tạo. Khi giữ hóa đơn, Tuition khóa
toàn bộ tập hóa đơn của MSSV và yêu cầu tập UNPAID khớp snapshot; nếu công nợ đổi,
trả 409 để người dùng xác nhận lại toàn bộ. Không giữ tiền ở bước tạo snapshot.

PaymentView ví dụ:

```json
{
  "payment_id": "11111111-1111-4111-8111-111111111111",
  "transaction_code": "TXN-11111111111141118111111111111111",
  "payer_user_id": 1,
  "account_id": 1,
  "mssv": "SV20261013",
  "student_name": "Lê Minh Khang",
  "selection_mode": "ALL_UNPAID",
  "total_amount": "5000000.00",
  "terms_version": "2026-11-03",
  "terms_accepted_at": "2026-11-03T15:00:00+00:00",
  "status": "PENDING_OTP",
  "phase": "RESERVE",
  "items": [{"invoice_id": 1, "invoice_version": 1, "semester": "2026-2027-HK1", "amount": "2000000.00"}, {"invoice_id": 2, "invoice_version": 1, "semester": "2026-2027-HK2", "amount": "3000000.00"}],
  "error_message": null,
  "retry_count": 0,
  "created_at": "2026-11-02T05:00:00+00:00",
  "updated_at": "2026-11-02T05:00:00+00:00"
}
```

Một `Idempotency-Key` thuộc duy nhất một người trả và một payload. Gửi lại cùng
key giữ nguyên snapshot, kể cả hóa đơn đã thay đổi sau đó. Cùng key khác dữ liệu
trả 409; nếu request cùng key đang khởi tạo, thử lại sau bằng key cũ.

## Email và OTP

OTP được gửi bằng SMTP thật đến email đã xác minh được chụp trong snapshot
của người đang đăng nhập. SSL/STARTTLS và login cấu hình qua biến môi trường;
tài khoản SMTP gửi thư không quyết định địa chỉ nhận. Sau khi xác minh email
hồ sơ mới, giao dịch mới lấy địa chỉ mới; bản nháp dùng địa chỉ cũ cần hủy và tạo lại.
Không in OTP vào log, không trả mã OTP trong JSON và không lưu mã rõ trong DB.
Giao diện tự gọi send-otp sau khi xác nhận tạo giao dịch thành công; nếu gửi lỗi,
người dùng thử lại nút Gửi mã trên cùng UUID, không tạo khoản thanh toán mới.

Mã sáu chữ số được HMAC với UUID, challenge, danh sách/phiên bản hóa đơn và tổng tiền;
hạn 5 phút, tối đa 5 lần sai, gửi lại sau 60 giây. Gửi lại hủy xác minh cũ. Xác minh
thành công tiêu thụ mã; process phải bắt đầu trước khi xác minh hết hạn. Giao dịch
đã nhận xử lý tiếp tục được phục hồi dù OTP hết hạn sau đó.

Mã còn hiệu lực không trùng với mã của giao dịch khác. Bộ cấp mã khóa transaction
toàn hệ thống Payment trong SQL Server, kiểm tra dấu vân tay HMAC của mã và sinh
lại khi trùng; filtered unique index `uq_payments_otp_fingerprint` bảo vệ ở DB.
Không trả dấu vân tay qua API. Chỗ dành mã được giữ đến hạn gốc, kể cả mã đã dùng;
mã hết hạn được giải phóng ở lần cấp tiếp theo. Gửi lại cũng không dùng mã trước
của chính giao dịch. Tối đa 128 lượt sinh mã, sau đó trả 503 để thử lại, không gửi
thư hoặc ghi challenge dở dang.

SMTP lỗi trả 503, làm mất hiệu lực challenge vừa cấp và cho phép thử gửi lại.
PaymentView có `active_challenge` (cùng metadata như response send-otp, không có
mã OTP) khi đang chờ xác minh. Chủ giao dịch có thể tải lại trang, đăng nhập và
nhập mã đã nhận, không cần tạo giao dịch hoặc gửi email mới.

PaymentView bổ sung `completed_at` (UTC hoặc null), `receipt_status` (PENDING/SENT
hoặc null). Khi SUCCEEDED, biên nhận được ghi vào `email_outbox` trong cùng lần
commit. Worker gửi thư riêng, backoff tối đa 300 giây và phục hồi sau restart.
Lỗi email không đổi kết quả thanh toán và không chạy lại debit/finalize.
Giao dịch thành công trước migration email không tự phát sinh email cũ.

SMTP là cơ chế gửi ít nhất một lần: nếu server đã nhận thư nhưng mất ACK hoặc
Payment dừng trước khi lưu SENT, có thể có thư trùng. UUID sự kiện/Message-ID cố
định giúp đối chiếu; ràng buộc duy nhất giữ một sự kiện biên nhận cho mỗi payment.
Không có đảm bảo gửi email đúng một lần chỉ bằng SMTP.

Harness acceptance cũ dựa trên Mailpit chưa được chuyển đổi hoặc chạy lại cho
bản SMTP-only này. Phạm vi kiểm chứng hiện tại gồm unit test bằng SMTP giả lập,
API đang chạy và kết nối/xác thực SMTP; không gửi thư thử thật hoặc thực hiện
thanh toán thật. Bằng chứng acceptance lịch sử giữ nguyên ngày và phạm vi cũ.

## Gateway cho giao diện

UI tại Account cổng 8001 gọi cùng origin:

- `GET /api/v1/tuition/{mssv}` → Tuition.
- `GET/POST /api/v1/payments` và các route UUID/OTP/process đã liệt kê → Payment.

Gateway chỉ chuyển Authorization, Content-Type và Idempotency-Key; không đưa
internal key ra trình duyệt và không mở proxy cho endpoint nội bộ. Timeout trả
504 để client tra cứu/thử lại UUID cũ. Các service vẫn cung cấp API trực tiếp ở
cổng 8002/8003 để kiểm thử độc lập.

## Retry và đối soát

- Chuỗi chính: PENDING_OTP → OTP_VERIFIED → PROCESSING → SUCCEEDED.
- Khi chưa biết kết quả: PENDING_RECONCILIATION, giữ phase RESERVE/DEBIT/FINALIZE/CANCEL.
- Kết thúc bù trừ: FAILED nếu chưa trừ tiền, REFUNDED nếu đã hoàn đúng khoản trừ.
- Retry HTTP hoặc timeout giữ nguyên UUID/payload. `GET` chỉ đọc; worker quét
  giao dịch chưa kết thúc mỗi 5 giây, backoff tối đa 60 giây, tiếp tục sau restart.
- Không refund chỉ vì finalize timeout. Khi cần hủy, nhả/fence Tuition trước;
  nếu đã PAID thì kiểm tra ledger và ghi thành công. Chỉ sau RELEASED mới cancel
  Account để hoàn hoặc chặn khoản trừ đến muộn.
- Lỗi HTTPException hiện dùng `{detail}`; lỗi process đã kết thúc trả PaymentView
  cùng 409. Chưa chuyển sang schema lỗi có `code` chung ở mốc này.
