# Đối chiếu mục 3–5: OTP, thành công và tính nhất quán — 04/11/2026

Ngày 05/11 dữ liệu demo chính đã được reset theo yêu cầu người dùng. Bằng chứng
bên dưới thuộc các lượt trước reset; xem [tự tạo dữ liệu demo mới](demo-data-reset.md).

Lượt rà soát mục 1 tiếp theo được ghi tại [đăng nhập và thông tin người dùng](login-user-requirements-review.md).
Số liệu `ee2d6bd8` bên dưới thuộc lượt nghiệm thu OTP trước phần bổ sung đăng nhập.

Phạm vi là ba mục trong ảnh đề bài người dùng cung cấp. Quy tắc thanh toán
hiện tại là trả toàn bộ công nợ chưa đóng của MSSV, theo xác nhận ngày 03/11.

## Những điểm đã sửa

1. Trước đây OTP ngẫu nhiên chỉ được ràng buộc bằng hash theo giao dịch, chưa
   bảo đảm hai mã số còn hiệu lực khác nhau. Đã thêm bộ cấp mã có transaction
   application lock chung trong payment_db, dấu vân tay HMAC có khóa bí mật và
   filtered unique index ở SQL Server. Gặp trùng thì sinh lại, không lưu mã rõ.
2. Giao diện trước đây cần bấm Gửi mã sau khi xác nhận. Hiện tự gửi sau khi tạo
   giao dịch thành công. Nếu gửi thất bại, nút thử lại giữ cùng UUID; tải lại
   trang có challenge đang hoạt động cũng không tự gửi thêm thư.

## Mục 3 — xác thực bằng OTP

| Yêu cầu | Cách thực hiện / bằng chứng |
|---|---|
| Gửi email đến người nộp | Email snapshot lấy từ Account bằng JWT; không nhận địa chỉ người trả do client tự truyền. UI tự yêu cầu gửi khi xác nhận. |
| Gắn một giao dịch cụ thể | Hash HMAC gồm UUID, challenge, tổng tiền, ID/phiên bản/số tiền từng hóa đơn và mã OTP. Sai giao dịch hoặc challenge bị từ chối. |
| Không trùng mã còn hiệu lực | Khóa cấp mã chung và unique index bảo vệ cả các yêu cầu chạy đồng thời; test ép hai transaction chọn cùng mã trên SQL Server vẫn cấp hai mã khác nhau. |
| Tối đa 5 phút | Hạn server bằng thời điểm cấp + 5 phút; tại đúng giây 300 đã hết hiệu lực. Process lần đầu cũng kiểm tra hạn gốc. |
| Dùng một lần | Khóa theo UUID, ghi OTP_VERIFIED và xóa otp_hash trong cùng transaction; 5 yêu cầu xác minh đồng thời chỉ một yêu cầu thành công. |
| Gửi lại / nhập sai | Gửi lại sau 60 giây, thay challenge và mã, hủy xác minh trước đó; tối đa 5 lần nhập sai cho mỗi challenge. |
| Không xử lý từ OTP sai/hết hạn | Verify và process đều có kiểm tra phía server, không chỉ dựa vào nút trên UI. Test xác nhận không có debit hoặc thay đổi học phí. |

`otp_fingerprint` chỉ phục vụ kiểm tra bằng nhau và không trả qua API. Chỗ dành
mã giữ tới hạn gốc dù đã dùng; mã hết hạn được dọn khi cấp mã tiếp theo. Nếu
128 lượt sinh vẫn trùng, trả 503, rollback và không gửi email.

## Mục 4 — xử lý giao dịch thành công

| Bước đề bài | Cách thực hiện / bằng chứng |
|---|---|
| Kiểm tra lại giao dịch và số dư | Tuition khóa/kiểm tra toàn bộ tập công nợ, version và tổng snapshot; Account khóa tài khoản, kiểm tra chủ, ACTIVE và số dư ngay trong transaction debit. |
| Trừ đúng số tiền | Bút toán DEBIT gắn UUID, tài khoản và tổng tiền; debit lặp cùng UUID trả kết quả trước, không trừ thêm. |
| Cập nhật đã thanh toán | Finalize khóa cả nhóm và ghi tất cả PAID, paid_payment_id, thời gian, version trong một transaction Tuition. |
| Lưu lịch sử | Payment lưu SUCCEEDED/DONE/completed_at sau khi nhận kết quả hợp lệ; history có kiểm tra chủ JWT. |
| Email xác nhận | SUCCEEDED và sự kiện biên nhận được commit cùng transaction; outbox có unique(payment_id,event_type), worker gửi lại độc lập khi SMTP lỗi. |
| Hiển thị kết quả | UI hiện thành công, số tiền, sinh viên, danh sách hóa đơn, số dư mới và trạng thái biên nhận; có lịch sử và khôi phục UUID sau reload. |

## Mục 5 — giao dịch đồng thời và phục hồi

