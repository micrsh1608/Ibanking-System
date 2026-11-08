# Xác minh email và chọn đúng hộp thư

Email chỉ được kích hoạt sau khi người dùng nhận và xác nhận mã tại địa chỉ
đích. Kiểm tra định dạng hoặc việc SMTP nhận thư không chứng minh quyền sở
hữu hộp thư. Mã xác minh hồ sơ khác mã OTP của từng giao dịch thanh toán.

## Tài khoản và nơi nhận thư

Ứng dụng chính chỉ dùng SMTP thật. `SMTP_USERNAME`, `SMTP_PASSWORD` và
`SMTP_FROM` cấu hình người gửi; địa chỉ nhận mã luôn lấy từ hồ sơ/yêu cầu
của người dùng đang đăng nhập. Không dùng địa chỉ SMTP làm người nhận thay
cho tất cả tài khoản. API công khai chỉ trả `smtp` hoặc `not_configured`.

`start.ps1 -PrepareDemo -Detached` tạo dữ liệu còn thiếu và giữ hồ sơ/số dư cũ; không gửi mã
hoặc tự xác minh email. Tài khoản seed `huy` mới có email trống. Tài khoản
còn địa chỉ mẫu phải cập nhật email thật trước khi thanh toán.

Để tạo người trả thứ hai phục vụ ca hai tài khoản cùng một học phí:

```powershell
powershell -ExecutionPolicy Bypass -File .\demo-data.ps1 -CreateTestAccount -Email 'your-second-real-email'
```

Lệnh cấp `huy2` / `HuyDemo_123!`, tài khoản ACTIVE với số dư ban đầu 10 triệu,
email thật vừa truyền vào ở trạng thái chưa xác minh. Nó không gửi thư hoặc
tự chứng minh quyền sở hữu hộp thư. Người dùng hoàn tất xác minh trên Web.
Đăng nhập `huy` và `huy2` ở Chrome thường + ẩn danh, hoặc Chrome + Edge để
hai phiên độc lập. Mỗi phiên dùng email đã xác minh của chính tài khoản đó.

## Xác minh email và lưu hồ sơ trên Web

1. Đăng nhập, mở **Thông tin cá nhân**, chọn **Cập nhật thông tin**. Điền
   địa chỉ email thật bạn nhận được thư, họ tên/điện thoại và mật khẩu hiện tại.
2. Nhấn lưu để yêu cầu mã xác minh. **Mọi lần lưu hồ sơ đều cần mã email**,
   kể cả chỉ đổi tên/điện thoại và giữ nguyên email đã xác minh. Toàn bộ hồ sơ
   mới nằm ở trạng thái chờ; các giá trị đang dùng chưa đổi.
3. Mở hộp thư của địa chỉ vừa nhập, kiểm tra cả thư rác. Lấy mã 6 số trong
   thư **iBanking — Xác minh email**, nhập trong 5 phút rồi chọn
   **Xác minh và lưu hồ sơ**. Xác nhận thành công mới lưu hồ sơ/email mới.
4. Mở **Đóng học phí** và tạo giao dịch mới. OTP thanh toán và biên nhận dùng
   email đã xác minh của chính người trả, độc lập với tài khoản SMTP gửi thư.

Không thấy thư: kiểm tra địa chỉ nhận đang hiển thị, thư rác và cấu hình SMTP.
Nhập sai email thì hủy yêu cầu chờ và cập nhật lại. Gửi lại mã cần mật khẩu
hiện tại và chờ 60 giây từ lần gửi trước; mã cũ mất hiệu lực. Mã sai quá 5
lần hoặc hết 5 phút phải yêu cầu mã mới. Đăng xuất/tải lại vẫn khôi phục
được yêu cầu chờ sau khi đăng nhập.

## Quy tắc backend

- Hồ sơ/email hiện tại được giữ tới khi xác nhận mã đúng. Mọi thay đổi hồ sơ
  được ràng buộc vào mã đã cấp; địa chỉ mới đang chờ chưa được kích hoạt.
- HMAC ràng buộc mục đích, user, UUID, email, nội dung bản nháp, mã và kênh
  đã chọn khi cấp yêu cầu mới. Không trả hoặc log mã rõ, không lưu mật khẩu
  trong bản nháp. Client không tự gán verified, route hoặc timestamp qua JSON.
- Khóa theo user bảo vệ gửi/gửi lại/xác nhận/hủy. Lưu hồ sơ, đánh dấu verified
  và tiêu thụ mã nằm cùng transaction; SMTP ngoài transaction. Gửi thất bại
  thu hồi challenge tương ứng và giữ hồ sơ cũ.
- Tạo payment, gửi/xác nhận OTP và bắt đầu xử lý đều kiểm tra người trả,
  email đã xác minh và snapshot. Payment/outbox mới giữ kênh gửi trong DB,
  tránh dùng nhầm hộp thư khi tài khoản đang cập nhật thông tin.
- Payment chờ dùng snapshot email/kênh cũ cần hủy và tạo mới sau cập nhật.
  Lịch sử đã hoàn tất giữ nguyên. Giao dịch đã bắt đầu vẫn tiếp tục đối soát.
- **Hủy yêu cầu email** trong hồ sơ giữ hồ sơ cũ. **Hủy giao dịch** ở màn
  OTP là thao tác khác: chỉ bản nháp PENDING_OTP/OTP_VERIFIED được ghi FAILED,
  thu hồi mã và không trừ tiền. Giao dịch đang xử lý không bị hủy kiểu này.

UI/API hồ sơ không cache. Sau nâng cấp giao diện, tải lại trang và đăng nhập;
ô mã xác minh hiển thị trong phần email, yêu cầu chờ có thể khôi phục nếu
phản hồi lưu bị mất. Không gửi thêm nhiều lần chỉ vì email hiện tại chưa đổi.

## Migration và bằng chứng

Revision `20261105_verified_email` không tự công nhận email cũ. Hai revision
ngày 06/11, `20261106_account_email_routes` và `20261106_payment_email_channels`,
thêm route/snapshot và ban đầu giữ route `configured` cho dữ liệu cũ.
Revision `20261107_smtp_only_accounts` chuyển tài khoản sang `smtp`, đồng thời
xóa trạng thái verified và challenge từng dùng Mailpit để người dùng xác minh
lại hộp thư thật. Xác minh SMTP thật hiện có được giữ; hồ sơ, số dư và lịch sử
thanh toán được bảo toàn. Payment/outbox Mailpit cũ không tự chuyển sang SMTP
để gửi lại thư lịch sử. Các migration không tự gửi mã/email. Xem
[migration](migrations.md) và [cấu hình SMTP](runbook.md).

Các bằng chứng kiểm thử lịch sử trong môi trường cô lập đã lưu tại `artifacts/email-verification-acceptance.json`,
`artifacts/browser-acceptance.json` và `artifacts/acceptance-summary.json`
giữ nguyên phạm vi/ngày chạy. Chúng không thay cho việc tự nhận email thật
trên máy demo hoặc một lượt nghiệm thu lại các thay đổi mới. Harness acceptance
cũ dựa trên Mailpit chưa được chuyển đổi hoặc chạy lại cho bản SMTP-only này.
Phạm vi kiểm chứng hiện tại gồm unit test bằng SMTP giả lập, API đang chạy và
kết nối/xác thực SMTP; không gửi thư thử thật hoặc thực hiện thanh toán thật.
SMTP/outbox
có ngữ nghĩa at-least-once; khi mất ACK, vẫn có thể nhận email lặp dù chỉ có
một hiệu lực tài chính.
