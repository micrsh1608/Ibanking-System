# Đối chiếu tra cứu và thanh toán với đề bài — 03/11/2026

Lượt rà soát tiếp theo ngày 04/11 về OTP, thành công và tính nhất quán được ghi
riêng tại [đối chiếu mục 3–5](otp-success-consistency-review.md); số liệu dưới đây
thuộc lượt kiểm tra ngày 03/11.

Người dùng đã xác nhận thay yêu cầu chọn từng kỳ trước đó bằng **trả toàn bộ
công nợ chưa đóng của MSSV**. Bảng dưới đối chiếu trực tiếp mục 2 trong ảnh đề bài.

| Yêu cầu | Kết quả kiểm tra / thay đổi |
|---|---|
| Người nộp: họ tên, điện thoại, email | Lấy từ tài khoản đang đăng nhập. Hiển thị bằng text chỉ đọc trên trang thanh toán; API không nhận thông tin người trả do client tự gửi. Thiếu/sai định dạng thì chặn xác nhận, có đường dẫn cập nhật hồ sơ riêng. |
| Nhập MSSV tự tra cứu | Tự tra sau 650ms ngừng nhập, vẫn có nút Tra cứu để thử lại. Hiển thị tên, MSSV, các khoản học phí và tổng. |
| Không dùng kết quả MSSV cũ | Đổi MSSV xóa ngay thông tin/số tiền/đồng ý cũ; bỏ qua phản hồi đến muộn của lần tra trước. Không tìm thấy trả 404 và không thể xác nhận. |
| Trả toàn bộ, không một phần | Bỏ radio chọn kỳ và checkbox hóa đơn. Chỉ ALL_UNPAID; API từ chối SELECTED, invoice_ids và amount. Một MSSV có một hóa đơn thì trả đủ hóa đơn đó; có nhiều hóa đơn thì trả đủ tất cả khoản chưa đóng. |
| Thông tin thanh toán | Nhóm riêng hiển thị số dư khả dụng, số tiền cần trả, điều khoản và đồng ý. Payer/tuition/payment có tiêu đề rõ ràng. |
| Khoản tồn tại, chưa thanh toán | Không xác nhận nếu không tìm thấy MSSV, không còn công nợ hoặc có khoản RESERVED. PAID vẫn hiển thị để đối chiếu nhưng không được trả lại. Khoản RESERVED hiển thị tiền đang chờ hoàn tất, đồng thời chặn giao dịch mới. |
| Số dư >= số tiền | UI khóa nút khi thiếu tiền. Payment kiểm tra lại trước tạo snapshot; Account vẫn kiểm tra trong transaction trừ tiền để xử lý cạnh tranh. Bằng đúng tổng tiền được chấp nhận. |
| Nút Xác nhận giao dịch | Chỉ bật khi đủ người trả hợp lệ, tài khoản ACTIVE, MSSV có công nợ phù hợp, đủ số dư và đã đồng ý điều khoản. API kiểm tra độc lập với nút. |
| Công nợ thay đổi sau xác nhận | Tuition dùng UPDLOCK/HOLDLOCK trên tập hóa đơn của MSSV khi giữ công nợ. Tập UNPAID/phiên bản/tổng thay đổi thì yêu cầu tra cứu/xác nhận lại; không tự tăng tiền sau khi người dùng đã xác nhận. |

## Điều khoản và dữ liệu hiện có

Payment mới lưu `terms_version=2026-11-03` và `terms_accepted_at` cùng snapshot.
`terms_accepted` phải là boolean true; không nhận số/chuỗi/false hoặc thiếu trường.
Migration chỉ thêm hai cột nullable, không tự ghi nhận đồng ý cho lịch sử cũ.

Bản nháp cũ chọn từng kỳ hoặc chưa có đồng ý điều khoản không được cấp OTP/bắt
đầu trừ tiền; UI hướng dẫn tạo giao dịch mới. Lịch sử thành công được giữ nguyên.
Các giao dịch đã PROCESSING/PENDING_RECONCILIATION vẫn phục hồi để không bỏ dở
hiệu lực tiền. Không reset số dư/hóa đơn để phù hợp chính sách mới.

## Bằng chứng

- **68 unit test đạt**, gồm điều kiện trên, không chấp nhận client sửa tiền/người
  trả/chọn một phần, số dư bằng tổng, thay đổi công nợ không trừ tiền, bảo vệ lịch
  sử/migration và kiểm tra số điện thoại có 7–15 chữ số.
- **14 bài Edge đạt**: desktop/mobile, OTP/biên nhận, retry cùng UUID, khôi phục
  trang, số dư 0/đúng bằng tổng, thiếu phone, account LOCKED, không có hóa đơn,
  MSSV không tồn tại, thay MSSV, phản hồi đảo thứ tự và công nợ RESERVED.
- **8 kịch bản SQL Server/SMTP** và **7 kịch bản tải/lỗi hạ tầng** đạt trong project
  `ibanking-acceptance-d6343569`. Dựng lại mã với build cache, volume hoàn toàn mới.
  32 payment/16 request process đồng thời, 64 hóa đơn; audit đủ ba DB; tất cả
  response 200, p95 HTTP process 3.878 giây. Đây là số đo trên máy hiện tại.
- Project kiểm thử cưỡng chế SMTP về Mailpit, không gửi thư thử qua SMTP Internet
  của ứng dụng chính. Container kiểm thử đã dừng, volume giữ lại để đối chiếu.

Các lượt SQL/tải/Edge của `d6343569` dùng bản quy tắc toàn bộ/điều khoản; sau đó
siết thêm phone phải có 7–15 chữ số và chạy lại 68 unit test. Không coi lần chạy
unit này là một lần chạy lại tải/lỗi. JSON: `artifacts/release/d6343569/acceptance.json`,
`artifacts/backend-acceptance.json`, `artifacts/browser-acceptance.json`.

Ảnh: `artifacts/tuition-full-debt-desktop.png`, `payment-selection-mobile.png`
và `tuition-insufficient-balance.png`. Hợp đồng mới trong `docs/api.md` và OpenAPI.

Các PDF/PPTX của mốc bàn giao trước phần thay đổi này giữ thông tin lịch sử;
tài liệu này, README, API và mã hiện hành là nguồn quy tắc mới. Cần dùng quy tắc
toàn bộ khi chỉnh bản báo cáo/slide để nộp chính thức.

## Cách dùng và tái hiện

Chạy ứng dụng vẫn một lệnh `powershell -ExecutionPolicy Bypass -File .\start.ps1`.
Mở `http://127.0.0.1:8001/ui/`, tải lại trang rồi vào Đóng học phí. Nhập MSSV,
kiểm tra đủ ba nhóm thông tin, mở điều khoản, tích đồng ý và xác nhận giao dịch.
Tạo giao dịch mới nếu đang giữ bản nháp chọn từng kỳ từ phiên bản trước.

Để nghiệm thu có gửi thư bằng dữ liệu hư cấu khi đang cấu hình SMTP thật, chạy:

```powershell
.\.venv\Scripts\python.exe -m tests.integration.release_acceptance --cached-build --full-checks
```

Lệnh này tự tạo project/SQL/Mailpit riêng, chạy SQL concurrency, tải/lỗi và Edge,
rồi dừng container test. Cần cổng 810x/14331/8026/1026/910x trống. `npm run test:e2e`
kiểm tra email mode trước và từ chối dùng SMTP Internet để gửi thư test.
