# Bàn giao ngày 07–08/11 — nghiệm thu, báo cáo và trình diễn

Thực hiện sớm ngày **02/11/2026** theo yêu cầu tiếp tục kế hoạch. Đã hoàn thiện
phần kiểm thử tải/lỗi hạ tầng, cài mới, báo cáo, sơ đồ, slide và source dự phòng.
Thông tin bìa: Kiến trúc hướng dịch vụ, Nhóm 12, TS. Dương Hữu Phúc; Phạm Minh
Huy — 524H009; hai thành viên còn lại ghi “Điền sau”.

## Kết quả cuối

| Kiểm tra | Kết quả và bằng chứng |
|---|---|
| Unit/startup/validation | 29 passed; 1 cảnh báo deprecation TestClient/httpx |
| Backend SQL Server/SMTP | 8/8 kịch bản; artifacts/backend-acceptance.json |
| Edge desktop/mobile | 4/4 bài; artifacts/browser-acceptance.json |
| Release tải/lỗi/cài mới | 7/7 kịch bản; artifacts/release/1d770842/acceptance.json |
| Docker một lệnh | start.ps1 -Detached hoàn tất, SQL/ba service/Mailpit healthy |
| Báo cáo | 14 trang PDF, nguồn Markdown; đã render và kiểm tra bố cục |
| Slide | 14 slide PPTX, sơ đồ và bảng API là đối tượng có thể sửa; cấu trúc/import/layout đạt |

Bài nghiệm thu release chạy từ **image build --no-cache**, project
`ibanking-acceptance-1d770842`, volume hoàn toàn mới. Thời gian UTC
06:25:42–06:29:17 ngày 02/11/2026. Image ID:
`sha256:16728d4aad6ad42aa45876c8232384437a47ab21fb2942c8d1ad1253e1847fbd`.
Các service dùng 8101–8103, SQL 14331, Mailpit 8026; proxy test 9101/9102.
Container test đã dừng bằng compose down; volume test được giữ để đối chiếu.
Project demo 8001–8003/14330 không bị kill/disconnect bởi bộ test này.

## Thử tải và vấn đề đã sửa

32 payment trên 8 tài khoản; 16 request process đồng thời; 64 hóa đơn, mỗi
payment 1 triệu/2 hóa đơn. Tất cả 32 response lần đầu là **200**, sau đó đối chiếu
trực tiếp đủ ba DB: đúng một DEBIT/UUID, số dư đúng, hai hóa đơn PAID đúng mã,
Payment SUCCEEDED đúng tổng và một outbox event.

| Đại lượng | Số đo cuối |
|---|---|
| HTTP process p50 | 4.073 giây |
| HTTP process p95 | 4.849 giây |
| HTTP process tối đa | 4.852 giây |
| Tổng thời gian chạy tải và đối chiếu | 15.417 giây |
| Số payment / thời gian trên | 2.076 payment/giây |

Thời gian tổng có cả kiểm tra hội tụ; throughput này không phải tải bền vững hoặc
SLA. Host còn chạy demo Docker và các công cụ khác. Không ngoại suy sang production.

Lần đầu `8a5b550b`: guard applock giữ kết nối chung pool ORM trong khi chờ REST,
khi nhiều request đồng thời thì các transaction ngắn không còn kết nối. Một
response 503 và 31 timeout client (mã 599 là ký hiệu của test, không phải HTTP từ
server). Sau recovery cả 32 payment vẫn có dữ liệu đúng, nhưng tiêu chí latency/
admission thất bại. Đã sửa trong `shared/locking.py`: engine NullPool riêng cho
session guard, không chiếm pool ORM; release rõ ràng khi thoát, invalidate khi
không xác định được acquisition/release. Bản sửa vượt qua lượt cache `896b896c`
và lượt cuối không cache `1d770842`. Giữ cả bằng chứng thất bại để truy vết.

## Lỗi được tạo trên hạ tầng thật

