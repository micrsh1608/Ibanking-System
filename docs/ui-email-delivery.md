# Gửi email và trình diễn thanh toán

Ứng dụng chính chỉ dùng SMTP thật. Tài khoản SMTP xác định người gửi;
người nhận là email của tài khoản đang đăng nhập. Mọi lần cập nhật hồ sơ
được lưu thành bản chờ, gửi mã đến địa chỉ người dùng vừa nhập và chỉ lưu
sau khi xác minh đúng, kể cả khi giữ nguyên email đã xác minh. OTP/biên nhận
của giao dịch mới dùng email đã xác minh sau bước cập nhật đó.

Tài khoản `huy` mới chưa có email. Tạo thêm người trả thứ hai bằng:

```powershell
powershell -ExecutionPolicy Bypass -File .\demo-data.ps1 -CreateTestAccount -Email 'your-second-real-email'
```

Tài khoản mới là `huy2` / `HuyDemo_123!`, số dư ban đầu 10 triệu. Đăng nhập
và xác minh địa chỉ email thật của từng người trên Web trước khi thanh toán.
Lệnh tạo dữ liệu không gửi mã hoặc tự đánh dấu email đã xác minh.

Cấu hình SMTP thật theo [runbook](runbook.md), sau đó chạy:

```powershell
.\start.ps1
```

## 05/11 — OTP SMTP và email xác nhận

- OTP gửi qua SMTP đến email snapshot của người đăng nhập. Thư có mã một lần,
  UUID, sinh viên, MSSV, từng học kỳ, tổng tiền và hạn 5 phút. Không in mã ra log.
- Gửi lại sau 60 giây, hủy challenge/xác minh cũ; 5 lần sai bị chặn. SMTP lỗi làm
  vô hiệu challenge vừa tạo và cho phép thử gửi lại, không bắt đầu thanh toán.
- SUCCEEDED và một sự kiện `email_outbox` được commit cùng transaction.
  UNIQUE(payment_id,event_type) chặn tạo nhiều sự kiện cho cùng một biên nhận.
- Worker email độc lập với worker thanh toán, retry/backoff tối đa 300 giây,
  lưu số lần thử/lỗi và tiếp tục sau restart. Gửi mail không gọi debit/finalize.
- SMTP hỗ trợ login, SSL hoặc STARTTLS. Compose chính chỉ dùng SMTP thật.
  Biến SMTP đặt trong `infra/env/docker.env`; xem [runbook](runbook.md).

Mã nguồn chính: `services/payment/mailer.py`, `email_templates.py`, `outbox.py`,
`routes.py`, `coordinator.py`; revision `20261105_email_outbox` thêm outbox và
completed_at, giữ dữ liệu cũ. Không tự gửi lại email cho lịch sử trước migration.

