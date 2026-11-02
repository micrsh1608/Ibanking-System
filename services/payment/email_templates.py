from datetime import timedelta, timezone


def vnd(amount):
    return f'{amount:,.2f}'.replace(',', '_').replace('.', ',').replace('_', '.') + ' VND'


def local_time(value):
    return value.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M:%S (UTC+7)')


def invoice_lines(payment):
    return '\n'.join(f'- {item.semester} / hóa đơn #{item.invoice_id}: {vnd(item.amount)}' for item in payment.items)


def otp_message(payment, code):
    return (
        f'iBanking — Mã xác thực {payment.transaction_code}',
        f'Xin chào {payment.payer_name},\n\n'
        f'Mã OTP của bạn: {code}\n'
        f'Hết hạn: {local_time(payment.otp_expires_at)}\n\n'
        f'Sinh viên: {payment.student_name}\nMSSV: {payment.mssv}\n'
        f'{invoice_lines(payment)}\nTổng tiền: {vnd(payment.total_amount)}\n'
        f'Mã giao dịch: {payment.payment_id}\n\n'
        'Mã chỉ dùng một lần cho đúng giao dịch này. Không chia sẻ mã cho người khác.\n'
        'Nếu bạn không yêu cầu thanh toán, hãy bỏ qua email này.\n'
    )


def receipt_message(payment):
    return (
        f'iBanking — Thanh toán học phí thành công {payment.transaction_code}',
        f'Xin chào {payment.payer_name},\n\nThanh toán học phí đã hoàn tất.\n\n'
        f'Mã giao dịch: {payment.payment_id}\nMã hiển thị: {payment.transaction_code}\n'
        f'Thời gian ghi nhận: {local_time(payment.completed_at)}\n'
        f'Sinh viên: {payment.student_name}\nMSSV: {payment.mssv}\n'
        f'{invoice_lines(payment)}\nTổng đã thanh toán: {vnd(payment.total_amount)}\n'
        'Trạng thái: THÀNH CÔNG\n\n'
        'Bạn có thể đăng nhập iBanking và mở Lịch sử để đối chiếu giao dịch.\n'
    )
