# Cài đặt, chạy và kiểm thử

Các lệnh dưới đây chạy trong PowerShell tại thư mục gốc. Ứng dụng gồm ba
microservice Account, Payment và Tuition, dùng ba database SQL Server. Máy
chạy Docker không cần cài Python/Node.js để mở Web.

## Một lệnh cho ứng dụng và catalog demo

Cài Docker Desktop, chọn Linux containers và điền SMTP thật trong
`infra/env/docker.env` theo phần email bên dưới, rồi chạy:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -PrepareDemo -Detached
```

`start.ps1` chờ service sẵn sàng, kiểm tra SQL đúng cổng
14330 rồi tạo catalog còn thiếu qua `infra/docker/demo_catalog.py`. Tài khoản
mới `demo01`–`demo10` có mật khẩu `Demo_123!`, số dư 10 triệu. Không đặt lại
mật khẩu/số dư/hồ sơ cũ, không đổi hóa đơn PAID hoặc xóa lịch sử. Chuẩn bị
không tự xác minh email và không gọi API thanh toán.

Khai báo dữ liệu nằm tại `services/account/seed.py` và
`services/tuition/seed.py`; catalog chỉ điều phối. Hai MSSV bổ sung để đóng
học phí là `SV20261001` (2,5 triệu) và `SV20261002` (3,5 triệu). Chỉ hóa đơn
chưa tồn tại mới được thêm; hóa đơn đã trả không bị tạo lại.

Kết quả ở `artifacts/demo-accounts.json` và `artifacts/demo-inspect.sql`. Kiểm
tra ghi chú từng tài khoản; cập nhật địa chỉ email thật và xác minh trên Web
bằng mật khẩu hiện tại trước khi thanh toán.
Số dư/công nợ dự kiến của catalog mới không thay cho trạng thái thực trong DB.

| Thành phần | Địa chỉ chính |
|---|---|
| Web | http://127.0.0.1:8001/ui/ |
| Account / Payment / Tuition API | Cổng 8001 / 8002 / 8003, `/docs` và `/health/db` |
| SQL Server cho SSMS | `127.0.0.1,14330` |

Sau chuẩn bị, toàn bộ thanh toán và hai ca cạnh tranh thực hiện trên Web.
Xem [catalog và kịch bản](demo-script.md), [hai phiên và SQL](consistency-demo.md).

## Startup, dừng và dữ liệu

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Detached
```

Startup tự khởi động Docker Desktop khi cần, tạo `infra/env/docker.env` riêng
nếu thiếu, kiểm tra cấu hình, so sánh SHA-256 các file Dockerfile sao chép rồi
build khi source khác image. Nếu image khớp và image hạ tầng đã có, dùng lại
không gọi registry. Build thất bại giữ dịch vụ đang chạy; startup thất bại giữ
container để xem log. Lần tải image/dependency đầu cần Internet.

Luồng là SQL healthy → `db-init` tạo/migrate ba DB → ba API. `db-init` Exited
(0) là bình thường. Worker recovery/outbox chạy trong Payment, không mở terminal
riêng. SQL có named volume, giữ dữ liệu qua stop/restart.

- `start.ps1` không có `-Detached`: log chung một terminal; Ctrl+C dừng container.
- `start.ps1 -Check`: kiểm tra Docker/Compose, chưa khởi chạy ứng dụng.
- `start.ps1 -PrepareDemo -Detached`: khởi động và bổ sung catalog demo còn thiếu.
- `start.ps1 -Rebuild -Detached`: chủ động build lại.
- `docker compose --env-file infra/env/docker.env stop`: dừng khi chạy nền.
- `start.ps1 -SeedDemo -Detached`: cấp bộ seed cũ `huy` / `HuyDemo_123!`,
  `SV20261013` có HK1 2 triệu + HK2 3 triệu nếu chưa tồn tại. Bộ này độc lập
  catalog demo01–demo10; không chạy seed tự động ở mọi lần startup.

Lệnh `demo-data.ps1 -Reset` xóa dữ liệu ba DB. Chỉ dùng khi chủ động muốn làm
lại từ đầu theo [hướng dẫn reset](demo-data-reset.md). Không dùng `down -v`
để sửa lỗi khởi động hoặc làm mới một ca đã trả. Đổi mật khẩu trong env không
tự đổi login `sa` đã có trong SQL volume.

## Email thật cho từng người dùng

Compose chính chỉ có SQL Server và ba API; không chạy hộp thư giả lập.
API công khai trả nhãn **chỉ đọc** `email_delivery`; người dùng cập nhật
email trong hồ sơ và xác minh bằng mã gửi đến chính địa chỉ mới. Khi đã xác
minh, giao dịch mới lấy email đó để gửi OTP và biên nhận. Tài khoản SMTP là
người gửi thư, không phải địa chỉ nhận cố định của mọi người.

Để thử hai người trả một học phí, đăng nhập `huy` và `huy2` ở hai phiên độc
lập, cập nhật/xác minh email thật của từng tài khoản rồi cùng tra một MSSV
còn UNPAID. Tài khoản mới chưa xác minh email sẽ chưa được thanh toán.

