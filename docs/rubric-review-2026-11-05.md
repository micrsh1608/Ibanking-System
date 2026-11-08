# Rà soát dự án theo đề bài và phiếu chấm giữa kỳ

**Bản rà soát lịch sử và kết quả xử lý:** những thiếu sót về tài liệu/sơ đồ và
truy vết bên dưới đã được xử lý ở bộ bàn giao tiếp theo. Dùng
`docs/pre-submit.md`, PDF hiện hành, PPTX v3 và
`artifacts/final-delivery-acceptance.json` để đọc trạng thái mới. Chỉ thông tin
hai thành viên/phân công và diễn tập trên máy trình chiếu còn chờ nhóm.

Ngày rà soát: 05/11/2026, giờ Việt Nam. Nguồn yêu cầu là ba ảnh đề bài và
phiếu chấm do người dùng cung cấp trong cuộc trò chuyện. Các số điểm bên dưới
là trọng số của rubric, không phải điểm đã được giảng viên chấm.

## Kết luận và phạm vi

Mã nguồn đã hiện thực các luồng nghiệp vụ bắt buộc: đăng nhập bằng tài khoản
được cấp, tra MSSV, thanh toán toàn bộ công nợ, OTP qua email, lịch sử và biên
nhận. Ba service Account, Payment và Tuition chạy độc lập, giao tiếp REST và
sở hữu ba database riêng. Không cần bổ sung đăng ký tài khoản công khai.

Hồ sơ bàn giao chưa đồng bộ với mã nguồn. Báo cáo PDF/Markdown và slide còn
mô tả lựa chọn một/nhiều hóa đơn, trong khi API và UI hiện chỉ chấp nhận
`ALL_UNPAID`. Cần sửa hồ sơ và diễn tập trước khi coi bộ nộp là hoàn tất.

Bản rà soát chỉ đọc mã nguồn, sản phẩm và dữ liệu demo. Kiểm thử có ghi dữ liệu,
ngắt mạng và dừng service chạy trên project/volume acceptance riêng; thư thử
chỉ gửi vào Mailpit của project đó. Không dùng kết quả này để khẳng định hệ
thống đã được nghiệm thu vận hành ngân hàng hoặc mọi loại sự cố có thể xảy ra.

## Đối chiếu tám tiêu chí

| Tiêu chí | Trọng số | Kết quả | Bằng chứng và phần cần hoàn thiện |
|---|---:|---|---|
| 1. Phân tích nghiệp vụ và UML | 1,0 | Có, cần đồng bộ bản xuất | `docs/architecture.md`, `docs/diagrams/use-cases.puml`, ba ERD. Use Case PNG/PPTX cũ chưa khớp nguồn PlantUML hiện tại; ERD Account cần thể hiện phần xác minh email mới nếu trình bày schema đầy đủ. |
| 2. Kiến trúc Microservices | 1,5 | Đạt phần hiện thực | Ba app/DB riêng; REST trong `services/payment/clients.py`; gateway tại Account; có hình `microservices.png`. Dùng chung image Docker và SQL Server cho demo vẫn chạy ba service riêng. Bổ sung đường Account → SMTP cho xác minh email trong sơ đồ hiện tại. |
| 3. Thiết kế REST API | 1,0 | Đạt | `docs/api.md`, Pydantic request/response, JWT/internal key, HTTP status, validation/error handling; cả ba OpenAPI offline khớp API đang chạy. |
| 4. Database và persistence | 1,0 | Đạt | SQL Server, model/migration riêng; PK/FK/UNIQUE/CHECK; Decimal/NUMERIC(18,2), số dư không âm; volume bền vững và kiểm tra rollback/restart. |
| 5. Chức năng và payment workflow | 2,0 | Đạt trong các kịch bản kiểm thử | Hồ sơ người trả lấy từ JWT, chỉ đọc trên màn thanh toán; tự tra MSSV; chỉ toàn bộ công nợ; điều khoản, số dư, trạng thái hóa đơn; OTP và kết quả/lịch sử/biên nhận. |
| 6. Transaction và concurrency | 1,5 | Đạt trong các kịch bản kiểm thử | SQL transaction, UPDLOCK/HOLDLOCK, application lock, unique ledger, reservation, idempotency và saga phục hồi. Đã kiểm tra cả hai tình huống bắt buộc. |
| 7. UI và integration | 0,5 | Đạt trong các kịch bản kiểm thử | Web tích hợp API: đăng nhập → tra cứu → xác nhận → OTP → kết quả/lịch sử; kiểm thử desktop/mobile, số dư bằng công nợ, số dư thiếu, hồ sơ thiếu và phản hồi đến muộn. |
| 8. Tài liệu, deployment và demo | 1,5 | Có deployment; hồ sơ/demo cần hoàn thiện | README/runbook, Docker một lệnh, API docs, PDF/PPTX/ZIP đã có. PDF/PPTX còn quy tắc cũ; thiếu thông tin hai thành viên và phân công; cần dữ liệu chưa thanh toán, diễn tập và trình bày hai ca concurrency. |

