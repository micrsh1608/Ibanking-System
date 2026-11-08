# Migration và dữ liệu cũ

Mỗi database có bảng `schema_revisions(revision, applied_at)`. Runner ở
`shared/migrations.py` dùng application lock trong transaction SQL Server để
tránh hai tiến trình nâng cấp đồng thời. Các revision đã áp dụng được bỏ qua.
Không có thao tác drop/reset dữ liệu trong migration này.

Account và Tuition tắt `IDENTITY_CACHE` khi chạy migration trên SQL Server,
ngoài transaction theo yêu cầu của SQL Server. Việc này hạn chế bỏ qua dải ID
lớn sau khi restart; không tự đánh lại ID đã tồn tại. Khóa nội bộ vẫn có thể
khuyết khi rollback/xóa dòng.

| Database | Revision | Thay đổi |
|---|---|---|
| account_db | `20261104_account_cancellation` | Tạo các bảng Account còn thiếu và `account_cancellations` |
| account_db | `20261105_verified_email` | Thêm trạng thái xác minh email, challenge/hash/hạn/lần thử và bản nháp hồ sơ; email cũ chưa được tự coi là đã xác minh |
| account_db | `20261106_account_email_routes` | Thêm email_channel và email_pending_channel; route cũ mặc định configured, thêm ràng buộc route hợp lệ |
| account_db | `20261107_smtp_only_accounts` | Chuyển configured/mailpit sang smtp; hủy xác minh và challenge từng dùng Mailpit, giữ hồ sơ và dữ liệu tài chính |
| tuition_db | `20261102_tuition_reservations` | Tạo bảng nhóm giữ hóa đơn và chi tiết nhóm |
| tuition_db | `20261103_invoice_version` | Thêm `version` mặc định 1 cho bảng hóa đơn cũ nếu chưa có |
| payment_db | `20261102_payment_snapshots` | Tạo `payments` và `payment_items` cho UUID/snapshot/OTP/recovery |
| payment_db | `20261105_email_outbox` | Tạo `email_outbox`, thêm `completed_at`, giữ lịch sử hiện có |
| payment_db | `20261103_full_tuition_terms_v1` | Thêm `terms_version`, `terms_accepted_at` nullable; không giả lập đồng ý cho lịch sử cũ |
| payment_db | `20261104_unique_active_otp` | Thêm dấu vân tay HMAC và filtered unique index cho mã OTP; hủy mã PENDING_OTP cũ chưa có dấu vân tay để yêu cầu gửi lại |
| payment_db | `20261106_payment_email_channels` | Thêm email_channel cho payments và email_outbox; giữ người nhận, thời hạn OTP và kết quả tiền/học phí |

Chạy Windows từ thư mục gốc sau khi cấu hình `.env`:

```powershell
.\.venv\Scripts\python.exe -m services.account.migrate
.\.venv\Scripts\python.exe -m services.tuition.migrate
.\.venv\Scripts\python.exe -m services.payment.migrate
```

Docker tự gọi migration qua `db-init` khi chạy `start.ps1`. Mặc định không seed;
chỉ tạo mẫu khi dùng `-SeedDemo`, `-PrepareDemo` hoặc `demo-data.ps1 -Seed`.
Seed giữ số dư, trạng thái hóa đơn và dữ liệu đang có. Demo Tuition có hai kỳ,
2 triệu và 3 triệu; chỉ thêm kỳ chưa tồn tại, không chuyển hóa đơn PAID về UNPAID.

Catalog demo01–demo10 được khai báo trong `services/account/seed.py`, còn
MSSV/học phí trong `services/tuition/seed.py`. `infra/docker/demo_catalog.py`
điều phối hai seed, được gọi bởi `start.ps1 -PrepareDemo -Detached` sau khi ứng dụng chính đã
sẵn sàng. Migration không tự tạo catalog hoặc gửi thư. Catalog
chỉ cấp mật khẩu Demo_123! và 10 triệu cho tài khoản mới, giữ dữ liệu đã có;
email ở tài khoản mới để trống và dùng SMTP. Mỗi người dùng nhập rồi xác minh
email thật trên Web; catalog không lấy địa chỉ người nhận từ tài khoản SMTP,
không tự gửi mã hoặc đánh dấu email đã xác minh. Xem [demo chính](consistency-demo.md).

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
Payment prototype. Bằng chứng nâng cấp SQL Server cũ giữ nguyên phạm vi/ngày chạy.

