# Chuẩn bị nộp và bảo vệ

## Bản nguồn và bộ nộp

Thư mục làm việc hiện chứa `README.md`, `BaoCao.pdf`, `BaoCao.md`, `Slide.pptx`
cùng mã nguồn. Chỉ gửi bộ đã lọc `submission/NHOM12_IBANKING.zip` khi đã tạo
lại và kiểm chứng. Bên trong ZIP:

```text
NHOM12_IBANKING/
  README_NOP.md
  BaoCao.pdf
  BaoCao.md
  Slide.pptx
  MaNguon/
  MANIFEST.json
  SHA256SUMS.txt
```

Đọc README_NOP.md trước; chạy lệnh từ MaNguon. JSON/ảnh chọn lọc nằm ở
MaNguon/artifacts/, kết quả tổng hợp là acceptance-summary.json. Đây là
bằng chứng đã lưu, không phải database được khôi phục tự động trên máy mới.
Nguồn báo cáo ở `docs/final-report-detailed.md`, builder là
`scripts/build_detailed_report.py`. Hai tên/MSSV và phân công còn “Điền sau”
phải được nhóm bổ sung trong docs/team.json/team-completion.md, rồi xuất lại
báo cáo/slide và đóng gói. Không tự gán công việc chưa được xác nhận.

## Khởi động và chuẩn bị bằng một lệnh

Cài Docker Desktop Linux containers, mở PowerShell tại gốc mã nguồn:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -PrepareDemo -Detached
```

Ứng dụng chính dùng Web 8001, SQL 14330 và SMTP thật đã cấu hình. Ba service vẫn tách
biệt Account/Payment/Tuition. Catalog mới có demo01–demo10, mật khẩu
`Demo_123!`, số dư mỗi tài khoản 10 triệu. Chuẩn bị lại chỉ thêm mục thiếu;
không đặt lại mật khẩu/số dư, hồ sơ, hóa đơn PAID hay lịch sử.

- Cấu hình SMTP thật trong `infra/env/docker.env`; username/mật khẩu SMTP
  là thông tin người gửi, còn địa chỉ nhận lấy từ hồ sơ của từng người dùng.
- Ở mỗi tài khoản, cập nhật email thật và xác minh mã trên Web. Mọi lần lưu
  hồ sơ đều phải nhập mã gửi đến địa chỉ vừa nhập; hồ sơ mới chỉ lưu sau khi
  xác minh thành công. Chuẩn bị catalog không tự xác minh hộp thư.
- Tạo tài khoản thứ hai bằng `demo-data.ps1 -CreateTestAccount -Email
  'your-second-real-email'`: `huy2` / `HuyDemo_123!`, số dư ban đầu 10 triệu.
  Email chưa xác minh; người dùng phải nhận và nhập mã trên Web.
- Kiểm tra `artifacts/demo-accounts.json` và mở `artifacts/demo-inspect.sql`
  trong SSMS. Các số dư/công nợ thực tế mới là căn cứ trước buổi demo.
- Sau chuẩn bị chỉ cần `start.ps1 -Detached` để chạy tiếp. Lần build đầu cần
  mạng; tải image/dependency trước buổi trình diễn.
- Bộ seed huy/SV20261013 chỉ tạo khi chủ động `-SeedDemo`; tài khoản huy mới
  có email trống và cần cập nhật/xác minh email thật trước khi thanh toán.

## Trình diễn 5–10 phút

1. Mở kiến trúc, giới thiệu ba service/DB và REST, gateway, SMTP/outbox.
2. Đăng nhập `huy` đã xác minh email thật. Xem hồ sơ/số dư và địa chỉ nhận mã.
   OTP và biên nhận của giao dịch mới dùng email đã xác minh của người trả.
3. Tra SV20261006 hoặc SV20261007; đọc thông tin người trả chỉ đọc, sinh viên,
   toàn bộ công nợ và điều khoản. Trên bộ mới đều là 1 triệu.
4. Xác nhận, lấy OTP đúng người nhận/UUID, nhập và thanh toán trên Web.
5. Đối chiếu SUCCEEDED, số dư giảm đúng tổng, hóa đơn PAID, lịch sử/biên nhận.
6. Hai phiên độc lập cho `huy` và `huy2`: cùng tra một MSSV còn UNPAID,
   nhận OTP riêng qua email thật của từng người rồi thanh toán gần nhau.
   Chỉ một người bị trừ tiền và nhóm hóa đơn chỉ PAID một lần.
7. Chạy SELECT, đối chiếu tiền, DEBIT, snapshot, nhóm hóa đơn và lịch sử.
8. Nêu rõ bấm tay không bảo đảm request tới cùng thời điểm; mở bằng chứng
   concurrency tự động đã lưu khi cần chứng minh phần kiểm thử có kiểm soát.

Theo [kịch bản](demo-script.md), [hai phiên Web](consistency-demo.md) và
[truy vết](observability.md). UI tự cập nhật khoảng 5 giây và khi quay lại
cửa sổ; có thể bấm Làm mới. Bỏ bản nháp OTP thì dùng Hủy giao dịch; giao dịch
đã xử lý phải chờ đối soát. Không reset, kill/disconnect hoặc chạy fault/load
trong giờ trình diễn chính.

## Kiểm chứng và sao chép

Báo cáo/slide hiện có và JSON nghiệm thu giữ nguyên phạm vi của lần xuất/lần
chạy ghi trong chúng. Sau thay đổi catalog/UI, kiểm tra riêng trước khi nộp;
không sửa số kiểm thử lịch sử để làm như đã chạy lại full acceptance.

Packager đọc báo cáo/slide ở root; nếu chưa có mới tìm đầu vào submission cũ.
Nếu vừa biên tập báo cáo, đồng bộ bản root với bản mới đã xuất trước khi đóng
gói. Xem [chính sách lọc](submission-filter.md). Manifest/checksum phải được
đóng gói lại cùng nội dung đã thay đổi, không giữ checksum cũ.

Không đưa .env riêng, mật khẩu SMTP, dependency/cache, SQL volume hoặc log
thô vào bài nộp. Giải nén thử trên máy phù hợp, chạy lệnh chuẩn bị, mở báo
cáo và slide, kiểm tra font/ảnh/liên kết. Sao chép ZIP sang USB và đối chiếu
hash sau sao chép. Kiểm tra tên tệp/định dạng theo yêu cầu giảng viên.
