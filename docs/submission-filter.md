# Chính sách lọc bộ nộp dự án

Bộ nộp được tạo riêng từ allowlist. Mã nguồn đang làm việc, private env,
artifact và database hiện có được giữ nguyên; không xóa volume hoặc cache
chỉ để giảm dung lượng bài gửi.

## Cấu trúc đầu ra

```text
NHOM12_IBANKING/
  README_NOP.md
  BaoCao.pdf
  BaoCao.md
  Slide.pptx
  MaNguon/
    README.md
    services/  shared/  frontend/  infra/
    tests/  scripts/  docs/  artifacts/
    compose.yaml  start.ps1  demo-data.ps1
    requirements*.txt  package*.json  playwright.config.cjs  pytest.ini
    .env.example  .dockerignore  .gitignore  .gitattributes
  MANIFEST.json
  SHA256SUMS.txt
```

Thư mục làm việc hiện có báo cáo/slide ngay root. Packager ưu tiên
`BaoCao.pdf`, `BaoCao.md`, `Slide.pptx`; nếu thiếu từng tệp mới tìm bản tương
ứng tại `submission/bao-cao-ibanking-chi-tiet.pdf`, `.md` và
`submission/trinh-bay-ibanking-v3.pptx`. Sau khi xuất báo cáo mới vào
submission, đồng bộ bản root trước khi đóng gói để tránh chọn bản cũ.

MaNguon giữ nguyên đường dẫn runtime. README của mã nguồn được lấy từ
README.md hiện hành, không dùng một template startup cũ riêng. Giữ mọi
`__init__.py`, migration, seed/catalog, module xác thực, Dockerfile và
`infra/env/docker.env.example`. Catalog chạy trên Compose chính; bộ cũ ở
cổng demo riêng và các launcher/helper/test tương ứng đã nghỉ hưu.

## Giữ và loại

| Giữ | Không đưa vào bộ nộp |
|---|---|
| Ba service, shared, Web, Docker/Compose/init/migration | .git, .venv, node_modules, cache Python/test |
| start.ps1, demo-data.ps1, catalog và quản trị dữ liệu | Private .env/docker.env, mật khẩu SMTP, khóa riêng |
| Unit, SQL/concurrency/integration, Playwright | Log thô, trace, kết quả tạm, render/build preview |
| Kiến trúc, API/OpenAPI, sơ đồ, runbook, demo hiện hành | Bàn giao từng ngày, báo cáo/slide cũ, ZIP nguồn lồng |
| Báo cáo master và builder JSON, requirements-report.txt | Builder cũ cần runtime riêng hoặc log thô |
| Bảy JSON và bốn ảnh nghiệm thu đã chọn | SQL backup/data, Docker image/volume, catalog chứa dữ liệu cá nhân cục bộ |

JSON được chọn: backend-acceptance, browser-acceptance,
release-acceptance-latest, otp-consistency-acceptance,
email-verification-acceptance, observability-acceptance và acceptance-summary.
Ảnh được chọn: payment-history-desktop, payment-success-mobile,
tuition-full-debt-desktop và email-proof-confirmed. Đây là bằng chứng lịch
sử đã lưu theo phạm vi/ngày chạy, không tự chứng nhận catalog/UI mới hoặc
khôi phục dữ liệu SQL trên máy nhận. Không sửa các JSON đó khi chưa nghiệm
thu lại.

Runtime/code mới trong services/shared/frontend/infra/tests được lấy tự
động theo phần mở rộng allowlist. Tài liệu hiện hành được chọn tường minh;
link lịch sử được chuyển tới tài liệu hiện hành hoặc thành chữ. Ảnh báo cáo
bắt buộc phải còn trong bộ nộp, không được âm thầm bỏ. BaoCao.md ở gốc có
thể dùng đường ảnh nguồn hoặc đường đã có tiền tố MaNguon; packager điều
chỉnh mà không thêm tiền tố lặp.

## Tạo và kiểm chứng

Chuẩn bị đủ báo cáo/slide, docs/final-report-detailed.md,
scripts/build_detailed_report.py và artifacts/acceptance-summary.json PASS,
rồi chạy từ thư mục phát triển:

```powershell
python -m scripts.package_clean_submission
```

Đầu ra là `submission/NHOM12_IBANKING/` và
`submission/NHOM12_IBANKING.zip`. Packager chỉ dùng thư viện chuẩn Python;
không gọi Docker, database, SMTP hoặc fault test. Nếu đích đã tồn tại, lệnh
dừng và giữ nguyên; đổi tên/lưu trữ bộ cũ chủ động trước khi dựng lại. Không
có recursive delete; staging thất bại được giữ để kiểm tra.

Các kiểm tra trước khi công bố:

1. Chỉ lấy file allowlist; từ chối symlink/junction và đường dẫn vượt phạm vi.
2. Kiểm tra literal secret từ env riêng trong payload/XML PPTX, không in giá trị bí mật.
3. Kiểm tra link/ảnh Markdown và đường ảnh báo cáo ở gốc.
4. Ghi SHA-256/size vào manifest; đọc lại từng file staging để đối chiếu.
5. Kiểm tra CRC, đúng tập entry và hash từng file ZIP trước khi rename đầu ra.

MANIFEST.json liệt kê payload/hash cùng metadata nghiệm thu. SHA256SUMS.txt
xác minh payload và manifest, trừ chính tệp checksum; SHA của ZIP được in
khi tạo. Số kiểm thử/số trang lấy từ JSON, không hard-code để làm như đã
nghiệm thu lại. Kiểm tra hash sau khi chép sang USB.

## Biên tập báo cáo và chạy trên máy nhận

Trong nguồn sạch, sửa docs/final-report-detailed.md hoặc docs/team.json:

```powershell
python -m pip install -r requirements-report.txt
python scripts/build_detailed_report.py
```

Builder tạo PDF/Markdown ở submission/ và cập nhật metadata báo cáo trong
artifacts/acceptance-summary.json; không ghi database. Font mặc định là
Times New Roman trên Windows hoặc DejaVu Serif trên Linux; có thể đặt
IBANKING_REPORT_FONT_DIR tới thư mục có bốn font Times New Roman. Đồng bộ
bản root mới, kiểm tra PDF/slide rồi tạo lại bộ nộp/hash; không sửa nội dung
đã đóng gói nhưng giữ checksum cũ.

Máy nhận giải nén toàn bộ, đọc README_NOP.md, vào MaNguon rồi chạy một lệnh:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -PrepareDemo -Detached
```

Lệnh chạy ứng dụng chính và tạo catalog thiếu. Mỗi tài khoản cần nhập và tự
xác minh email thật trên Web; SMTP gửi mã đến đúng địa chỉ người dùng. Không thanh toán từ
terminal. Máy mới cần mạng để tải image/dependency lần đầu; không cần mang
.venv, node_modules hay database của máy phát triển.