## Các yêu cầu nghiệp vụ đã kiểm tra

| Yêu cầu | Cách hiện thực và xác minh |
|---|---|
| Username/password, không yêu cầu đăng ký mới | Account băm mật khẩu, cấp JWT, kiểm tra active; không có UI/route đăng ký công khai. |
| Họ tên, điện thoại, email, số dư, lịch sử | `users`, `accounts`, `payments`; `/users/me`, `/accounts/me`, lịch sử giới hạn đúng chủ. |
| Người trả được tự điền và không sửa trên màn thanh toán | UI dùng các phần tử hiển thị; server lấy hồ sơ/tài khoản qua JWT, từ chối trường payer/account/amount tự truyền. Cập nhật hồ sơ nằm ở chức năng riêng. |
| Nhập MSSV tự tra sinh viên/học phí | UI debounce 650 ms; phản hồi cũ không thay MSSV mới; không tồn tại hoặc không còn công nợ thì không xác nhận được. |
| Thanh toán toàn bộ | `PaymentCreate` chỉ có `ALL_UNPAID`, bắt buộc đồng ý điều khoản; server chốt toàn bộ hóa đơn UNPAID. Tuition từ chối khi tập công nợ đã thay đổi. |
| Số dư lớn hơn hoặc bằng khoản phải trả | UI/API kiểm tra trước xác nhận; Account kiểm tra lại dưới khóa dòng khi trừ tiền. Bằng nhau được phép. |
| OTP gắn giao dịch, không trùng các mã còn hạn | HMAC gắn UUID/challenge/tổng tiền/hóa đơn; cấp mã dưới khóa SQL chung và filtered unique index cho fingerprint. |
| OTP tối đa 5 phút, dùng thành công một lần | Kiểm tra hạn ở verify và trước lần process đầu; tiêu thụ hash/trạng thái; resend hủy challenge cũ; giới hạn 5 lần sai. |
| Thành công cập nhật đúng dữ liệu | Reserve → debit → finalize; sau đó Payment lưu SUCCEEDED và outbox trong cùng transaction cục bộ; kết quả/lịch sử liên kết đúng UUID. |
| Gửi email xác nhận | Worker gửi receipt outbox, retry tách khỏi thao tác trừ tiền. Một event/payment; SMTP có thể nhận thư trùng nếu mất ACK. |
| Xác minh địa chỉ email trước thanh toán | Chỉ kích hoạt email sau khi nhập đúng mã gửi đến địa chỉ đó; email chờ chưa thay hồ sơ đang dùng; OTP/receipt dùng email đã xác minh khớp snapshot. Đây là phần bổ sung theo yêu cầu người dùng. |

## Hai tình huống concurrency bắt buộc

1. **Một tài khoản, nhiều giao dịch:** hai khoản 7 triệu cạnh tranh trên số dư
   10 triệu; chỉ một khoản được trừ, số dư cuối 3 triệu, không âm. Kiểm tra
   balance/ledger nằm trong cùng transaction có khóa dòng.
