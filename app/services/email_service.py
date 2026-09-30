import smtplib
from email.message import EmailMessage

from app.core.config import settings


class EmailService:
    def send_otp(self, to_email: str, otp: str, transaction_id: str, expires_in: int) -> None:
        # DEMO mode: no SMTP configuration -> print OTP in terminal.
        if not settings.smtp_host:
            print(
                f"[DEMO EMAIL] to={to_email} | "
                f"transaction={transaction_id} | OTP={otp} | expires={expires_in}s"
            )
            return

        message = EmailMessage()
        message["Subject"] = "iBanking - Ma OTP xac thuc giao dich"
        message["From"] = settings.smtp_from
        message["To"] = to_email
        message.set_content(
            f"Ma OTP cua ban la: {otp}\n"
            f"Giao dich: {transaction_id}\n"
            f"Ma co hieu luc trong {expires_in // 60} phut."
        )

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
