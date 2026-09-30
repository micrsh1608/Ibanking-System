# TV2 - Use Case Specification

## UC04 - Xem thông tin học phí

**Actor:** Sinh viên

**Pre-condition**
- Sinh viên đã đăng nhập.
- Hệ thống hoạt động bình thường.

**Main flow**
1. Sinh viên chọn Xem thông tin học phí.
2. Nhập MSSV.
3. Frontend gọi `GET /api/v1/tuition/{mssv}`.
4. TV2 kiểm tra MSSV.
5. TV2 truy vấn khoản học phí.
6. TV2 trả về MSSV, họ tên, email, số tiền và trạng thái.
7. Frontend hiển thị thông tin.

**Alternative**
- MSSV không tồn tại -> HTTP 404.
- Khoản học phí không tồn tại -> HTTP 404.

---

## UC05 - Chọn khoản học phí

**Actor:** Sinh viên

**Main flow**
1. Hệ thống hiển thị khoản học phí sau khi tra cứu.
2. Sinh viên chọn khoản học phí.
3. Vì đề bài chỉ cho thanh toán toàn bộ, hệ thống không cho nhập số tiền tùy ý.
4. Chuyển sang UC06 - Tạo yêu cầu thanh toán của TV3.

**Lưu ý:** TV2 không cần API riêng cho thao tác chọn; đây là thao tác trên giao diện.

---

## UC07 - Gửi OTP

**Actor:** Hệ thống / TV3 gọi TV2

**Main flow**
1. TV3 tạo transaction.
2. TV3 gọi `POST /api/v1/otp/send`.
3. TV2 kiểm tra sinh viên và email.
4. TV2 tạo OTP 6 số.
5. OTP được gắn với transaction_id.
6. OTP không trùng OTP đang hiệu lực.
7. Lưu OTP với thời hạn 5 phút.
8. Gửi OTP qua email.
9. Trả kết quả.

---

## UC08 - Xác thực OTP

**Actor:** Sinh viên

**Main flow**
1. Sinh viên nhập OTP.
2. Frontend gọi `POST /api/v1/otp/verify`.
3. TV2 kiểm tra transaction_id.
4. Kiểm tra OTP tồn tại.
5. Kiểm tra thời hạn.
6. Kiểm tra OTP chưa được sử dụng.
7. Kiểm tra mã OTP.
8. Nếu hợp lệ, đánh dấu used=true.
9. Trả verified=true.

**Alternative**
- Sai OTP -> 400.
- Hết hạn -> 400.
- Đã sử dụng -> 400.
- Giao dịch không có OTP -> 400.

---

## UC10 - Cập nhật trạng thái học phí

**Actor:** Hệ thống / TV3

**Main flow**
1. TV3 trừ tiền thành công.
2. TV3 gọi `PATCH /api/v1/internal/tuition/{mssv}/paid`.
3. TV2 kiểm tra trạng thái hiện tại.
4. Nếu UNPAID -> chuyển PAID.
5. Lưu transaction_id và thời gian thanh toán.
6. Trả kết quả.

**Concurrency**
- Hai giao dịch cùng cập nhật một MSSV: chỉ một yêu cầu được chuyển UNPAID -> PAID.
- Giao dịch còn lại nhận HTTP 409.