2. **Nhiều tài khoản, cùng khoản học phí:** hai người trả cùng một MSSV; chỉ một
   giao dịch hoàn tất nhóm hóa đơn, một debit thành công; bên còn lại bị từ
   chối hoặc bù trừ đúng. Kiểm tra cùng tập hóa đơn, trạng thái và UUID.

Một transaction SQL không bao trùm cả ba service. Mỗi service commit cục bộ;
Payment lưu phase, retry idempotent và bù trừ có hàng rào. Khi chưa rõ kết quả,
UI hiển thị PROCESSING/PENDING_RECONCILIATION. Chỉ kết thúc SUCCEEDED sau khi
đã xác nhận debit và hóa đơn PAID. Cần giải thích rõ điều này khi bảo vệ.

## Điều kiện giới hạn điểm trong phiếu chấm

| Điều kiện của rubric | Điểm tối đa khi thiếu | Hiện trạng |
|---|---:|---|
| Không có sản phẩm chạy/demo | 4,0 | Có ứng dụng Docker, health và kiểm thử UI. |
| Chỉ là monolith, không có service thực sự giao tiếp | 6,5 | Ba FastAPI process/container, DB riêng và HTTP REST thực. |
| Không có quy trình OTP | 7,0 | Có SMTP/challenge/hạn/dùng một lần và kiểm thử SQL. |
| Không có giải pháp transaction/concurrency | 7,5 | Có giải pháp và kiểm thử đồng thời, rollback, mất reply, crash. |
| Không có Microservices Architecture Diagram | 8,0 | Có cả Mermaid và PNG/PPTX. |

Không phát hiện điều kiện giới hạn điểm nào đang thiếu trong sản phẩm hiện
thực. Phần demo và giải thích trực tiếp vẫn cần nhóm thực hiện đúng lúc bảo vệ.

## Những việc cần hoàn thiện trước khi nộp

### Ưu tiên 1: đồng bộ báo cáo, slide, sơ đồ và số liệu

- `docs/final-report.md` và `submission/bao-cao-ibanking.md` còn mô tả chọn
  một/nhiều hóa đơn tại phạm vi nghiệp vụ, UI và kịch bản demo.
- `submission/bao-cao-ibanking.pdf`: trang 2 còn cho chọn từng kỳ; trang 12
  còn ghi 29 unit và diễn tập trả một kỳ; trang 13 còn demo chọn một kỳ và
  mô tả bootstrap tự seed cũ. Bản hiện tại mặc định chỉ tạo schema, seed phải
  yêu cầu rõ ràng và tài khoản demo mới còn cần xác minh email.
- `submission/trinh-bay-ibanking-v2.pptx`: slide 8 nói client gửi lựa chọn
  hóa đơn; slide 14 demo chọn một hóa đơn; slide 2/Use Case PNG là bản cũ.
- Builder `scripts/build_presentation.mjs` còn cùng nội dung cũ và tham chiếu
  các đường dẫn source đã đổi; phải sửa builder trước khi xuất lại.
- `docs/architecture.md`/sơ đồ xuất cần thể hiện Account gửi mã xác minh email,
  trạng thái email đã xác minh, thông tin điều khoản trong snapshot nếu trình
  bày schema chi tiết. Ghi rõ thuộc tính nào được lược khỏi sơ đồ tổng quan.
- `docs/final-acceptance.md`, `docs/assessment.md` có số liệu lịch sử 29/4;
  dùng kết quả mới trong bản rà soát này khi trình bày hiện trạng. Không lấy
  số liệu lượt cũ gán cho image hoặc lượt kiểm thử mới.

### Ưu tiên 2: chuẩn bị dữ liệu và nội dung bảo vệ

- Điền tên/MSSV hai thành viên còn lại, mã nhóm báo cáo và phân công thực tế
  khi nhóm có thông tin; cập nhật bìa từ `docs/team.json`.