| Tình huống | Cách thử | Kết quả audit |
|---|---|---|
| Mất reply sau debit | Proxy đợi upstream 200 rồi giữ phản hồi 14 giây, vượt timeout HTTP client | Đối soát SUCCEEDED, một DEBIT, không REFUND |
| Mất reply sau finalize | Proxy giữ reply sau Tuition đã trả 200 | PAID giữ nguyên, Payment khôi phục SUCCEEDED |
| Phân hoạch mạng | docker network disconnect/connect proxy Tuition trong project test | Lúc mất mạng chưa debit; sau nối lại hoàn tất |
| Payment chết sau debit | SIGKILL sau khi proxy ghi nhận Account upstream 200, trước khi trả reply | Restart, worker tiếp tục phase, không trừ lần hai |
| SQL chết giữa transaction | Mở transaction thay số dư/ghi ledger chưa commit rồi SIGKILL SQL Server | Sau start, balance cũ và 0 entry chưa commit; payment retry thành công |
| Cài mới / diễn tập | Volume mới, seed, trả một kỳ rồi tất cả còn lại, SMTP OTP và biên nhận | Từ 10 triệu về 5 triệu, cả hai hóa đơn PAID; seed chạy lại không reset |

Proxy chỉ bật trong `infra/docker/compose.acceptance.yaml`. API điều khiển proxy
test không có trong demo mặc định; không dùng cấu hình acceptance để triển khai
công khai. Test không log OTP, bearer token hoặc key nội bộ.

## Lệnh tái hiện

Khởi động ứng dụng vẫn chỉ một lệnh: `powershell -ExecutionPolicy Bypass -File .\start.ps1`.
Chạy bộ kiểm thử chủ động bằng các lệnh độc lập sau khi đã cài dev dependencies:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m tests.integration.backend_acceptance
npm run test:e2e
.\.venv\Scripts\python.exe -m tests.integration.release_acceptance
```

Release test cần Docker Desktop, Python dev với pyodbc/ODBC Driver 18; cần cổng
14331/810x/8026/1026/910x trống. Mỗi lần tạo tên project và image mới. Có thể dùng
`--cached-build` để tiết kiệm thời gian, nhưng bằng chứng cuối trên dùng mặc định
không cache. Không chạy đồng thời hai release test vì chúng dùng cùng cổng host.

Backend/E2E mặc định tạo dữ liệu IT_* trong DB demo và giữ lại để đối chiếu;
release tách biệt toàn bộ dữ liệu và thao tác restart. Tham số `--workers` và
`--payments` cho phép điều chỉnh tải; các số đo trong tài liệu chỉ áp dụng lượt
được nêu rõ ở trên.

## Hồ sơ và giới hạn

- `submission/bao-cao-ibanking.pdf`: báo cáo 14 trang; bản Markdown cùng tên để sửa.
- `submission/trinh-bay-ibanking-v2.pptx`: slide trình bày 14 trang.
- `docs/diagrams/exported/`: Use Case, kiến trúc, ba ERD và sequence PNG.
- `docs/api.md` và `docs/api/openapi-*.json`: hợp đồng API và schema offline.
- `docs/demo-script.md`, `docs/submission-checklist.md`: diễn tập và phần nhóm cần điền.
- `submission/ibanking-source.zip`, `SOURCE-MANIFEST.json`, `SHA256SUMS.txt`: bản nguồn
  và hash đối chiếu. Không chứa .env riêng, SQL volume, node_modules hoặc .venv.

Nguồn Markdown đầy đủ ở `docs/final-report.md`, thông tin bìa ở `docs/team.json`;
builder dùng dữ liệu JSON nghiệm thu để điền số đo. Source backup chứa dữ liệu
demo/evidence hư cấu và mật khẩu **tài khoản demo** đã công khai, không chứa key
SQL/JWT/internal/SMTP riêng. ZIP không chứa Docker image; máy mới vẫn cần tải
image/package lần đầu. Báo cáo bàn giao PDF và nguồn Markdown để biên tập.

Đã kiểm tra cấu trúc PPTX, font khai báo, geometry, native table và import lại
bằng Artifact Tool, đồng thời xem từng slide. Chưa có kiểm chứng trên PowerPoint
của máy trình chiếu; nhóm cần mở thử trước khi bảo vệ. SMTP Internet chưa có tài
khoản của nhóm; Mailpit đã kiểm tra SMTP thực. Các nâng cấp ngoài phạm vi như
JWT revocation, rate limit, TLS, SQL login theo DB và tải dài hạn được ghi rõ trong
báo cáo. Hai thành viên còn lại/phân công thực tế đang chờ nhóm bổ sung.
