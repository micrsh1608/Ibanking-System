# Tuition Service

Sở hữu sinh viên/MSSV, hóa đơn có phiên bản, nhóm reservation và chi tiết nhóm
trong `tuition_db`. Mã nguồn: `services/tuition/`.

```powershell
.\.venv\Scripts\python.exe -m services.tuition.seed
.\.venv\Scripts\python.exe -m uvicorn services.tuition.main:app --reload --port 8003
```

Cách chạy chung: `.\start.ps1`. Seed tự chạy migration, giữ dữ liệu có sẵn;
demo `SV2026001` có hai học kỳ 2 triệu và 3 triệu. ID phụ thuộc database đang dùng.

- API công khai `GET /api/v1/tuition/{mssv}` dùng JWT Account.
- API nội bộ snapshot/reserve/finalize/release/status dùng `X-Internal-Key`.
- Khóa UUID và khóa các invoice theo ID tăng dần trong transaction SQL Server.
- Một nhóm được giữ/hoàn tất/nhả toàn bộ; request trùng trả cùng kết quả.
- Fingerprint và version từ chối payload hoặc snapshot đã thay đổi.
- Release tạo dấu hủy kể cả khi reserve chưa đến; không nhả nhóm đã PAID.
- Không tự nhả reservation theo TTL khi chưa biết kết quả tiền.

Xem [API](../api.md), [migration](../migrations.md), [nghiệm thu SQL Server](../backend-delivery.md).
