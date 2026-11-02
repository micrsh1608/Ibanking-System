# Kiến trúc và phân tích nghiệp vụ — mốc hoàn thành 08/11

Cập nhật ngày 02/11/2026: đã hoàn thành sớm phần việc 02–08/11, gồm backend,
SMTP/outbox, UI, tải và lỗi hạ tầng. Sơ đồ mô tả mã đã chạy và kiểm thử;
bản hình xuất ở `docs/diagrams/exported`, nguồn có thể sửa nằm trong PPTX bàn giao.

## Microservices

```mermaid
flowchart LR
    Web[Web: tài khoản / học phí / lịch sử] --> Account[Account và public gateway :8001]
    Account -->|Public API cùng origin / JWT| Payment
    Account -->|Tra MSSV / JWT| Tuition
    Client[Swagger / REST client có JWT] --> Payment[Payment :8002]
    Client --> Tuition[Tuition :8003]
    Payment -->|REST debit / cancel / status| Account
    Payment -->|REST snapshot / reserve / finalize / release| Tuition
    Account --> ADB[(account_db)]
    Payment --> PDB[(payment_db)]
    Tuition --> TDB[(tuition_db)]
    Worker[Worker đối soát trong Payment] --> PDB
    Worker -->|REST retry cùng UUID| Account
    Worker -->|REST retry cùng UUID| Tuition
    Payment -->|Gửi OTP qua SMTP| Mail[Mailpit hoặc SMTP thật]
    MailWorker[Worker email trong Payment] --> PDB
    MailWorker -->|Biên nhận từ outbox| Mail
```

| Service | Quyền sở hữu và trách nhiệm |
|---|---|
| Account | Người dùng, JWT, tài khoản, số dư, ledger, dấu hủy debit |
| Tuition | Sinh viên/MSSV, hóa đơn, phiên bản, nhóm reservation và dấu hủy |
| Payment | UUID, PaymentItem, OTP, phase/retry, lịch sử, outbox biên nhận |

Mỗi service có engine, session, metadata và database riêng. Payment chỉ gọi REST;
không import model/đọc bảng Account hoặc Tuition. Tham chiếu user/account/invoice
trong Payment là ID logic, không là FK xuyên database. Các bảng prototype cũ
được giữ trong DB, không được API mới dùng. `shared/` chỉ chia sẻ hạ tầng kỹ thuật.

Docker dùng một SQL Server chứa ba DB cho demo. Chưa tách SQL login theo DB;
Account có gateway chỉ cho public API, UI dùng cùng origin không cần mở CORS.
Hai worker thanh toán/email khởi động cùng Payment, nên `start.ps1` vẫn là một lệnh.

Guard session applock dùng engine NullPool riêng, không lấy kết nối từ pool ORM
trong lúc chờ HTTP/SMTP. Bản thử tải ban đầu đã phát hiện nguy cơ hết pool khi
nhiều guard giữ kết nối và transaction ngắn không còn kết nối để hoàn tất.

## Use Case và quy tắc nghiệp vụ

Nguồn UML chuẩn: [use-cases.puml](diagrams/use-cases.puml).
Người trả là chủ tài khoản đã đăng nhập; sinh viên theo MSSV có thể là người khác.
Chức năng ghi/sửa hồ sơ và tài khoản nằm ngoài phân hệ học phí.

| Use Case | Điều kiện và luồng chính | Kết quả / luồng lỗi |
|---|---|---|
| UC01 Đăng nhập | Username/password hợp lệ, người dùng active | JWT có subject, issuer, audience và hạn; sai thông tin trả 401/403 |
| UC02 Tra MSSV | JWT hợp lệ; đọc tên sinh viên, các kỳ, tiền và trạng thái | Không có MSSV trả 404; RESERVED hiển thị đang xử lý |
| UC03 Chọn học phí | Chọn một/nhiều hóa đơn hoặc ALL_UNPAID | Server chốt hóa đơn/phiên bản/tổng; không nhận tiền hay người trả do client cung cấp |
| UC04 Xác minh OTP | Xác nhận snapshot rồi yêu cầu challenge | SMTP gửi mã một lần, 5 phút, 5 lần sai; resend hủy mã/xác minh cũ |
| UC05 Thanh toán | Đúng chủ, OTP còn hạn, chưa xử lý | Giữ toàn bộ nhóm → debit đúng tổng → hoàn tất; không được trả một phần nhóm |
| UC06 Tra kết quả/lịch sử | JWT và đúng chủ | Trả UUID/status/phase/items; timeout hướng dẫn tra cứu mã cũ |
| UC07 Đăng xuất | Phiên trình duyệt đang mở | UI xóa JWT trong RAM; chưa thu hồi JWT trung tâm |

Tiền dùng Decimal/NUMERIC(18,2). Mỗi sinh viên hiện có một hóa đơn cho mỗi học kỳ,
ràng buộc UNIQUE(student_id, semester). Một giao dịch có 1–100 hóa đơn. ALL_UNPAID
chốt công nợ có thể trả tại thời điểm tạo, không tự bổ sung hóa đơn được phát hành sau đó.

## ERD đã triển khai

Các quan hệ có ghi API là tham chiếu logic, không phải khóa ngoại giữa DB.
`schema_revisions` là bảng hạ tầng riêng trong mỗi DB, lược khỏi sơ đồ nghiệp vụ.

