# Cài đặt, chạy và kiểm thử

Các lệnh chạy từ thư mục gốc bằng PowerShell. Python đã kiểm tra: 3.13.7.

## Chạy toàn bộ bằng một lệnh

```powershell
.\start.ps1
```

Chỉ cần Docker Desktop đã cài và bật Linux containers. Script tự khởi động
Docker Desktop khi engine chưa chạy, tạo `infra/env/docker.env` nếu chưa có,
build image và chạy SQL Server, job tạo bảng/seed, ba API, Mailpit.
Không cần Python hoặc môi trường `.venv` trên máy để chạy cách này.

Log của các container hiển thị chung; nhấn **Ctrl+C** để dừng cả dự án.
Script dừng container, giữ nguyên dữ liệu SQL Server và cấu hình riêng.
Các lần sau dùng lại đúng lệnh trên; Docker tái sử dụng lớp build đã cache.

- `.\start.ps1 -Detached`: chạy nền, chờ các API healthy rồi trả terminal.
- `.\start.ps1 -Check`: kiểm tra Docker/Compose và chuẩn bị cấu hình, không chạy container.
- `docker compose --env-file infra/env/docker.env stop`: dừng khi đang chạy nền.

Nếu PowerShell chặn script:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Giao diện ở `http://127.0.0.1:8001/ui/`, Mailpit ở `http://127.0.0.1:8025`.
Account/Payment/Tuition Swagger lần lượt ở các cổng 8001/8002/8003, đường dẫn `/docs`.
Nếu cổng đã có ứng dụng khác dùng, dừng ứng dụng đó trước khi khởi động dự án.

## Windows và SQL Server

1. Cài Python và Microsoft ODBC Driver 18 for SQL Server.
2. Tạo môi trường ảo nếu chưa có, rồi cài dependency:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

