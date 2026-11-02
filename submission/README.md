# Hồ sơ bàn giao — Nhóm 12

- `bao-cao-ibanking.pdf`: báo cáo 14 trang.
- `bao-cao-ibanking.md`: bản báo cáo có thể biên tập; hình tham chiếu về docs/artifacts.
- `trinh-bay-ibanking-v2.pptx`: 14 slide có thể sửa, gồm sơ đồ native và bảng API.
- `ibanking-source.zip`: mã nguồn, cấu hình mẫu, tài liệu, sơ đồ, báo cáo/slide và
  JSON/ảnh nghiệm thu đã chọn; giải nén thư mục Ibanking-System rồi chạy `start.ps1`.
- `SOURCE-MANIFEST.json`: danh sách file trong ZIP và SHA-256 từng file.
- `SHA256SUMS.txt`: hash của ZIP và các sản phẩm chính.
- `evidence/`: bản sao các JSON và ảnh nghiệm thu để mở nhanh.

Cần Docker Desktop Linux containers; máy mới cần mạng để tải image lần đầu.
Ứng dụng chạy bằng một lệnh PowerShell trong thư mục gốc:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

UI: http://127.0.0.1:8001/ui/ — Mailpit: http://127.0.0.1:8025.
Tài khoản demo `huy` / `HuyDemo_123!`, MSSV `SV2026001`.

Hai thành viên còn lại và phân công thực tế cần nhóm điền trước khi nộp.
Thông tin nguồn ở `docs/team.json`; PDF/slide đã xuất cũng cần cập nhật khi đổi
thông tin bìa. Xem `docs/submission-checklist.md` và `docs/demo-script.md`.

ZIP không có .env riêng, SQL volume, Docker image, .venv hoặc node_modules.
Khi chạy từ source mới, start.ps1 tạo cấu hình riêng; không chép cấu hình bí mật
của máy đang dùng vào bài nộp. Không dùng `down -v` nếu cần giữ lịch sử/số dư.
