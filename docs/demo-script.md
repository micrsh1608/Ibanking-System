# Kịch bản trình diễn 5–10 phút — Nhóm 12

Môn Kiến trúc hướng dịch vụ; giảng viên TS. Dương Hữu Phúc. Phạm Minh Huy,
MSSV 524H009; hai thành viên còn lại điền sau. Nhóm tự bổ sung người thuyết
trình theo phân công thực tế.

## Chuẩn bị trước giờ trình bày

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -PrepareDemo -Detached
```

Chỉ chạy ứng dụng chính: Web http://127.0.0.1:8001/ui/, SQL
`127.0.0.1,14330`, email qua SMTP thật. Lệnh chuẩn bị khởi động
chung ba service, tạo catalog `demo01`–`demo10` nếu thiếu, mật khẩu mới
`Demo_123!`, số dư mới 10 triệu. Không đặt lại dữ liệu đã dùng. Xem trạng
thái thực trong `artifacts/demo-accounts.json`, SQL chỉ đọc trong
`artifacts/demo-inspect.sql`.

- Dùng `huy` và `huy2` cho ca hai người trả cùng học phí. Ở từng tài khoản,
  mở Thông tin cá nhân, nhập email thật của người dùng rồi tự nhập mã nhận
  tại địa chỉ đó để xác minh trước demo. Chuẩn bị dữ liệu không xác minh hộ.
- Mỗi tài khoản demo khác cũng phải cập nhật/xác minh email thật trước khi
  nhận OTP thanh toán. Người gửi SMTP không thay thế địa chỉ nhận trong hồ sơ.
- Dùng MSSV còn UNPAID, ví dụ `SV20261001` có 2,5 triệu hoặc `SV20261007`
  có 1 triệu trên bộ mới; kiểm tra số dư hiện tại của cả hai người trả.
- Mở Chrome thường + ẩn danh hoặc Chrome + Edge cho hai phiên độc lập.
- Catalog idempotent: chạy lại không nạp tiền, không chuyển PAID về UNPAID
  hoặc xóa lịch sử. Kiểm tra công nợ và số dư trước khi nói kết quả dự kiến.
- Tải image/dependency trước; lần build đầu cần mạng. Đọc
  [runbook](runbook.md) nếu SMTP/Docker chưa sẵn sàng.
- Không chạy reset, kill/disconnect hoặc bộ fault/load trong lúc demo.

## Nội dung theo thời gian

| Thời gian | Thao tác / lời giải thích | Quan sát |
|---|---|---|
| 0:00–1:00 | Giới thiệu Account, Payment, Tuition; mỗi service sở hữu DB và giao tiếp REST | Sơ đồ kiến trúc, API healthy |
| 1:00–2:00 | Đăng nhập, xem hồ sơ và nhãn hộp thư; tra MSSV | Người trả chỉ đọc, thông tin sinh viên, toàn bộ công nợ, số dư |
| 2:00–3:30 | Đồng ý điều khoản, xác nhận, mở đúng hộp thư và nhập OTP | OTP riêng của giao dịch, hiệu lực tối đa 5 phút |
| 3:30–4:30 | Thanh toán và xem lịch sử/biên nhận | SUCCEEDED, số dư giảm đúng tổng, toàn bộ hóa đơn PAID |
| 4:30–7:30 | Hai phiên minh họa hai ca concurrency | Một DEBIT hợp lệ mỗi ca, không vượt tiền hoặc trả trùng |
| 7:30–9:00 | Đối chiếu SQL, giải thích khóa, idempotency, saga/outbox | Tiền, hóa đơn, snapshot và lịch sử cùng kết quả |
| 9:00–10:00 | Mở bằng chứng kiểm thử đã lưu, nêu giới hạn | Phân biệt demo tay, kiểm thử tự động và SMTP at-least-once |

Màn thanh toán lấy họ tên/điện thoại/email tự động từ tài khoản đăng nhập;
người dùng không sửa người trả ở đó. Chỉ trả toàn bộ công nợ chưa đóng của
MSSV. Nút xác nhận cần học phí hợp lệ, đủ tiền, email đã xác minh và đồng ý
điều khoản. Không sửa số tiền hoặc chọn một phần hóa đơn để vượt quy tắc đề.

## Hai ca tính nhất quán

Theo [hướng dẫn chi tiết](consistency-demo.md), chuẩn bị cả hai OTP trước
khi bấm thanh toán gần nhau, dùng Web hoàn toàn:

| Ca | Tài khoản/MSSV trên bộ mới | Kết quả cuối cần đối chiếu |
|---|---|---|
| Một tài khoản, hai khoản | demo02; SV20261003 và SV20261004, mỗi khoản 7 triệu; số dư 10 triệu | Một SUCCEEDED; bên còn lại bị từ chối hoặc chặn trước xử lý; còn 3 triệu và một DEBIT 7 triệu |
| Hai tài khoản, một công nợ | huy và huy2; cùng một MSSV còn UNPAID, ví dụ SV20261001 có 2,5 triệu | Chỉ một người bị trừ đúng tổng học phí; người còn lại giữ nguyên số dư; hóa đơn PAID một lần |

Thao tác tay không bảo đảm request đến cùng thời điểm. Trình bày đúng giới
hạn này; bằng chứng SQL concurrency tự động nằm ở bộ nghiệm thu đã lưu.
Không cần mở terminal để gửi payment, không thêm độ trễ vào service.

Ở cả hai ca, Web có thể cập nhật số dư/công nợ rồi khóa nút thanh toán
trước khi request thứ hai được gửi. Đây là chặn hợp lệ; bản nháp có thể
còn PENDING_OTP/OTP_VERIFIED thay vì tự chuyển FAILED. Dùng **Hủy giao
dịch** để kết thúc bản nháp thành FAILED với lý do hủy. SQL phải có 0 DEBIT
cho payment bị chặn/hủy. Không trình bày trạng thái bản nháp đó như một
request xử lý đã bị server từ chối.

## Khi cần xử lý trong buổi demo

- Không thấy email: đọc địa chỉ nhận trong hồ sơ/giao dịch, kiểm tra hộp
  thư thật và thư rác của đúng người dùng. OTP thanh toán khác mã xác minh
  hồ sơ; khớp UUID/người nhận/hạn.
- Bỏ màn OTP: **Hủy giao dịch** chỉ áp dụng PENDING_OTP/OTP_VERIFIED; lịch sử
  FAILED ghi lý do hủy, không thay đổi tiền/học phí. Giao dịch đang xử lý
  phải chờ đối soát, không tạo thanh toán mới để thay thế.
- UI tự cập nhật khoảng 5 giây và khi trở lại cửa sổ; có thể bấm Làm mới.
  Đối chiếu SQL khi trạng thái cuối đã hội tụ.
- Lỗi mạng sau khi bấm: dùng lại UUID trong lịch sử để theo dõi; refresh
  không đồng nghĩa cần tạo một giao dịch khác.

Kiểm thử/đối chiếu log: [nghiệm thu đã lưu](final-acceptance.md),
[truy vết](observability.md), [JSON tổng hợp](../artifacts/acceptance-summary.json).
Các bằng chứng cũ giữ nguyên phạm vi/ngày chạy; thay đổi catalog/UI cần kiểm
tra riêng trước khi tuyên bố đã nghiệm thu lại toàn bộ.
