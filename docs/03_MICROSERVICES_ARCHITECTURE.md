# Microservices Architecture - Nhóm 3 thành viên

```mermaid
flowchart LR
    U[Student] --> G[API Gateway]

    G --> TV1[TV1 Account Service]
    G --> TV2[TV2 Tuition + OTP Service]
    G --> TV3[TV3 Payment Service]

    TV1 --> DB1[(Account DB)]
    TV2 --> DB2[(Tuition DB)]
    TV3 --> DB3[(Payment DB)]

    TV2 --> EMAIL[Email Service]
    TV3 --> TV2
```

## TV2 responsibilities

- Tra cứu học phí.
- Cung cấp dữ liệu cho màn hình chọn khoản học phí.
- Tạo và gửi OTP.
- Xác thực OTP.
- Cập nhật trạng thái học phí sau khi TV3 thanh toán thành công.
- Đảm bảo chỉ một giao dịch chuyển khoản học phí từ UNPAID sang PAID.

## Communication

- Frontend -> API Gateway -> TV2.
- TV3 -> TV2 qua REST API nội bộ.
- TV2 -> Email service/SMTP để gửi OTP.
