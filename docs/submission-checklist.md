# Checklist trước khi nộp

Nguồn hiện có báo cáo/slide ở root. Bộ gửi sau khi đóng gói lại là
`submission/NHOM12_IBANKING.zip`, gồm README_NOP.md, BaoCao.pdf/md,
Slide.pptx, MaNguon/, MANIFEST.json và SHA256SUMS.txt. Chạy ứng dụng từ gốc
mã nguồn hoặc MaNguon khi đã giải nén bộ nộp.

## Yêu cầu kỹ thuật và bằng chứng đã lưu

- [x] Chỉ trả toàn bộ công nợ MSSV, đủ thông tin người trả và điều khoản.
- [x] Không đăng ký công khai; cập nhật email cần xác minh quyền sở hữu.
- [x] OTP gắn giao dịch, không trùng mã còn hiệu lực, 5 phút, dùng một lần.
- [x] Có bằng chứng SQL concurrency, recovery, idempotency và outbox.
- [x] Có Use Case, kiến trúc, ba ERD, sequence và X-Request-ID/log JSON.
- [x] Báo cáo/slide và bộ nghiệm thu trước đã kiểm tra bố cục/nội dung.

Số liệu và phạm vi lấy từ artifacts/acceptance-summary.json. Bản nguồn lọc
ngày 05/11 đã chạy 152 unit PASS và Compose config hợp lệ; đó là kết quả
của revision/lượt chạy trước, không tự áp dụng cho thay đổi mới. Không đổi
JSON nghiệm thu lịch sử khi chưa chạy lại. Master báo cáo là
`docs/final-report-detailed.md`, builder là `scripts/build_detailed_report.py`.

## Kiểm tra sau thay đổi catalog và UI

- [ ] start.ps1 -PrepareDemo -Detached chạy một lệnh, dùng project chính, cổng 8001/14330 và SMTP thật.
- [ ] Catalog có demo01–demo10; mật khẩu/số dư mới đúng; chạy lại giữ dữ liệu cũ.
- [ ] Demo01 nhận mã hồ sơ thật qua SMTP và tự xác minh thành công trên Web.
- [ ] Demo02–demo10 dùng Mailpit, có kết quả xác minh hoặc ghi chú xử lý thủ công.
- [ ] Nhãn email_delivery của từng hồ sơ/giao dịch đúng; OTP/biên nhận đúng hộp thư.
- [ ] Thanh toán thông thường trả đủ công nợ, số dư/PAID/lịch sử/biên nhận khớp.
- [ ] Hai phiên demo02 không chi vượt 10 triệu; demo03/demo04 không trả trùng SV20261005.
- [ ] Hủy bản nháp OTP/đã xác minh không trừ tiền; bản đang xử lý không bị hủy.
- [ ] UI cập nhật số dư/công nợ/lịch sử khi có thay đổi từ phiên khác.
- [ ] Unit/Compose/static kiểm tra lại sau thay đổi, ghi kết quả riêng đúng phạm vi.

## Kiểm tra bộ nộp mới

- [ ] Giữ nguyên yêu cầu/thông tin thành viên; điền hai tên/MSSV và phân công thực tế còn thiếu.
- [ ] Đồng bộ PDF/Markdown/slide sau biên tập; mở Slide.pptx trên máy trình chiếu.
- [ ] Đường ảnh BaoCao.md trong bộ nộp hợp lệ, kể cả ảnh đã có tiền tố MaNguon.
- [ ] Đủ runtime/__init__/migration/catalog/env mẫu/tests/tài liệu hiện hành.
- [ ] Không còn launcher/helper/test demo cô lập đã nghỉ hưu hoặc lệnh thanh toán từ terminal.
- [ ] ZIP loại private env, dependency/cache, log/artifact tạm, SQL volume và bản lịch sử.
- [ ] Manifest/checksum/ZIP readback đúng bản mới; đối chiếu sau sao chép USB.
- [ ] Chạy thử lệnh chuẩn bị trên môi trường phù hợp; kiểm tra dữ liệu trước demo.

Xem [chuẩn bị nộp](pre-submit.md), [catalog và demo Web](demo-script.md),
[chính sách lọc](submission-filter.md). Không chạy reset hoặc fault test
trong lúc trình diễn. Email thật cần kiểm tra tại máy demo, không suy ra
từ Mailpit hoặc một thông báo SMTP đã nhận thư.
