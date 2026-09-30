# Test Cases - TV2

| ID | Test | Expected |
|---|---|---|
| TC01 | Tra cứu MSSV tồn tại | 200 |
| TC02 | Tra cứu MSSV không tồn tại | 404 |
| TC03 | Gửi OTP đúng transaction + email | 200 |
| TC04 | Email không khớp sinh viên | 400 |
| TC05 | Xác thực OTP đúng | 200 |
| TC06 | OTP sai | 400 |
| TC07 | OTP hết hạn | 400 |
| TC08 | OTP đã sử dụng | 400 |
| TC09 | Cập nhật UNPAID -> PAID | 200 |
| TC10 | Cập nhật lần 2 bằng transaction khác | 409 |
| TC11 | Hai request cùng cập nhật một học phí | Chỉ một request thành công |
| TC12 | OTP đang hiệu lực được gửi lại cùng transaction | Không tạo OTP thứ hai |