SMTP có thể gửi trùng thư nếu mất ACK sau khi server đã nhận hoặc app dừng trước
khi ghi SENT. Message-ID cố định giúp đối chiếu; hệ thống bảo đảm một sự kiện
biên nhận và không trừ tiền lại, không tuyên bố gửi mail đúng một lần. Xem
[SMTP RFC 5321](https://www.rfc-editor.org/rfc/rfc5321.html).

## 06/11 — Web thanh toán và lịch sử

- Giữ thiết kế iBanking hiện tại, thêm Đóng học phí và Lịch sử trên máy tính/điện thoại.
- Hồ sơ người trả, CMND/CCCD, điện thoại, email, tài khoản/số dư lấy từ API và chỉ đọc.
- Tra MSSV, xem hóa đơn UNPAID/RESERVED/PAID và trả toàn bộ công nợ chưa đóng.
  UI tính tiền bằng BigInt theo đơn vị xu; server vẫn là nơi chốt snapshot/tổng tiền.
- Xem lại snapshot trước OTP, nhập mã nhận qua email và thanh toán cùng UUID.
- Hiển thị đang xử lý/đối soát, thành công, thất bại/hoàn tiền và tình trạng biên nhận.
  Poll GET để tra kết quả; không tạo giao dịch khác để thử lại khoản chưa rõ.
- Mất phản hồi tạo/process giữ UUID cũ; nút thử lại chỉ hoạt động sau request trước.
  Tải lại trang giữ duy nhất UUID/user ID trong sessionStorage, đăng nhập lại rồi
  tiếp tục challenge cũ. JWT và OTP không được ghi localStorage/sessionStorage.
- Lịch sử chỉ của người đăng nhập, có phân trang, mở chi tiết và tiếp tục giao dịch.
  Đăng xuất xóa thông tin đang hiển thị và dừng timer/poll của phiên cũ.

Gateway `services/account/gateway.py` chuyển các public API của Payment/Tuition
qua cổng 8001 cùng origin. Nó không chuyển internal key và không proxy route nội
bộ. Không cần mở CORS cho nhiều cổng hoặc thêm terminal/service web riêng.

## Trình diễn

1. Mở [iBanking](http://127.0.0.1:8001/ui/), đăng nhập `huy` / `HuyDemo_123!`.
2. Mở **Thông tin cá nhân**, nhập email thật và xác minh mã nhận tại địa chỉ đó.
   Sau đó chọn **Đóng học phí**, tra `SV20261013`. Nếu demo đã trả hết, tạo sinh viên/hóa
   đơn demo mới; không đổi hóa đơn PAID về UNPAID để tái diễn lại giao dịch cũ.
3. Kiểm tra toàn bộ hóa đơn chưa đóng và tổng tiền, đồng ý điều khoản rồi gửi OTP.
4. Mở hộp thư thật của email đã xác minh của người trả để lấy đúng mã giao dịch.
5. Nhập OTP, xác nhận thanh toán; xem số dư mới, email biên nhận và **Lịch sử**.
6. Khi mạng gián đoạn, giữ mã hiện tại, dùng Kiểm tra lại/Lịch sử; không tạo mã mới.

Để thử hai tài khoản trả cùng học phí, dùng hai phiên độc lập cho `huy` và
`huy2`, cùng tra một MSSV còn UNPAID và nhận OTP riêng tại email của từng
người. Chỉ một payment được trừ tiền và hoàn tất nhóm hóa đơn.

## Bằng chứng kiểm thử lịch sử ngày 05–06/11

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m tests.integration.backend_acceptance
npm ci
npm run test:e2e
```

- 29 pytest đạt: thêm OTP email, SMTP thất bại, revoke challenge, outbox retry,
  SSL/STARTTLS và gateway không chuyển khóa nội bộ. Một cảnh báo httpx của TestClient.
- 8 kịch bản SQL Server/SMTP đạt: các kiểm tra tài chính trước đó và tắt Mailpit,
  restart Payment, bật Mailpit; biên nhận được gửi, ledger vẫn chỉ một khoản trừ.
- **4/4 kiểm thử Edge đạt**: desktop trả một kỳ rồi tất cả còn lại; mobile 390px; mất phản hồi
  create/process; refresh và đăng nhập lại để tiếp tục UUID/OTP cũ.
- JSON kết quả ở `artifacts/backend-acceptance.json`, `artifacts/browser-acceptance.json`;
  screenshot desktop/mobile trong `artifacts/payment-*.png`.

Playwright dùng Edge đã cài trên Windows, Chromium trên các hệ khác. Node.js chỉ
là công cụ test; người dùng chạy ứng dụng Docker không cần Node. Browser tích hợp
của công cụ bị lỗi khởi tạo, nên QA hình ảnh và luồng được thực hiện bằng Edge headless.
Integration/browser của lượt kiểm thử lịch sử tạo dữ liệu IT riêng trong Docker
và giữ ledger để đối chiếu. Lượt đó có stop/start Mailpit và restart Payment; không chạy trong lúc
đang trình diễn giao dịch khác.

Ngày 07–08/11 còn kiểm thử tải/lỗi hạ tầng mở rộng, báo cáo/slides và diễn tập.
