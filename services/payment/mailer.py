"""Bounded SMTP transport; message content and authentication are never logged."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import format_datetime, parseaddr
from datetime import datetime, timezone


class MailError(Exception):
    pass


class Mailer:
    def send(self, *, recipient: str, subject: str, body: str, message_id: str):
        try:
            message = EmailMessage()
            sender = os.getenv('SMTP_FROM', 'iBanking <ibanking@example.test>')
            message['From'], message['To'], message['Subject'] = sender, recipient, subject
            message['Date'] = format_datetime(datetime.now(timezone.utc))
            message['Message-ID'] = f'<ibanking-{message_id}@notifications.ibanking.test>'
            message.set_content(body)
        except (ValueError, TypeError) as error:
            raise MailError(type(error).__name__) from None
        use_ssl = os.getenv('SMTP_SSL', 'false').lower() == 'true'
        use_starttls = os.getenv('SMTP_STARTTLS', 'false').lower() == 'true'
        try:
            if use_ssl and use_starttls:
                raise ValueError('Choose SSL or STARTTLS, not both')
            host = os.environ['SMTP_HOST']
            port = int(os.getenv('SMTP_PORT', '465' if use_ssl else '587'))
            username, password = os.getenv('SMTP_USERNAME'), os.getenv('SMTP_PASSWORD')
            if username and not password:
                raise ValueError('SMTP password is missing')
            options = {'host': host, 'port': port, 'timeout': 10}
            transport = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
            if use_ssl:
                options['context'] = ssl.create_default_context()
            with transport(**options) as smtp:
                if use_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if username:
                    smtp.login(username, password)
                refused = smtp.send_message(message, from_addr=parseaddr(sender)[1], to_addrs=[recipient])
                if refused:
                    raise MailError('RecipientRefused')
        except (OSError, smtplib.SMTPException, ValueError, KeyError) as error:
            raise MailError(type(error).__name__) from None


def get_mailer():
    return Mailer()
