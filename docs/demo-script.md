# Kịch bản trình diễn 5–10 phút — Nhóm 12

Môn Kiến trúc hướng dịch vụ; giảng viên TS. Dương Hữu Phúc. Phạm Minh Huy,
MSSV 524H009; hai thành viên còn lại điền sau. Nhóm tự bổ sung người thuyết trình
từng phần theo phân công thực tế; không coi vai trò gợi ý là thành tích đã xác nhận.

## Chuẩn bị trước giờ trình bày

- Cài Docker Desktop và chọn Linux containers. Lần tải image đầu cần mạng;
  chạy trước tại nhà, không đợi đến giờ bảo vệ để build lần đầu.
- Tại thư mục gốc, chạy `powershell -ExecutionPolicy Bypass -File .\start.ps1`.
  Đây là một lệnh duy nhất, log gom vào một terminal; Ctrl+C dừng.
- Mở UI `http://127.0.0.1:8001/ui/`, Mailpit `http://127.0.0.1:8025` và slide.
  Kiểm tra `/health/db` của ba service trả 200.
- Trên **volume mới**: `huy` / `HuyDemo_123!`, MSSV `SV2026001`, số dư 10 triệu,
  HK1 2 triệu và HK2 3 triệu. Volume đã dùng giữ trạng thái thanh toán qua restart;
  kiểm tra công nợ trước khi trình bày. Không dùng `down -v` để reset dữ liệu đang có.
- Có thể dùng một project rehearsal riêng có volume mới để diễn tập. Bộ
  `tests.integration.release_acceptance` đã tự làm việc này ở cổng 810x/8026;
  đây là bài kiểm thử có thao tác kill/disconnect, không chạy trong buổi demo trực tiếp.
- Đảm bảo hai thành viên còn lại đã được điền trong `docs/team.json`, bìa và PPTX.
  Lưu PDF/PPTX/ZIP và ảnh nghiệm thu sang USB trước khi đi.

## Nội dung theo thời gian

| Thời gian | Thao tác / lời giải thích | Bằng chứng mong đợi |
|---|---|---|
| 0:00–1:00 | Giới thiệu Account, Tuition, Payment; DB riêng, REST và worker | Sơ đồ kiến trúc, terminal Docker đã healthy |
| 1:00–2:00 | Đăng nhập, xem hồ sơ chỉ đọc, tra MSSV | Đúng tên sinh viên, hai hóa đơn và tổng 5 triệu trên volume mới |
| 2:00–3:30 | Chọn HK1; xác nhận snapshot; mở Mailpit; nhập OTP; thanh toán | Một UUID; HK1 PAID; số dư 8 triệu |
| 3:30–4:30 | Xem lịch sử và biên nhận | Payment SUCCEEDED, đúng hóa đơn/tổng/UUID; email biên nhận |
| 4:30–6:00 | Chọn toàn bộ công nợ còn lại, xác minh OTP và thanh toán | Chỉ HK2 còn lại 3 triệu; số dư cuối 5 triệu, cả hai PAID |
| 6:00–7:30 | Trình bày cạnh tranh 7 triệu + 7 triệu và hai người trả cùng hóa đơn | JSON backend: chỉ một bên thắng, không âm số dư/không trả trùng |
| 7:30–9:00 | Trình bày fault test và kết quả tải | JSON release: commit mất reply, ngắt mạng, SIGKILL Payment/SQL và audit ba DB |
| 9:00–10:00 | Giải thích idempotency, tombstone và giới hạn | Một UUID dùng lại, SQL local transaction + saga; SMTP có thể gửi thư trùng khi mất ACK |

Nếu chỉ có 5 phút, thực hiện một hóa đơn, xem kết quả/biên nhận và dành phút cuối
cho sơ đồ cùng bằng chứng concurrency. Chế độ toàn bộ công nợ được minh họa bằng
ảnh và JSON từ buổi diễn tập nếu không đủ thời gian.

## Khi gặp sự cố

- **Process chậm/mất phản hồi:** giữ UUID, mở lịch sử và làm mới kết quả. Khi đang
  đối soát, giải thích trạng thái đúng như hệ thống; không tạo payment mới để thử lại.
- **OTP chưa thấy:** kiểm tra thư có đúng UUID, email người trả và thời gian.
  Mailpit không phải hộp thư Internet. Nếu resend, mã cũ không còn hiệu lực.
- **Biên nhận đang chờ:** thanh toán vẫn đã thành công; worker gửi lại email riêng.
  Không bấm lại thao tác trừ tiền để “gửi lại thư”.
- **Docker chưa sẵn sàng/cổng bị chiếm:** chạy `start.ps1 -Check`, xem runbook;
  nếu không xử lý kịp, dùng PDF/PPTX, ảnh và JSON nghiệm thu đã lưu, nói rõ đây là
  bằng chứng diễn tập. Source ZIP không chứa Docker image nên không tự chạy offline
  trên một máy chưa tải image.
- **Đã trả hết dữ liệu mẫu:** dùng kết quả đã lưu hoặc chuẩn bị project riêng trước
  buổi trình bày. Không xóa volume hoặc sửa số dư/PAID trong lúc bảo vệ.

## Câu hỏi thường gặp

**Vì sao không có một transaction cho ba DB?** Mỗi service sở hữu DB và commit
cục bộ; Payment lưu phase, gọi REST idempotent và đối soát/bù trừ. Không giữ SQL
transaction mở khi chờ HTTP. UI phân biệt đang xử lý với thành công cuối.

**Làm sao không trừ tiền hai lần?** UUID, khóa theo thao tác/tài khoản, unique
ledger và kiểm tra payload. Retry sau commit lấy lại kết quả cũ; cùng UUID khác
dữ liệu bị từ chối. cancel/release lưu hàng rào để chặn request đến muộn.

**Email có đúng một lần không?** Một outbox event/payment, nhưng SMTP có thể nhận
thư rồi mất ACK. Retry có thể gửi trùng thư; không làm lặp ledger hoặc thanh toán.