- MSSV demo đang được dùng đã trả các khoản trong ảnh; cần chuẩn bị khoản
  UNPAID mới hoặc bộ diễn tập riêng trước buổi demo. Dùng `demo-data.ps1
  -AddTuition` theo `docs/demo-data-reset.md`; tài khoản phải đủ số dư và email
  đã xác minh. Chưa cần xóa dữ liệu hiện có để thực hiện việc này.
- Chèn bước xác minh email vào kịch bản dữ liệu mới. Luồng thanh toán bắt buộc
  là trả toàn bộ công nợ, đồng ý điều khoản, nhận OTP rồi thanh toán.
- Diễn tập hai tình huống cạnh tranh, trình bày số dư cuối, số debit và mã
  thanh toán hóa đơn; chuẩn bị JSON/ảnh làm bằng chứng khi không chạy tải trực tiếp.
- Mở PDF/PPTX trên máy trình chiếu và kiểm tra trước Docker/image/cổng/mạng.
  Máy đã có image khớp source có thể chạy bằng `start.ps1 -Detached` mà không
  truy cập registry; máy mới vẫn cần tải image/package lần đầu.

### Ưu tiên 3: nâng chất lượng nếu hướng tới mức 10

Đã có integration/E2E/concurrency test, idempotency, gateway và recovery/outbox.
Logging hiện có lỗi database, recovery và receipt gắn payment_id, nhưng chưa
có request/trace ID xuyên gateway và ba service. Có thể bổ sung structured log
và correlation ID, giữ bí mật/password/OTP/JWT ngoài log. Đây là cải tiến cho
mức engineering cao, không thay thế việc hoàn thiện hồ sơ bắt buộc.

Rubric mức 9,0–9,5 yêu cầu code/kiến trúc tốt, ownership rõ, API docs, automated
testing, deployment thuận tiện và giải thích quyết định thiết kế. Sản phẩm có
bằng chứng cho phần kỹ thuật này; chỉ nên đặt mục tiêu điểm sau khi hồ sơ đã
nhất quán và nhóm diễn tập thành công. Không suy ra điểm 10 từ số test pass.

## Bằng chứng kiểm thử

Lượt mới `9592abc6` hoàn tất lúc 13:49 ngày 05/11/2026 giờ Việt Nam, project
`ibanking-acceptance-9592abc6`, SQL/Mailpit/volume tách biệt. Image dùng build
cache; database của lượt cài mới nằm trên volume mới. Đây không phải lượt
build image không cache.

| Phạm vi | Kết quả mới |
|---|---|
| Unit/validation/startup | 144 passed, gồm 10 bài launcher; một cảnh báo deprecation thư viện TestClient |
| Edge desktop/mobile | 26 passed, 0 failed/skipped/flaky |
| Backend SQL concurrency | 8/8 kịch bản đạt |
| OTP và nhất quán sau thành công | 7/7 kịch bản đạt |
| Xác minh quyền sở hữu email | 5/5 kịch bản đạt |
| Cài mới, tải, mất reply, ngắt mạng, crash | 7/7 kịch bản đạt; tải 32 payment/16 request process đồng thời |
| API đang chạy | Ba `/health/db` trả 200; ba OpenAPI offline khớp live; UI trả 200 và no-store |

Kết quả mới của lượt rà soát được ghi tại
`artifacts/requirements-review-latest.json`. Nhật ký unit:
`artifacts/rubric-unit-checks.log`. Kiểm tra API đang chạy:
`artifacts/rubric-review/live-checks.json`.

Lệnh tái hiện đầy đủ trên project riêng:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m tests.integration.release_acceptance --cached-build --full-checks
```

Full acceptance có thao tác kill/disconnect ở project riêng và cần Docker,
ODBC, dev dependencies cùng các cổng acceptance trống. Demo chính đã cấu hình
SMTP Internet; bài kiểm thử luôn dùng SMTP Mailpit riêng. Kiểm tra cấu hình
SMTP không tự chứng minh thư Internet đã đến inbox trong lượt rà soát này.
