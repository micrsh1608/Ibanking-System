# Dữ liệu sinh viên và học phí

Bộ dữ liệu mẫu dùng MSSV cùng định dạng `SV20261001`, họ tên đầy đủ và học kỳ
`2026-2027-HK1`, `2026-2027-HK2`. Tên tài khoản đăng nhập `demo01`–`demo10`
là thông tin của người trả tiền; MSSV là thông tin của sinh viên nhận thanh toán.

| MSSV | Họ tên | Mục đích / học phí ban đầu |
|---|---|---|
| SV20261001 | Nguyễn Minh An | 2.500.000 đồng |
| SV20261002 | Trần Ngọc Linh | 3.500.000 đồng |
| SV20261003 | Lê Hoàng Nam | Ca hai giao dịch cùng số dư: 7.000.000 đồng |
| SV20261004 | Phạm Thu Hà | Ca hai giao dịch cùng số dư: 7.000.000 đồng |
| SV20261005 | Hoàng Gia Bảo | Ca hai người trả cùng học phí: 2 + 3 triệu |
| SV20261006 | Võ Khánh Vy | Ca OTP/email thật: 1.000.000 đồng |
| SV20261007 | Đặng Minh Quân | 1.000.000 đồng |
| SV20261008 | Bùi Ngọc Anh | 2.000.000 đồng |
| SV20261009 | Đỗ Đức Huy | 1.000.000 đồng |
| SV20261010 | Hồ Thảo Nhi | 2.000.000 đồng |
| SV20261011 | Dương Tuấn Kiệt | 1.000.000 đồng |
| SV20261012 | Ngô Phương Thảo | 2.000.000 đồng |
| SV20261013 | Lê Minh Khang | Bộ seed tối thiểu tùy chọn: hai kỳ 2 + 3 triệu |
| SV20261014 | Nguyễn Hoàng Phúc | Bộ bổ sung: hai kỳ 400.000 + 600.000 đồng |

`start.ps1 -PrepareDemo -Detached` tạo 12 sinh viên đầu. `-SeedDemo` tạo thêm MSSV kết thúc
1013 nếu được yêu cầu. Lệnh `infra.docker.prepare_demo` dùng các mã còn trống
từ 1014 trở đi. Số tiền còn nợ thực tế phụ thuộc các giao dịch đã thực hiện.

## Ý nghĩa các ID

- `students.id`: khóa nội bộ của một sinh viên; `students.mssv`: mã nhập trên Web.
- `tuition_invoices.id`: mã của từng hóa đơn học phí.
- `tuition_invoices.student_id`: tham chiếu đến `students.id`.
- `payment_items.invoice_id` và `tuition_reservation_items.invoice_id`: cùng
  tham chiếu đến hóa đơn đó khi thanh toán/giữ học phí.

Bộ dữ liệu đang dùng được chuẩn hóa theo MSSV tăng dần, ID sinh viên bắt đầu
từ 1; ID học phí tăng liên tục theo sinh viên rồi theo hóa đơn cũ. Vì một sinh
viên có thể có nhiều hóa đơn, `invoice_id` và `student_id` có thể khác nhau.
Trong SSMS, mở [SQL xem dữ liệu](../infra/sql/004_inspect_tuition.sql). Dùng
`ORDER BY id ASC` để xem ID từ nhỏ đến lớn; SELECT không có ORDER BY không
cam kết thứ tự dòng, còn `DESC` hiển thị từ lớn xuống nhỏ.

SQL Server mặc định có bộ nhớ đệm IDENTITY nên ID có thể nhảy một dải lớn sau
khi khởi động lại. Migration đã tắt `IDENTITY_CACHE` cho `tuition_db` và lần
chuẩn hóa đặt lại bộ đếm theo ID lớn nhất hiện có. ID vẫn có thể khuyết khi
xóa dữ liệu hoặc rollback; không tự đánh số lại sau mỗi thanh toán vì các
ID này được lưu trong lịch sử và các liên kết dữ liệu.

## Chuyển bộ dữ liệu cũ

Thực hiện khi không có giao dịch đang chờ OTP hoặc đang xử lý:

```powershell
powershell -ExecutionPolicy Bypass -File .\demo-data.ps1 -NormalizeTuition
powershell -ExecutionPolicy Bypass -File .\start.ps1 -PrepareDemo -Detached
```

Lệnh đầu dừng ba API, kiểm tra dữ liệu, sao lưu đầy đủ `tuition_db` và
`payment_db` bằng SQL Server COPY_ONLY/CHECKSUM rồi xác minh bản sao lưu.
Các mã cũ được đổi tại sinh viên, reservation và snapshot của payment;
ID hóa đơn được đổi đồng bộ tại cả Tuition và Payment trong một transaction.
Số tiền, trạng thái thanh toán, UUID giao dịch, thời gian và phiên bản hóa đơn
được giữ nguyên. Không ghi vào số dư hay bút toán của Account. Nội dung email
đã gửi trong outbox được giữ làm bằng chứng tại thời điểm gửi.

Bản sao `.bak` nằm trong `artifacts/db-backups/` và volume SQL Server; bản đồ
ID/MSSV nằm trong `artifacts/tuition-normalization.json`. Khi kiểm tra sau ghi
không khớp, transaction bị rollback. Lệnh từ chối dữ liệu không nhận diện
được, MSSV đích đã tồn tại hoặc giao dịch chưa kết thúc để tránh gộp nhầm dữ
liệu. Chạy lại lệnh chuẩn hóa không tạo thêm công nợ.

Lệnh thứ hai cập nhật danh sách hướng dẫn trong `artifacts/demo-accounts.json`
và `artifacts/demo-inspect.sql` theo MSSV mới. Seed không tự đổi mã của dữ liệu
cũ; nếu phát hiện mã cũ, nó yêu cầu chạy bước chuyển dữ liệu trước.