3. Nếu **chưa có** `.env`, sao chép `.env.example`. Giữ tệp riêng hiện có.

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48)); print(secrets.token_urlsafe(48))"
```

Điền hai chuỗi khác nhau vào `JWT_SECRET_KEY` và `INTERNAL_API_KEY`; sửa `DB_SERVER`.
Không gửi các giá trị khóa vào chat hoặc đưa vào Git.
Không đặt `DB_USER`/`DB_PASSWORD` nếu dùng Windows Authentication.
Nếu dùng SQL login, đặt cả hai. Tuition có thể dùng `TUITION_DB_USER` và
`TUITION_DB_PASSWORD` riêng, hoặc dùng chung `DB_USER`/`DB_PASSWORD`.

4. Dùng SSMS chạy ba script trong `infra/sql/` để tạo database. Tài khoản chạy
ứng dụng cần quyền với các DB tương ứng. Sau đó khởi tạo bảng và seed:

```powershell
.\.venv\Scripts\python.exe -m services.account.seed
.\.venv\Scripts\python.exe -m services.payment.init_db
.\.venv\Scripts\python.exe -m services.tuition.seed
```

Các script không xóa dữ liệu hiện có. `create_all()` không thay cho migration
khi cập nhật cột/ràng buộc của bảng đã có; việc thêm migration nằm trong kế hoạch.
Migration có revision chạy trước seed; Payment tạo bảng snapshot/điều phối mới,
giữ nguyên các bảng prototype cũ. Xem [migration](migrations.md).

5. Khi cần debug từng service bằng Python, chạy riêng các lệnh dưới đây.
Để chạy toàn bộ dự án trong một terminal, dùng `start.ps1` như hướng dẫn đầu tài liệu.

```powershell
.\.venv\Scripts\python.exe -m uvicorn services.account.main:app --reload --port 8001
.\.venv\Scripts\python.exe -m uvicorn services.payment.main:app --reload --port 8002
.\.venv\Scripts\python.exe -m uvicorn services.tuition.main:app --reload --port 8003
```

Mở Account `/ui/` và từng service `/docs`. Đăng nhập `huy` / `HuyDemo_123!`.
Dùng JWT trả về để Authorize trong Tuition Swagger, tra `SV2026001`.
Payment lấy hồ sơ/tài khoản và học phí qua REST; xem [cách thử backend](backend-delivery.md).
Khi chạy bằng Python, cấu hình SMTP theo bảng dưới. Worker phục hồi và worker
email mặc định bật; không cần chạy chúng trong terminal riêng.

## Docker để trình diễn

Cần Docker Desktop đang chạy Linux containers và có đủ tài nguyên cho SQL Server.
Image SQL Server yêu cầu chấp nhận EULA và mật khẩu `sa` theo chính sách độ mạnh.
Tham khảo [hướng dẫn Microsoft](https://learn.microsoft.com/en-us/sql/linux/quickstart-install-connect-docker?view=sql-server-ver16).

```powershell
.\.venv\Scripts\python.exe -m scripts.setup_demo_env
docker compose --env-file infra/env/docker.env config --quiet
docker compose --env-file infra/env/docker.env up --build -d
docker compose --env-file infra/env/docker.env ps -a
```

Script tạo ba bí mật ngẫu nhiên trong `infra/env/docker.env`, đã được bỏ qua bởi
Git và Docker build. Nếu tệp đã có, script giữ nguyên và kết thúc với thông báo.
Không dùng `docker compose config` không có `--quiet` khi chia sẻ output vì lệnh
đó có thể hiển thị giá trị môi trường.

Luồng khởi động: SQL Server healthy → job `db-init` tạo ba DB và bảng/seed → ba API.
`db-init` kết thúc `Exited (0)` là bình thường. Dữ liệu SQL Server lưu trong named volume.
Các cổng demo chỉ bind `127.0.0.1`; SQL Server ở `127.0.0.1,14330` nếu cần mở SSMS.
Demo dùng `sa` cho đơn giản; tách login theo từng DB trước khi triển khai công khai.

```powershell
docker compose --env-file infra/env/docker.env logs --tail 100 account payment tuition db-init
docker compose --env-file infra/env/docker.env stop
docker compose --env-file infra/env/docker.env start
```

`stop` giữ container và dữ liệu. Nếu thay đổi source, chạy lại `up --build -d`.
Đổi mật khẩu trong env không tự đổi mật khẩu `sa` của DB đã tạo trong volume.
Không xóa volume để xử lý lỗi nếu còn dữ liệu cần giữ.

Nếu báo không thấy `dockerDesktopLinuxEngine`, mở Docker Desktop rồi chạy lại
`docker version`. Nếu `db-init` lỗi, xem log SQL Server và `db-init`; kiểm tra mật
khẩu, ODBC và DB permissions. Dockerfile cài Driver 18 theo
[hướng dẫn Debian của Microsoft](https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server).

**Phạm vi hiện tại:** ba API đã tích hợp; worker đối soát chạy trong Payment.
UI dùng public gateway của Account cùng origin, SMTP và outbox biên nhận đã chạy.

## Email demo qua Mailpit

Mailpit có trong Compose. Hộp thư mở tại `http://127.0.0.1:8025`.
SMTP mặc định ở cổng 1025, không yêu cầu tài khoản/TLS trong cấu hình demo.
Xem [Docker Mailpit](https://mailpit.axllent.org/docs/install/docker/) và
[SMTP Mailpit](https://mailpit.axllent.org/docs/configuration/smtp/).

| Nơi chạy Payment | SMTP host | Port | STARTTLS/SSL |
|---|---|---|---|
| Trong Compose | `mailpit` | 1025 | false/false |
| Python trên Windows, Mailpit trong Docker | `127.0.0.1` | 1025 | false/false |

`SMTP_FROM=ibanking@example.test`, username/password để trống.
Mailpit giữ email trong hộp thư demo để xem nội dung, không gửi đến hộp thư thật.

Payment gửi OTP bằng SMTP và worker gửi biên nhận thành công từ outbox. Không
cần tài khoản email thật khi demo với Mailpit. Mở hộp thư và tìm mã giao dịch để
xem OTP/biên nhận; mã không còn được in trong log. Mailpit lưu hộp thư vào volume
`mailpit-data`, giữ thư khi stop/restart container.

## Cấu hình email thật, ví dụ Gmail

Chỉ cần thiết nếu bài trình diễn yêu cầu nhận mail ở hộp thư thật.
Tài khoản cần đáp ứng điều kiện dùng App Password của Google, gồm xác minh hai bước;
một số loại tài khoản/chính sách tổ chức có thể không hỗ trợ lựa chọn này.
Tham khảo [Google — App Passwords](https://support.google.com/mail/answer/185833).

Lấy thông số từ nhà cung cấp, lưu trong `.env` riêng. Ví dụ SMTP Gmail:

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-account@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=your-account@gmail.com
SMTP_STARTTLS=true
SMTP_SSL=false
```

Cổng 587 dùng STARTTLS; nếu chọn 465 thì dùng SSL từ đầu và tắt STARTTLS.
Thông số máy chủ/cổng: [Google Gmail SMTP](https://developers.google.com/workspace/gmail/imap/imap-smtp).
Không dùng mật khẩu đăng nhập chính trong mã nguồn.

Để dùng SMTP thật trong Docker, đặt các biến SMTP trên vào `infra/env/docker.env`
rồi chạy lại `start.ps1`. Compose đọc các biến đó và mặc định về Mailpit khi chưa
đặt. Với Python trên Windows, đặt trong `.env` gốc. Giữ các tệp cấu hình riêng
ngoài Git; không cần sửa `compose.yaml` để thay SMTP.

Nội dung email cần có: OTP + danh sách học kỳ/tổng tiền/UUID/hạn 5 phút;
email xác nhận gồm UUID, hóa đơn đã trả, thời gian, số tiền và trạng thái thành công.
Chỉ ghi sự kiện gửi, không log mã OTP hoặc thông tin xác thực SMTP.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --check frontend/app.js
docker compose --env-file infra/env/docker.env config --quiet
```

Pytest mặc định chỉ thu thập `tests/unit`. Cấu hình test dùng SQL Server host giả,
JWT/key test và SQLite trong bộ nhớ cho Tuition; không ghi SQL Server thật.
Bài kiểm tra khởi động/static kiểm tra việc di chuyển thư mục, không xác nhận
toàn bộ nghiệp vụ thanh toán.

Bài kiểm tra Account đồng thời cần server Account và SQL Server đang chạy:

```powershell
.\.venv\Scripts\python.exe -m tests.integration.account_concurrency
```

**Bài integration có tạo người dùng, tài khoản và bút toán test trong DB cấu hình
ở `.env`; các bản ghi được giữ lại để đối chiếu.** Dùng database thử riêng.
Mặc định gọi Account ở cổng 8001; nếu đổi cổng, đặt `ACCOUNT_SERVICE_URL` tương ứng.
Nó kiểm tra debit trùng, thay payload, refund trùng và hai debit cạnh tranh;
riêng script này chưa kiểm tra Tuition. Bộ nghiệm thu backend mới kiểm tra đủ
ba service, ghi dữ liệu IT_* riêng vào Docker và restart riêng Payment:

```powershell
.\.venv\Scripts\python.exe -m tests.integration.backend_acceptance
```

Đã đạt 29 pytest và 8 kịch bản SQL Server/SMTP. Kiểm thử trình duyệt bằng
`npm ci` rồi `npm run test:e2e` (Windows dùng Edge đã cài; hệ khác dùng Chromium
của Playwright). Node.js chỉ cần cho kiểm thử, không cần để chạy ứng dụng Docker.
Xem [bàn giao ngày 05–06/11](ui-email-delivery.md).

Bộ nghiệm thu cuối thử tải, mất reply HTTP sau commit, ngắt mạng, SIGKILL Payment
và SQL Server trên **project/volume riêng**, không điều khiển demo chính:

```powershell
.\.venv\Scripts\python.exe -m tests.integration.release_acceptance
```

Mặc định build image không cache; dùng `--cached-build` nếu cần. Cần cổng 810x,
14331, 8026/1026 và 910x trống, chỉ chạy một release test mỗi lần. Kết thúc dừng
container test nhưng giữ volume để kiểm toán. Xem [nghiệm thu cuối](final-acceptance.md)
và [kịch bản demo](demo-script.md). Schema API offline ở `docs/api/openapi-*.json`.

Nếu chạy test bên trong môi trường sandbox của công cụ và bị treo ở
`socket._fallback_socketpair`, chạy từ PowerShell bình thường. Đây là hạn chế
tạo socket cục bộ trong sandbox đã gặp khi rà soát, không phải lỗi truy vấn DB.