Revision email không tự gửi biên nhận cho các payment đã thành công trước khi
nâng cấp. Thời gian hoàn tất lịch sử được lấy từ updated_at nếu chưa có.

Quy tắc chốt ngày 03/11 yêu cầu trả toàn bộ công nợ và đồng ý điều khoản. Giao
dịch mới lưu phiên bản/thời gian đồng ý cùng snapshot. Bản nháp cũ chưa bắt đầu
xử lý, thiếu đồng ý hoặc chọn từng kỳ, phải tạo lại; không cấp OTP hoặc bắt đầu
trừ tiền từ bản nháp này. Lịch sử đã hoàn tất được giữ nguyên. Giao dịch đã ở
PROCESSING/PENDING_RECONCILIATION vẫn đối soát tiếp để không bỏ dở hiệu lực tiền.
Các revision chạy theo danh sách khai báo trong migrate.py, không theo thứ tự tên.

Revision OTP ngày 04/11 giữ UUID, số dư, bút toán, hóa đơn và lịch sử; chỉ mã đang
chờ nhập từ trước bản nâng cấp cần gửi lại vì không thể khôi phục mã rõ từ hash
cũ để đăng ký chống trùng. Các giao dịch đã bắt đầu xử lý tiếp tục đối soát.

Hai revision route ngày 06/11 không thay đổi số dư, bút toán, hóa đơn hoặc
lịch sử. Tại thời điểm nâng cấp đó, user/payment/outbox cũ nhận giá trị configured
để giữ cách gửi đang dùng. Challenge mới ràng
buộc kênh gửi trong HMAC và bản nháp; payment/outbox mới giữ snapshot kênh.
Route chỉ do server cấp, API hồ sơ không cho client sửa bằng JSON. Nếu
snapshot email/kênh của payment chờ không còn khớp hồ sơ, hủy bản nháp và tạo
giao dịch mới; bản đã PROCESSING vẫn được phục hồi/đối soát.

Revision `20261107_smtp_only_accounts` áp dụng chính sách SMTP thật cho tài khoản:

- User có route `mailpit` hoặc yêu cầu xác minh chờ qua Mailpit được chuyển
  sang `smtp`, xóa trạng thái verified và challenge chờ. Nhận thư ở hộp thư
  giả lập trước đây không được coi là chứng minh quyền sở hữu email thật.
- User `configured` được chuyển sang `smtp`; trạng thái xác minh qua SMTP
  thật hiện có được giữ. Mọi lần lưu hồ sơ tiếp theo đều trả 202 và cần mã
  gửi đến địa chỉ được nhập, kể cả giữ nguyên email đã xác minh.
- Tên, email hồ sơ, mật khẩu, số dư, bút toán, hóa đơn và kết quả thanh toán
  được giữ nguyên. Migration không gửi email, không tạo người dùng và không
  ghi lại người nhận của payment/outbox lịch sử.
- Payment mới lấy email đã xác minh của đúng người trả và route `smtp`.
  Outbox cũ mang route Mailpit được giữ làm lịch sử, không tự chuyển sang
  SMTP để phát lại thư cũ đến hộp thư Internet.

Harness acceptance cũ dựa trên Mailpit chưa được chuyển đổi hoặc chạy lại cho
bản SMTP-only này. Phạm vi kiểm chứng hiện tại là unit test bằng SMTP giả lập,
API đang chạy và kết nối/xác thực SMTP; không gửi thư thử thật hoặc thực hiện
giao dịch thanh toán thật. Các artifact acceptance cũ là bằng chứng lịch sử.