| Tình huống | Kết quả phải giữ / đã kiểm tra |
|---|---|
| Cùng tài khoản, hai khoản 7 triệu từ số dư 10 triệu | Chỉ một khoản thành công; số dư cuối đúng 3 triệu và một DEBIT. Khóa UPDLOCK/HOLDLOCK bao quanh kiểm tra và trừ tiền. |
| Hai tài khoản trả cùng MSSV | Chỉ một nhóm giữ/finalize được toàn bộ công nợ; người thua không bị trừ, tất cả hóa đơn thuộc UUID người thắng. |
| Cùng UUID được xử lý nhiều lần | Khóa Payment cùng UUID, API nội bộ idempotent, ledger và outbox có ràng buộc duy nhất. |
| Mất phản hồi sau khi Account/Tuition commit | Giữ trạng thái đối soát và retry cùng UUID; không suy đoán hoàn tiền từ timeout. |
| Cần hủy | Nhả/fence Tuition trước rồi cancel Account; dấu hủy chặn reserve/debit đến muộn. Không hoàn tiền cho nhóm đã PAID. |
| Payment/SQL Server dừng đột ngột | Phase và ý định xử lý đã lưu bền vững; worker đọc lại sau restart; transaction SQL chưa commit bị rollback. |
| OTP hết hạn trong lúc phục hồi | Chỉ phục hồi giao dịch đã được chấp nhận xử lý trước hạn. Không khởi tạo giao dịch mới từ mã hết hạn hoặc bỏ dở khoản đã trừ. |

Ba service dùng transaction cục bộ và saga phục hồi. Trong sự cố, giao dịch có
thể tạm PROCESSING/PENDING_RECONCILIATION; giao diện yêu cầu chờ/tra cứu cùng UUID.
Chỉ kết luận thành công sau khi kiểm tra kết quả Account/Tuition. Các bài nghiệm
thu đối chiếu trực tiếp cả ba database sau khi giao dịch kết thúc.

SMTP có ngữ nghĩa gửi ít nhất một lần: nếu máy chủ nhận thư nhưng mất ACK, có
thể có biên nhận trùng. Message-ID ổn định và một sự kiện outbox giúp đối chiếu;
việc retry email không lặp hiệu lực tiền. Chưa kiểm thử khả năng thư đến hộp thư
Internet ở lượt này; toàn bộ thư thử nghiệm được cô lập vào Mailpit.

## Nâng cấp và kiểm chứng

Migration `20261104_unique_active_otp` thêm cột/index chống trùng. Mã PENDING_OTP
cũ chưa có dấu vân tay cần gửi lại sau cập nhật. UUID, tiền, hóa đơn, lịch sử và
các giao dịch đang đối soát được giữ nguyên; cấu hình SMTP riêng được giữ nguyên.

Lượt nghiệm thu Docker độc lập `ee2d6bd8` đạt toàn bộ; build dùng cache, dữ liệu
khởi tạo trên volume mới, các thử nghiệm email đều vào Mailpit. Bằng chứng:

| Bộ kiểm tra | Kết quả | File |
|---|---|---|
| Pytest nghiệp vụ/migration | 80 đạt, 1 cảnh báo thư viện TestClient/httpx | `tests/unit/` |
| SQL Server: quyền truy cập, đồng thời, idempotency, phục hồi, SMTP lỗi | 8 kịch bản đạt | `artifacts/backend-acceptance.json` |
| SQL Server: cấp trùng cưỡng bức, 8 OTP đồng thời, sai/hết hạn/gửi lại, 5 xác minh đồng thời, thành công/biên nhận | 7 kịch bản đạt | `artifacts/otp-consistency-acceptance.json` |
| Cài mới, tải, mất phản hồi commit, ngắt mạng, SIGKILL Payment và SQL Server | 7 kịch bản đạt | `artifacts/release/ee2d6bd8/acceptance.json` |
| Edge: tài khoản, toàn bộ công nợ, OTP tự gửi/thử lại, thanh toán, refresh và lịch sử | 15 đạt, không lỗi hoặc flaky | `artifacts/browser-acceptance.json` |

Bài tải gồm 32 giao dịch, 64 hóa đơn, 16 yêu cầu đồng thời: 32 phản hồi HTTP 200,
audit cuối khớp ba DB, p95 4,765 giây và cao nhất 4,812 giây trên máy kiểm thử.
Đây là số liệu nghiệm thu cục bộ, chưa phải cam kết hiệu năng triển khai thực tế.
Pytest có kiểm tra mốc 299/300/301 giây, gửi lại, sai mã, trùng mã, một lần sử
dụng, SMTP lỗi, bù trừ và phục hồi giao dịch đã bắt đầu trước hạn OTP.

Ứng dụng chính đã được cập nhật bằng `start.ps1 -Detached`: UI và cả ba
`/health/db` trả HTTP 200. SQL Server chính đã có revision/cột/filtered unique
index mới, không còn mã PENDING_OTP chưa đăng ký. Hash dữ liệu số dư, ledger,
hóa đơn và lịch sử trước/sau cập nhật khớp; hash hai file cấu hình riêng cũng
khớp. Chỉ đọc kiểm tra trên ứng dụng chính, không tạo payment hoặc gửi thư test
qua SMTP thật. Kết quả đối chiếu cục bộ lưu tại
`artifacts/otp-upgrade-main-before.json` và `artifacts/otp-upgrade-main-after.json`.

Chạy đầy đủ trên project Docker riêng:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m tests.integration.release_acceptance --cached-build --full-checks
```

Các file chính: `services/payment/otp.py`, `routes.py`, `coordinator.py`,
`outbox.py`, `models/payment.py`, `migrate.py`, `frontend/payments.js`;
khóa số dư/học phí tại `services/account/internal_routes.py` và
`services/tuition/internal_routes.py`. PDF/PPTX cũ vẫn là tài liệu của mốc trước;
cần cập nhật phần thuyết minh quy tắc mới trước khi nộp chính thức.
