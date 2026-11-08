# Demo tính nhất quán trên ứng dụng chính

Dùng chính Web tại http://127.0.0.1:8001/ui/, SQL Server
`127.0.0.1,14330` và hộp thư email thật của từng người dùng. Ba service là
Account, Payment và Tuition. Catalog phục vụ trình diễn nằm cùng database
chính; không cần môi trường demo riêng hoặc terminal để thực hiện thanh toán.

## Chuẩn bị

Chạy một lần trước giờ trình bày:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -PrepareDemo -Detached
```

Lệnh tự chạy `start.ps1 -Detached`, tạo các mục còn thiếu của catalog,
không gọi API thanh toán, đổi tiền hoặc reset dữ liệu đã có. Tài khoản mới
`demo01`–`demo10` có mật khẩu `Demo_123!`, số dư 10 triệu. Mỗi người dùng
phải cập nhật và xác minh email thật trên Web trước khi nhận OTP thanh toán.
Ca hai người cùng học phí dùng hai tài khoản `huy` và `huy2`.

Kiểm tra `artifacts/demo-accounts.json`: số dư/công nợ thực tế và kết quả xác
minh. Nếu đã dùng catalog, các con số ban đầu có thể không còn. Không chạy
reset để làm mới trong lúc demo. Giữ kết quả đã trả và chọn khoản chưa đóng
phù hợp; chỉ xóa dữ liệu khi chủ động muốn làm lại theo hướng dẫn reset.

Hai MSSV bổ sung để thanh toán thông thường: `SV20261001` (Nguyễn Minh An,
2,5 triệu) và `SV20261002` (Trần Ngọc Linh, 3,5 triệu). Khai báo tài khoản nằm
trong `services/account/seed.py`, khai báo MSSV/học phí nằm trong
`services/tuition/seed.py`; script chuẩn bị chỉ điều phối và bổ sung mục thiếu.

Mở hai phiên đăng nhập độc lập: Chrome thường + ẩn danh, hoặc Chrome + Edge.
Hai tab trong cùng phiên trình duyệt dùng chung trạng thái đăng nhập, không
phù hợp để đóng vai hai người khác nhau. Mở hộp thư thật của mỗi người để lấy
OTP đúng UUID giao dịch/người nhận; mỗi request có mã riêng, không dùng chung mã.

Trong SSMS, dùng SQL Server Authentication, login `sa`, mật khẩu riêng trong
`infra/env/docker.env`, bật Trust server certificate cho máy demo. Mở
`artifacts/demo-inspect.sql` và chạy SELECT trước/sau mỗi ca. Tệp lọc theo
catalog, không sửa dữ liệu. Không chia sẻ ảnh màn hình chứa mật khẩu/khóa.

Với hai tài khoản `huy` và `huy2`, mở thêm
[`docs/sql/test-shared-tuition.sql`](sql/test-shared-tuition.sql). Tệp này xem
email/số dư của đúng hai người trả, hóa đơn, kết quả giao dịch và bút toán cho
`SV20261001`. Nếu chọn MSSV khác, đổi biến `@mssv` trước khi chạy.

## Ca 1 — cùng tài khoản, hai khoản học phí

1. Cả hai phiên đăng nhập `demo02`.
2. Phiên A tra `SV20261003`, phiên B tra `SV20261004`. Mỗi MSSV có khoản
   chưa đóng 7 triệu; tài khoản mới có 10 triệu. Tổng hai khoản là 14 triệu.
3. Ở mỗi phiên, đọc và đồng ý điều khoản, xác nhận để nhận OTP. Lấy đúng hai
   email gửi đến địa chỉ đã xác minh của tài khoản, nhập mã tương ứng. Chuẩn bị xong
   cả hai màn trước khi bấm nút thanh toán gần nhau trên hai phiên.
4. Nếu Web đã cập nhật số dư và khóa nút thanh toán ở phiên còn lại vì
   không đủ tiền, đây là chặn hợp lệ trước khi gửi request xử lý. Bản nháp
   có thể còn PENDING_OTP/OTP_VERIFIED; dùng **Hủy giao dịch** để kết thúc
   bản nháp đó thành FAILED với lý do hủy. Đối chiếu SQL: payment bị chặn
   hoặc hủy không có DEBIT. Nếu cả hai request đã được gửi, chờ kết quả
   xử lý cuối rồi mở lịch sử và đối chiếu SQL.

| Quan sát với bộ mới | Kết quả mong đợi |
|---|---|
| Số dư | 3 triệu đồng |
| Giao dịch | Một SUCCEEDED; bên còn lại FAILED nếu đã bị server từ chối xử lý, hoặc còn bản nháp khi UI chặn trước request; hủy bản nháp để kết thúc FAILED |
| Bút toán | Đúng một DEBIT 7 triệu; không trùng payment/type |
| Hóa đơn | MSSV thắng PAID, MSSV còn lại UNPAID |

Account khóa dòng tài khoản và kiểm tra lại số dư trong transaction khi
trừ tiền. Sau lần trừ 7 triệu, lần còn lại chỉ thấy 3 triệu và bị từ chối.
Bên thắng không cố định. Màn hình ban đầu đủ số dư cho từng khoản riêng
không đảm bảo cả hai khoản đều được thanh toán.

## Ca 2 — hai tài khoản, cùng MSSV

1. Phiên A đăng nhập `huy`, phiên B đăng nhập `huy2`; xác minh email thật
   trong hồ sơ của từng tài khoản trước khi bắt đầu.
2. Cả hai tra cùng MSSV chưa đóng, ví dụ `SV20261001` có học phí 2,5 triệu
   trên bộ mới. Kiểm tra cả hai tài khoản đủ số dư hiện tại; người trả lấy từ
   phiên đăng nhập và chỉ đọc.
3. Xác nhận trên cả hai phiên trước khi thanh toán để cấp hai OTP riêng.
   Mở hộp thư email thật đã xác minh của từng người; phân biệt mã theo người
   nhận, UUID giao dịch và thời hạn.
4. Sau khi nhập mã đúng ở từng phiên, bấm thanh toán gần nhau rồi chờ kết
   quả cuối. Đối chiếu Web và cùng tệp SQL.
5. Nếu Web đã cập nhật công nợ và khóa nút thanh toán ở phiên còn lại vì
   hóa đơn vừa được trả, đây là chặn hợp lệ trước xử lý. Bản nháp vẫn có
   thể là PENDING_OTP/OTP_VERIFIED; dùng **Hủy giao dịch** để kết thúc
   FAILED với lý do hủy. Đối chiếu SQL: payment bị chặn hoặc hủy có 0
   DEBIT; tiền của người này giữ nguyên. Không cần cố gửi thêm request
   hoặc sửa dữ liệu để buộc phiên còn lại chuyển trạng thái.

| Quan sát với bộ mới | Kết quả mong đợi |
|---|---|
| Giao dịch | Chỉ một SUCCEEDED; bên còn lại FAILED khi server từ chối xử lý, hoặc là bản nháp bị UI chặn và được người dùng hủy thành FAILED |
| Số dư | Người thắng giảm đúng tổng học phí, người còn lại giữ nguyên |
| Bút toán | Một DEBIT đúng tổng học phí cho người thắng |
| Hóa đơn của MSSV | Chỉ PAID một lần, cùng paid_payment_id của giao dịch thắng |

Tuition kiểm tra và giữ toàn bộ nhóm hóa đơn dưới khóa; chỉ một payment
được thanh toán nhóm đó. Kiểm tra lại công nợ ở server bảo vệ cả khi phiên
khác vẫn đang hiển thị dữ liệu trước thời điểm thanh toán.

## Hai người nhập cùng một mã OTP

Mỗi giao dịch có UUID, challenge và OTP riêng. Mã đang còn hiệu lực không
được cấp trùng cho giao dịch khác. OTP được băm kèm UUID, challenge, tổng tiền
và danh sách hóa đơn; JWT kiểm tra người sở hữu giao dịch. Nếu A và B cùng
nhập mã của A thì chỉ giao dịch A có thể xác minh, giao dịch B báo OTP không
hợp lệ và chưa được trừ tiền. Mã/challenge của A không thể dùng cho payment B;
tài khoản B cũng không được truy cập payment của A.

Để minh họa trên Web, tạo hai giao dịch cho cùng MSSV chưa đóng ở hai phiên
độc lập. Lấy hai OTP từ hai email rồi thử nhập mã A ở phiên B: hệ thống phải
từ chối. Sau đó nhập lại đúng mã B. Khi cả hai dùng mã riêng hợp lệ và bấm
thanh toán gần nhau, khóa tại Tuition giữ toàn bộ công nợ cho đúng một
payment **trước khi gọi Account trừ tiền**. Người thua không có DEBIT. Chặn
OTP và chặn trả trùng là hai lớp riêng; OTP hợp lệ không đảm bảo học phí còn
đủ điều kiện thanh toán tại thời điểm xử lý.

## Cách đọc kết quả và giới hạn của thao tác tay

Giao diện tự cập nhật số dư/công nợ/lịch sử khoảng 5 giây khi đang hiển thị,
và khi trở lại cửa sổ. Có thể bấm **Làm mới dữ liệu** sau khi hoàn tất. Nếu
một giao dịch đang PROCESSING hoặc PENDING_RECONCILIATION, giữ UUID đó và
chờ đối soát; không kết luận chỉ từ một HTTP 200 hay số dư tạm thời.

Bấm tay trên hai cửa sổ không bảo đảm request tới đúng cùng một thời điểm.
Ca Web minh họa xử lý yêu cầu thật và trạng thái cuối. Bằng chứng kiểm thử
đồng thời có kiểm soát nằm ở các bài SQL/integration đã lưu, không được ghi
thao tác tay là kết quả Barrier/load test. Trong buổi trình bày không chèn
sleep, delay hoặc dùng terminal để phát lệnh thanh toán.

Nếu bỏ dở màn OTP, dùng **Hủy giao dịch** khi còn PENDING_OTP/OTP_VERIFIED.
Server ghi FAILED với lý do hủy và thu hồi mã; không trừ tiền, không đánh
dấu học phí PAID. Giao dịch đã bắt đầu xử lý không hủy theo cách này; tiếp
tục theo dõi kết quả hiện tại. Hủy yêu cầu xác minh email là thao tác riêng
trong hồ sơ, không thay cho hủy giao dịch.

Catalog chạy lại giữ nguyên tiền/hồ sơ/hóa đơn và lịch sử. Các volume và
artifact của môi trường demo cũ được giữ để đối chiếu; hướng dẫn hiện tại
chỉ dùng một ứng dụng chính. Bộ kiểm thử gây lỗi hạ tầng vẫn chạy riêng
theo [runbook](runbook.md), không chạy trong giờ demo.

## Bằng chứng kiểm tra ngày 07/11/2026

- 217 unit test đạt; seed giữ nguyên hồ sơ, mật khẩu, số dư và hóa đơn đã trả.
- 9 kiểm tra OTP/SQL đạt, gồm hai tài khoản gửi cùng mã OTP cho một MSSV,
  dùng nhầm challenge/người sở hữu, và hai OTP đúng cùng thanh toán một công nợ.
- 29 kiểm tra Web đạt, gồm hai phiên cạnh tranh số dư, hai người trả cùng
  nhóm học phí, cập nhật số dư giữa phiên và hủy bản nháp không trừ tiền.

Kiểm chứng tự động dùng SQL Server/Mailpit tạm thời để không tiêu tiền hoặc
đổi công nợ demo chính. Hệ thống chính vẫn dùng cùng mã nghiệp vụ và các khóa
SQL này. Sau kiểm tra, container kiểm thử được dừng và gỡ, không xóa volume.
Xem [kết quả kiểm tra lần này](../artifacts/shared-tuition-acceptance-latest.json)
và [chi tiết OTP/SQL](../artifacts/otp-consistency-acceptance.json). Bằng chứng
nghiệm thu cũ giữ nguyên ngày chạy và phạm vi của nó.
