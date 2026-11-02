# Kế hoạch hoàn thiện trong bảy ngày

Lập ngày 01/11/2026. Người dùng cho biết còn một tuần; dự kiến làm 02–08/11/2026.
Nhóm 12 gồm ba thành viên; đã có thông tin Phạm Minh Huy — 524H009, hai thành
viên điền sau. Phân công dưới đây theo vai trò; nhóm bổ sung phân công thực tế.

Mục tiêu: luồng Web đăng nhập → tra MSSV → chọn một hóa đơn/học kỳ hoặc toàn bộ
học phí chưa đóng → xác nhận bằng OTP qua email → xử lý → xem kết quả/lịch sử
→ nhận email xác nhận, chạy bằng Docker với SQL Server.

## Lịch triển khai và tiêu chí hoàn thành

**Cập nhật 02/11:** đã hoàn thành sớm phần việc ngày 02–08/11, gồm backend,
SMTP/outbox, UI, tải/lỗi hạ tầng, cài mới và hồ sơ báo cáo/trình diễn.
Xem [bàn giao backend](backend-delivery.md), [UI/email](ui-email-delivery.md)
và [nghiệm thu cuối](final-acceptance.md). Hai thành viên và phân công thực tế
còn lại do nhóm bổ sung trước khi nộp.

| Ngày | Công việc ưu tiên | Sản phẩm/điều kiện hoàn thành | Vai trò |
|---|---|---|---|
| 1 — 02/11 | Chốt schema/API, UUID, `PaymentItem`, danh sách hóa đơn; kiểm tra Docker; hoàn thiện Use Case/ERD | Ba service khởi động; DB/seed lặp được; hợp đồng request/response thống nhất; danh sách hóa đơn và tiền được server chốt | Thiết kế + backend |
| 2 — 03/11 | Tuition reserve/finalize/release/status cho nhóm hóa đơn; khóa SQL Server; idempotency và migration | Hai giao dịch giữ cùng một hóa đơn chỉ một bên thành công; nhóm có phần giao nhau không thanh toán một phần; retry không đổi kết quả | Backend Tuition |
| 3 — 04/11 | Bảo vệ Payment bằng JWT; gọi REST Account/Tuition; state machine và đối soát; bỏ phụ thuộc vào bảng giả | Một UUID nối payment/ledger/invoices; từ chối sai chủ; số tiền lấy từ server; xử lý lại không trừ lần hai; lưu được bước cần phục hồi | Backend Payment/Account |
| 4 — 05/11 | Gửi OTP Mailpit/SMTP, OTP một lần, hủy OTP cũ; outbox email thành công + retry | OTP 5 phút, không dùng lại/gắn sang giao dịch khác; gửi lại bị giới hạn; lỗi email không làm lặp thanh toán | Backend OTP/mail |
| 5 — 06/11 | UI tra MSSV, thông tin người trả chỉ đọc, chọn một/tất cả, tổng tiền, OTP, trạng thái đang xử lý, lịch sử | Đi được toàn luồng trên trình duyệt; số tiền khớp danh sách; không nhúng internal key; kết quả timeout hướng dẫn tra cứu mã cũ | Frontend |
| 6 — 07/11 | Kiểm thử SQL Server đồng thời + lỗi giữa các service + restart + retry email | Chạy các kịch bản nghiệm thu bên dưới; đối chiếu ba DB; lưu log/kết quả; ưu tiên sửa lỗi dữ liệu | Cả nhóm/kiểm thử |
| 7 — 08/11 | Hoàn thiện báo cáo, sơ đồ, REST API, cài đặt; chạy từ môi trường sạch; diễn tập demo | Có tài liệu đủ tám yêu cầu, dữ liệu mẫu, demo 5–10 phút, bản dự phòng; dành nửa ngày sửa lỗi cuối | Cả nhóm |

Thứ tự phụ thuộc chính: hợp đồng/schema → reserve hóa đơn → điều phối thanh toán
→ OTP/mail → UI → kiểm thử toàn luồng. Nếu có nhiều người, UI có thể làm từ API
mock đã chốt; không sửa hợp đồng riêng ở từng service.

## Thiết kế cần chốt ngày đầu

- Mỗi service sở hữu DB riêng; Payment không truy vấn bảng của Account/Tuition.
- Mỗi lần thanh toán có `payment_id` UUID và một/nhiều `PaymentItem`.
- Client chọn `SELECTED` (danh sách ID, có thể một hóa đơn) hoặc `ALL_UNPAID`.
  Backend chốt các hóa đơn chưa đóng của đúng MSSV tại thời điểm tạo giao dịch;
  trả danh sách/tổng để người dùng xác nhận. Không tự thêm hóa đơn sau khi cấp OTP.
