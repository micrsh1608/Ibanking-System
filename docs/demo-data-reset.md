# Xóa dữ liệu và tự tạo lại để demo — 05/11/2026

Bằng chứng kiểm thử lịch sử: 111 unit test và 6 kịch bản Docker độc lập tại
`artifacts/demo-data-acceptance.json`: reset xóa cả dữ liệu legacy, khởi động
bình thường giữ bảng trống, seed tường minh/lặp, thêm hóa đơn, từ chối trùng kỳ
và đăng nhập/tra cứu đúng dữ liệu mới. Không tạo giao dịch hoặc gửi email thử
qua SMTP thật trong quá trình reset chính.

Các lệnh chạy trong PowerShell tại thư mục gốc `Ibanking-System`, cần Docker
Desktop Linux containers. Không cần cài Python hoặc mở riêng từng service.

## 1. Xóa dữ liệu cũ, để bảng trống

Nếu chỉ cần sửa ID người dùng/tài khoản đang nhảy hàng nghìn, dùng
`powershell -ExecutionPolicy Bypass -File .\demo-data.ps1 -NormalizeAccounts`
thay vì reset. Lệnh dừng API, sao lưu và kiểm tra bản sao Account/Payment, đánh lại ID
liên tục và cập nhật liên kết ở accounts, ledger, cancellation và payment
trong một transaction. Mật khẩu, hồ sơ đã xác minh, số tài khoản, số dư và kết
quả thanh toán được giữ nguyên. Người dùng có ID thay đổi cần đăng nhập lại.
Bản đồ ID nằm ở `artifacts/account-normalization.json`, bản `.bak` ở
`artifacts/db-backups/`. Không chạy khi người dùng cần đổi ID đang có mã xác
minh hồ sơ hoặc giao dịch chờ xử lý.

```powershell
powershell -ExecutionPolicy Bypass -File .\demo-data.ps1 -Reset
```

Lệnh này **xóa toàn bộ dữ liệu** trong `account_db`, `payment_db`, `tuition_db`
của project Docker `ibanking-demo`, SQL Server `127.0.0.1,14330`. Nó dừng ba API,
ngắt kết nối đang dùng các DB này (kể cả cửa sổ query SSMS), xóa/tạo lại đúng ba
DB, chạy migration rồi mở lại API. Những bảng prototype cũ cũng bị xóa. SQL
Server trên Windows `HUY-PC` không phải đích của lệnh.

Sau reset: không có user, tài khoản, sinh viên, hóa đơn, OTP, bút toán, lịch sử
hoặc outbox. Chỉ `schema_revisions` có dòng metadata của migration. Cấu hình
SQL/SMTP trong `.env` và `infra/env/docker.env` được giữ nguyên. Việc khởi động
lại bình thường không tự thêm bộ demo; đăng nhập sẽ chưa được vì chưa có user.

Trong SSMS, Refresh Databases và mở New Query với kết nối `127.0.0.1,14330`.
Kiểm tra nhanh:

```sql
SELECT COUNT(*) AS users FROM account_db.dbo.users;
SELECT COUNT(*) AS accounts FROM account_db.dbo.accounts;
SELECT COUNT(*) AS students FROM tuition_db.dbo.students;
SELECT COUNT(*) AS invoices FROM tuition_db.dbo.tuition_invoices;
SELECT COUNT(*) AS payments FROM payment_db.dbo.payments;
```

Tất cả phải bằng 0. Xem đầy đủ số dòng mỗi bảng bằng `.\demo-data.ps1`.

## 2. Khi sẵn sàng, tự tạo bộ dữ liệu tối thiểu

```powershell
powershell -ExecutionPolicy Bypass -File .\demo-data.ps1 -Seed
```

Kết quả:

| Dữ liệu | Giá trị |
|---|---|
| Username / password | `huy` / `HuyDemo_123!` |
| Họ tên / số điện thoại | Phạm Minh Huy / 0900000001 |
| Số tài khoản / số dư | 1000000001 / 10.000.000 đồng |
| Email | Trống ở tài khoản mới — nhập và xác minh email thật trên Web trước khi thanh toán |
| MSSV / tên sinh viên | SV20261013 / Lê Minh Khang |
| Hóa đơn HK1 | 2026-2027-HK1, 2.000.000 đồng, UNPAID |
| Hóa đơn HK2 | 2026-2027-HK2, 3.000.000 đồng, UNPAID |
| Giao dịch/lịch sử | Chưa có |

