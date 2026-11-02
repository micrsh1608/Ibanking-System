# Đánh giá dự án — lịch sử mốc 02–06/11

**Cập nhật cuối 02/11/2026:** đã hoàn thành sớm cả phần việc 07–08/11.
Thử tải 32 payment/16 request đồng thời, mất reply sau commit, ngắt mạng,
SIGKILL Payment/SQL và cài mới đều đạt trên project riêng. Báo cáo 14 trang,
PPTX 14 slide, sơ đồ xuất, OpenAPI offline và ZIP nguồn nằm trong `submission/`.
Xem [nghiệm thu cuối](final-acceptance.md), [báo cáo](final-report.md) và
[checklist](submission-checklist.md). Còn hai thành viên/phân công thực tế do nhóm
điền; SMTP Internet chờ tài khoản của nhóm, Mailpit đã kiểm thử SMTP thực.

Phần dưới giữ lại đánh giá ở mốc 06/11 để theo dõi tiến độ; các công việc ghi
“tiếp theo/còn phải làm” trong phần lịch sử này đã được hoàn tất ở bàn giao cuối.

Ngày cập nhật: 02/11/2026. Đã triển khai sớm toàn bộ phần backend trong năm ngày
đầu của [kế hoạch](implementation-plan.md), giữ FastAPI + SQL Server và lệnh chạy
chung `start.ps1`. Nguồn yêu cầu nghiệp vụ là hai ảnh đề bài người dùng cung cấp.

## Đối chiếu tám yêu cầu

| Yêu cầu | Đã có ở mốc này | Việc tiếp theo |
|---|---|---|
| 1. Phân tích/Use Case/ERD | Use Case UML nguồn PlantUML, bảng luồng nghiệp vụ, ERD bám schema thực tế | Cập nhật hình xuất khi hoàn thiện báo cáo |
| 2. Microservices | Ba app/DB độc lập, Payment gọi REST, recovery worker | Tách SQL login; gateway cùng origin đã có |
| 3. REST API | JWT/ownership, UUID, idempotency, snapshot, hợp đồng và OpenAPI | Duy trì hợp đồng khi nghiệm thu |
| 4. DB | Payments/PaymentItem, nhóm reservation, dấu hủy Account, invoice version, migration có revision | Outbox/completed_at đã có migration giữ dữ liệu |
| 5. Đủ luồng nghiệp vụ | Web tạo → OTP SMTP → reserve/debit/finalize → kết quả/lịch sử/email | Thử tải và lỗi hạ tầng mở rộng |
| 6. Transaction/concurrency | Khóa SQL Server, idempotency, nhóm nguyên tử, bù trừ có fence, phục hồi sau restart | Mở rộng fault/load test khi nghiệm thu ngày 07/11 |
| 7. Web tích hợp | UI tài khoản, học phí, OTP, kết quả/lịch sử; desktop/mobile | Nghiệm thu mở rộng ngày 07/11 |
| 8. Tài liệu/demo | Một lệnh Docker, API/kiến trúc/migration/hướng dẫn và báo cáo kiểm thử | Slides, xuất sơ đồ, diễn tập demo cuối |

## Các thiếu sót P0 đã xử lý

- Payment bỏ model Account/Tuition giả; toàn bộ thông tin người trả và hóa đơn lấy qua REST.
- Tạo/tra cứu/OTP/process/lịch sử được bảo vệ JWT và đúng chủ. Client không được gửi số tiền hay payer/account tùy ý.
- Một UUID xuyên Payment, Account ledger và Tuition reservation. Mã TXN chỉ phục vụ hiển thị.
- Một hoặc nhiều hóa đơn được chốt phiên bản/tổng tiền; giữ/hoàn tất/nhả cả nhóm trong một transaction.
- Khóa thực tế trên SQL Server thay cho with_for_update không sinh khóa phù hợp ở prototype.
- Ghi trạng thái trước side effect, retry cùng UUID, worker đọc DB để tiếp tục sau restart.
- Hủy có dấu bền vững: Tuition chặn finalize/reserve muộn; Account chặn debit muộn và refund đúng khoản gốc.
- Bổ sung identity_number trong API người dùng; dữ liệu thật có thể chưa điền trường này.

## Còn phải làm theo lịch

1. **07/11 — Nghiệm thu mở rộng:** kiểm thử tải, phân hoạch mạng và SQL Server mất kết nối giữa transaction. Các kịch bản SMTP lỗi/restart và trình duyệt đã có.
2. **08/11 — Bàn giao:** báo cáo/slides, xuất Use Case/ERD/sequence và diễn tập demo từ môi trường sạch.

Các nâng cấp ngoài mốc ba ngày: thu hồi JWT tập trung, rate limit đăng nhập, phân
quyền tra cứu MSSV theo chính sách trường và cấu hình triển khai công khai.
JWT hiện có thời hạn; UI đăng xuất bằng cách xóa token trong bộ nhớ.

## Bằng chứng xác minh

- **29 bài pytest đạt**: auth/ownership, snapshot, idempotency, OTP SMTP, nhóm hóa đơn,
  rollback/bù trừ, mất phản hồi sau commit, recovery và migration giữ dữ liệu cũ.
- **8 kịch bản SQL Server/SMTP Docker đạt**: trả một/tất cả, cạnh tranh cùng số dư,
  hai người trả cùng hóa đơn, nhóm giao nhau, 5 process đồng thời, request đến muộn,
  restart Payment ở các phase RESERVE/DEBIT/FINALIZE và SMTP tắt/bật với receipt retry.
- **4 kịch bản Edge đạt**: luồng desktop/mobile, mất phản hồi với UUID cũ và refresh để tiếp tục OTP đã cấp.
- [Bàn giao UI/email](ui-email-delivery.md) và [bàn giao backend](backend-delivery.md) phân biệt rõ phạm vi unit và integration.
- Kết quả máy đọc nằm ở `artifacts/backend-acceptance.json`; không chứa OTP/token/khóa riêng.
- Một cảnh báo Starlette/TestClient còn dùng httpx cũ; không làm thất bại bài test.

Kiểm thử integration có tạo bản ghi IT_* trong ba DB Docker và giữ lại để đối
chiếu ledger. Không dùng kết nối SQL Server riêng trong `.env` của Windows.
Các thử nghiệm timeout sau commit dùng fault mô phỏng ở lớp REST trong pytest;
kiểm thử SQL Server thật tái tạo trạng thái sau commit và restart Payment để
xác minh phục hồi. Chưa chứng minh độ bền dưới mọi loại lỗi hạ tầng.