- Tổng tiền bằng tổng snapshot; dùng `Decimal`/`NUMERIC(18,2)` và chuỗi thập phân
  trong JSON. Phiên bản/trạng thái/tiền thay đổi trước khi giữ hóa đơn thì yêu cầu xác nhận lại.
- Account kiểm tra chủ tài khoản từ danh tính đã xác minh, trạng thái và số dư;
  cùng `payment_id` chỉ trừ hoặc hoàn tối đa một lần.
- Tuition giữ/hoàn tất tất cả hóa đơn trong một transaction SQL Server, theo
  thứ tự ID tăng dần. Một hóa đơn đã trả không được hoàn tất cho mã khác.
- Sau OTP, chỉ một worker/request giành quyền xử lý payment; ghi trạng thái
  bền vững trước/sau mỗi REST call. Không giữ transaction DB mở trong khi gọi HTTP/SMTP.
- Timeout sau debit/finalize phải được đối soát theo UUID; 404 khi request khác
  còn chạy không chứng minh chưa có hiệu lực. Không tự hoàn tiền khi finalize có thể đã thành công.
- Không tự nhả reservation đang xử lý tiền chỉ vì hết TTL; cần đối soát và hàng rào
  trạng thái để các request đến muộn không thể hoàn tất giao dịch đã bị hủy.
- Thành công: mọi hóa đơn trong nhóm PAID đúng UUID, một DEBIT đúng tổng,
  lịch sử SUCCEEDED; email được ghi vào outbox cùng transaction ghi thành công.
  Worker mail có thể dùng polling SQL, chưa cần message broker trong phạm vi một tuần.

## Danh sách nghiệm thu tối thiểu

| Kịch bản | Kết quả phải chứng minh |
|---|---|
| Đăng nhập đúng/sai, token hết hạn | Token hợp lệ mới truy cập; không sửa người trả từ request |
| Tra MSSV tồn tại/không có | Tên sinh viên, danh sách hóa đơn và trạng thái chính xác; 404 rõ ràng |
| Đóng một hóa đơn/học kỳ | Chỉ hóa đơn đã chọn chuyển PAID; số dư giảm đúng một lần |
| Đóng toàn bộ công nợ | Tất cả hóa đơn trong snapshot cùng hoàn tất; tổng tiền đúng; không có phần đã trả khi nhóm thất bại |
| Một tài khoản 10 triệu, hai lần trả 7 triệu đồng thời | Chỉ một lần thành công; số dư 3 triệu; một DEBIT |
| Hai người cùng trả một hóa đơn | Một payment thành công; bên còn lại không bị giữ/trừ tiền cuối cùng |
| Hai nhóm hóa đơn `[A,B]` và `[B,C]` | Không bên nào trả trùng B; thất bại giữ nhóm phải rollback cả nhóm |
| Gửi lặp cùng UUID / cùng UUID khác dữ liệu | Không trừ/hoàn/gửi hiệu ứng nghiệp vụ lần hai; khác dữ liệu trả 409 |
| OTP sai/hết hạn/đã dùng/giao dịch khác/gửi lại | Từ chối; mã cũ hết hiệu lực; không thể process bằng xác minh cũ |
| Giả `payer_id`, sửa tiền, xem payment người khác | 401/403/404 theo hợp đồng; không lộ dữ liệu, không đổi số dư |
| Mất kết nối sau debit hoặc sau finalize | Hiển thị đang đối soát; retry cùng mã; cuối cùng ba DB khớp |
| Restart Payment giữa các bước | Khôi phục từ trạng thái đã lưu; không cần người dùng tạo giao dịch mới |
| SMTP lỗi sau khi đã thanh toán | Thanh toán vẫn thành công; gửi lại email từ outbox, không trừ tiền lại |

## Hồ sơ bàn giao

- Use Case, ERD từng DB, sơ đồ Microservices và sequence thanh toán/lỗi.
- Danh mục REST API kèm URI, method, auth, input/output, HTTP status, ví dụ.
- Migration SQL/ORM có phiên bản, dữ liệu demo, mô tả invariant và locking.
- Cấu hình mẫu Windows/Docker/SMTP, lệnh chạy/test và xử lý lỗi thường gặp.
- Kết quả kiểm thử có log và đối chiếu số dư/ledger/payment/invoices.
- Kịch bản trình diễn: trả một kỳ, trả tất cả, OTP lỗi và hai request đồng thời.

## Kiểm soát phạm vi

Ưu tiên tính đúng đắn dữ liệu, tích hợp, email, hai chế độ trả học phí và báo cáo.
Giao diện nâng cao, dashboard quản trị, message broker riêng và triển khai cloud
có thể làm sau. Nếu chậm vào ngày 4, giảm phần trang trí UI và dùng polling worker;
không bỏ kiểm thử đồng thời hoặc cơ chế phục hồi sau timeout.