```mermaid
erDiagram
    users ||--o| accounts : owns
    accounts ||--o{ account_entries : ledger
    accounts ||--o{ account_cancellations : fences
    students ||--o{ tuition_invoices : has
    tuition_reservations ||--o{ tuition_reservation_items : includes
    tuition_invoices ||--o{ tuition_reservation_items : records
    payments ||--|{ payment_items : snapshots
    payments ||--o| email_outbox : receipt
    accounts ||..o{ payments : "API account_id"
    tuition_invoices ||..o{ payment_items : "API invoice_id"
    users {
        bigint id PK
        string username UK
        string password_hash
        string full_name
        string identity_number
        string email
        string phone
        boolean is_active
    }
    accounts {
        bigint id PK
        bigint user_id FK,UK
        string account_number UK
        decimal balance
        string status
    }
    account_entries {
        bigint id PK
        uuid payment_id
        bigint account_id FK
        string entry_type
        decimal amount
    }
    account_cancellations {
        uuid payment_id PK
        bigint account_id FK
        bigint payer_user_id
        decimal amount
    }
    students {
        int id PK
        string mssv UK
        string full_name
    }
    tuition_invoices {
        int id PK
        int student_id FK
        string semester
        decimal amount_due
        int version
        string status
        uuid reserved_payment_id
        uuid paid_payment_id
        datetime paid_at
    }
    tuition_reservations {
        uuid payment_id PK
        string request_hash
        string mssv
        decimal total_amount
        string status
    }
    tuition_reservation_items {
        int id PK
        uuid payment_id FK
        int invoice_id FK
        decimal amount
    }
    payments {
        uuid payment_id PK
        string transaction_code UK
        string request_hash
        bigint payer_user_id
        bigint account_id
        string mssv
        string student_name
        string selection_mode
        decimal total_amount
        string status
        string phase
        int retry_count
        datetime next_retry_at
        uuid challenge_id
        string otp_hash
        datetime otp_expires_at
        datetime otp_verified_at
        datetime completed_at
    }
    payment_items {
        int id PK
        uuid payment_id FK
        int invoice_id
        int invoice_version
        string semester
        decimal amount
    }
    email_outbox {
        uuid id PK
        uuid payment_id FK
        string event_type
        string recipient
        string subject
        string body
        string status
        int attempts
        datetime next_attempt_at
        datetime sent_at
    }
```

UUID được lưu dưới String(36). Ledger có UNIQUE(payment_id, entry_type);
PaymentItem và ReservationItem có UNIQUE(payment_id, invoice_id).
Balance không âm, các khoản thanh toán/bút toán dương. Reservation RELEASED có
thể không có item khi việc hủy đến trước yêu cầu giữ hóa đơn.

## Sequence thanh toán và phục hồi

```mermaid
sequenceDiagram
    actor U as Người dùng qua REST
    participant P as Payment
    participant T as Tuition
    participant A as Account
    participant W as Worker Payment
    U->>P: POST create (JWT, Idempotency-Key, MSSV, chế độ chọn)
    P->>A: users/me và accounts/me bằng JWT
    P->>T: Snapshot hóa đơn
    P-->>U: UUID, danh sách, tổng tiền
    U->>P: Yêu cầu OTP qua SMTP và xác minh mã nhận được
    U->>P: Process cùng UUID
    Note over P: Lưu PROCESSING/RESERVE trước REST
    P->>T: Reserve toàn bộ nhóm
    Note over P: Lưu phase DEBIT
    P->>A: Debit tổng tiền, cùng UUID
    Note over P: Lưu phase FINALIZE
    P->>T: Finalize cả nhóm
    Note over P: Commit SUCCEEDED và receipt outbox cùng transaction
    P-->>U: SUCCEEDED
    Note over P,W: Nếu timeout/crash: phase đã lưu được giữ lại
    W->>P: Quét PROCESSING/PENDING_RECONCILIATION
    W->>A: Retry/tra cứu cùng UUID
    W->>T: Retry/tra cứu cùng UUID
    Note over W: Không cần token/OTP cũ để tiếp tục intent đã được nhận
```

Payment có session application lock theo UUID để chỉ một coordinator xử lý cùng
lúc, kể cả khi chạy nhiều instance. Khóa session tồn tại qua các transaction ngắn;
không giữ transaction SQL mở trong khi gọi REST. DB session mất thì SQL Server
nhả khóa, worker khác tiếp tục từ trạng thái đã commit.

Tuition dùng transaction application lock theo UUID và UPDLOCK/HOLDLOCK trên từng
invoice theo ID tăng dần; nhóm giao nhau không bị giữ/hoàn tất một phần.
Account khóa UUID trước và khóa dòng tài khoản khi sửa balance, ghi ledger trong
cùng transaction. Tham khảo [Microsoft sp_getapplock](https://learn.microsoft.com/en-us/sql/relational-databases/system-stored-procedures/sp-getapplock-transact-sql)
và [table hints](https://learn.microsoft.com/en-us/sql/t-sql/queries/hints-transact-sql-table).

Hủy/bù trừ: fence Tuition trước. Nếu nhóm đã PAID, kiểm tra DEBITED và kết thúc
SUCCEEDED; không refund nhóm đã trả. Nếu RELEASED, Account cancel hoàn khoản đã
trừ hoặc lưu dấu hủy để debit đến muộn không có hiệu lực. Chỉ khi hoàn tất bù trừ
mới kết thúc FAILED/REFUNDED. Không tự nhả hóa đơn đang xử lý chỉ vì hết thời gian.

## Email và giao diện

Worker email đọc outbox và gửi SMTP ngoài transaction, retry không gọi lại thanh
toán. Message-ID cố định, một sự kiện/payment; SMTP có thể gửi trùng khi mất ACK.
UI tra MSSV, chọn hóa đơn, OTP, kết quả và lịch sử qua gateway Account. Chỉ UUID/
user ID được lưu tạm để phục hồi; token và OTP nằm trong bộ nhớ. Xem
[bàn giao UI/email](ui-email-delivery.md).