Seed dùng để chuẩn bị dữ liệu từ terminal, không phải chức năng đăng ký trên
ứng dụng. Mật khẩu được băm Argon2. Chạy Seed lần nữa chỉ bổ sung dữ liệu mẫu
còn thiếu; không nạp lại tiền hoặc đổi PAID về UNPAID.

Trên máy mới có thể gộp khởi động và seed thành một lệnh:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -SeedDemo -Detached
```

## 3. Cấu hình người nộp và demo thanh toán

1. Mở `http://127.0.0.1:8001/ui/`, tải lại trang và đăng nhập `huy`.
2. Cấu hình SMTP thật trong `infra/env/docker.env`. SMTP_USERNAME/SMTP_FROM
   là người gửi, không phải địa chỉ nhận cố định của mọi tài khoản.
3. Chọn Thông tin cá nhân → Cập nhật thông tin; điền email thật nhận thư của
   bạn, nhập mật khẩu `HuyDemo_123!` rồi nhấn Lưu. Mọi lần lưu hồ sơ đều gửi
   mã đến email vừa nhập, kể cả chỉ sửa tên/điện thoại và giữ nguyên email.
   Hồ sơ chưa đổi ngay: nhập mã từ hộp thư thật tại mục Xác minh địa chỉ email
   và nhấn Xác minh và lưu hồ sơ. Chỉ sau bước này hồ sơ/email mới được lưu.
4. Chọn Đóng học phí, nhập MSSV `SV20261013`: tổng phải trả đủ 5 triệu, số dư 10
   triệu. Đồng ý điều khoản rồi xác nhận; hệ thống tự gửi OTP.
5. Nhập OTP trong 5 phút được gửi đến email vừa xác minh để thanh toán. Kết quả: cả hai hóa đơn PAID, số dư còn
   5 triệu, một giao dịch SUCCEEDED và email biên nhận. Xem Lịch sử giao dịch.
6. Tra lại MSSV: không còn công nợ chưa đóng; không thanh toán lại khoản đã trả.

## 4. Tạo người trả thứ hai để thử cùng một học phí

```powershell
powershell -ExecutionPolicy Bypass -File .\demo-data.ps1 -CreateTestAccount -Email 'your-second-real-email'
```

Kết quả: tài khoản `huy2` / `HuyDemo_123!`, ACTIVE, số dư ban đầu 10 triệu.
Lệnh dùng địa chỉ thật bạn nhập và để email chưa xác minh; không gửi thư
hoặc tự đánh dấu verified. Đăng nhập `huy2`, lưu/xác minh hồ sơ bằng mã gửi
đến địa chỉ đó. Tài khoản `huy` mới cần cập nhật/xác minh email tương tự.

Mở hai phiên độc lập cho `huy` và `huy2`, cùng tra một MSSV còn UNPAID,
đảm bảo cả hai đủ số dư và nhận OTP riêng tại email của từng người. Sau khi
hai OTP được xác minh, bấm thanh toán gần nhau. Kỳ vọng chỉ một người bị trừ
đúng tiền, hóa đơn chỉ PAID một lần; người còn lại giữ nguyên số dư.

## 5. Tạo thêm sinh viên/học phí cho lần thử tiếp theo

```powershell
powershell -ExecutionPolicy Bypass -File .\demo-data.ps1 -AddTuition -Mssv SV2026002 -StudentName "Nguyễn Văn An" -Semester TEST-HK1 -Amount 1500000.00
```

Nếu MSSV chưa có, lệnh tạo sinh viên rồi thêm hóa đơn UNPAID/version 1. Nếu đã
có MSSV, giữ tên hiện tại và thêm kỳ mới. Không ghi đè kỳ đã tồn tại, kể cả đã
PAID; muốn tạo khoản mới cho cùng MSSV, dùng Semester khác. Nhập số tiền không
dấu phân cách hàng nghìn, dùng dấu chấm cho phần thập phân. Tiền phải dương.

Có thể thêm học phí trực tiếp trong SSMS (sau khi đã seed):

```sql
USE tuition_db;
GO
INSERT INTO dbo.tuition_invoices
    (student_id, semester, amount_due, version, status)
SELECT id, 'TEST-HK3', 1000000.00, 1, 'UNPAID'
FROM dbo.students
WHERE mssv = 'SV20261013';
```

Chạy một lần cho mỗi kỳ; cặp sinh viên/kỳ là duy nhất. Không tự sửa số dư,
PAID, reserved_payment_id hoặc bảng ledger sau thanh toán để làm lại demo.
Nếu cần trở lại hoàn toàn từ đầu, Reset rồi Seed chủ động theo hai bước trên.