Để nhận thư thật, lấy thông số từ nhà cung cấp và điền trong
`infra/env/docker.env` riêng. Ví dụ cấu hình cần điền, không phải mật khẩu dùng sẵn:

```dotenv
SMTP_HOST=smtp.your-provider.example
SMTP_PORT=587
SMTP_USERNAME=your-email@example.com
SMTP_PASSWORD=YOUR_PROVIDER_APP_PASSWORD
SMTP_FROM=your-email@example.com
SMTP_STARTTLS=true
SMTP_SSL=false
```

Dùng phương thức xác thực do nhà cung cấp hỗ trợ; không đưa mật khẩu đăng
nhập email vào mã nguồn. Nếu dùng cổng 465 với SSL từ đầu, tắt STARTTLS.
Không bật đồng thời SSL và STARTTLS. Chạy lại `start.ps1 -Detached` sau khi
sửa env để container nhận cấu hình. Hồ sơ đã có luôn được giữ; từng người
cần cập nhật/xác minh địa chỉ nhận thư của mình trên Web. Nếu còn bản nháp
PENDING_OTP/OTP_VERIFIED được tạo trước khi đổi email, hủy bản nháp và tạo
giao dịch mới để sử dụng email vừa xác minh.

SMTP chấp nhận thư không chứng minh quyền sở hữu hộp thư. Người dùng phải
nhận mã hồ sơ thật và xác nhận thành công trước khi dùng địa chỉ cho thanh
toán. Mã hồ sơ khác OTP từng giao dịch, đều có hạn và chỉ dùng một lần.
Xem [xác minh email](email-verification.md).

Giữ `.env` và `infra/env/docker.env` ngoài Git/bộ nộp. Không in `docker compose
config` đầy đủ để chia sẻ; dùng `config --quiet`. Không chụp ảnh các giá trị
bí mật; nếu khóa đã lộ thì thay tại nhà cung cấp và cập nhật cấu hình riêng.

## Đối chiếu database bằng SSMS

Server type Database Engine; server `127.0.0.1,14330`; SQL Server Authentication;
login `sa`; mật khẩu MSSQL_SA_PASSWORD trong env riêng; bật Trust server
certificate trên máy demo. Chọn account_db, payment_db hoặc tuition_db.

`artifacts/demo-inspect.sql` do bước chuẩn bị tạo chỉ có SELECT cho catalog:
người dùng/số dư/kênh email, payments, account_entries và hóa đơn. Chạy trước
và sau thao tác Web. Đợi kết quả cuối SUCCEEDED/FAILED/REFUNDED khi đối soát;
PROCESSING/PENDING_RECONCILIATION chưa phải kết luận cuối.

Nếu SSMS connection refused, kiểm tra Docker/SQL healthy và cổng 14330. Lỗi
`lookup registry-1.docker.io` là kết nối DNS/mạng khi build, không phải lỗi SQL
schema. Khôi phục kết nối rồi chạy lại startup; không reset DB hoặc tự đổi
mật khẩu volume để sửa lỗi mạng.

## Kiểm thử và debug

Để chạy unit trên máy phát triển:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Pytest mặc định chỉ thu thập tests/unit, dùng cấu hình test/SQLite và stub
hạ tầng. Không ghi vào SQL chính. Node.js chỉ cần cho Playwright: `npm ci`,
rồi `npm run test:e2e` trên môi trường phù hợp. Bộ E2E mặc định không gửi email
hư cấu ra SMTP Internet. Khi cần kiểm tra tự động đầy đủ:

```powershell
.\.venv\Scripts\python.exe -m tests.integration.release_acceptance --cached-build --full-checks
```

Đây là **project/volume kiểm thử riêng**, dùng cổng 810x, SQL 14331,
Mailpit 8026/1026 và proxy 910x. Bài thử có tạo dữ liệu, kill/disconnect và thử
tải; không chạy trong lúc demo chính, không chạy hai release test cùng lúc.
Xem [nghiệm thu](final-acceptance.md). Bộ backend/account_concurrency riêng
cũng ghi dữ liệu test; chỉ chạy khi đã chọn đúng môi trường theo mã test.

Để debug Python ngoài Docker, cài ODBC Driver 18, sao chép `.env.example` khi
chưa có `.env`, cấu hình DB và hai khóa khác nhau, chạy migration từng service.
Cấu hình SMTP thật giống các biến trong Compose để kiểm tra thủ công.
Ba entrypoint là services.account.main:app, services.payment.main:app và
services.tuition.main:app. Cách chạy demo chung vẫn là startup ở đầu tài liệu.

Schema OpenAPI offline ở docs/api/. Các bằng chứng JSON đã lưu thuộc lượt
chạy và revision ghi trong chúng; không tự coi thay đổi catalog/UI mới là
một lượt full acceptance mới. Không sửa số liệu nghiệm thu lịch sử.
