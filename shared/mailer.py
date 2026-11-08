"""Bounded SMTP transport; message content and authentication are never logged."""
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import format_datetime, parseaddr
from datetime import datetime, timezone


class MailError(Exception):
    pass


def _capture_host(host):
    normalized = str(host or '').strip().lower().rstrip('.')
    if normalized in {'mailpit', 'mailhog'}:
        return True
    return (normalized in {'localhost', '127.0.0.1', '::1', 'host.docker.internal'}
            and os.getenv('SMTP_PORT', '587') == '1025')


def resolve_email_channel(channel='configured'):
    """Resolve a read-only account route without connecting or raising errors."""
    if not isinstance(channel, str):
        return 'not_configured'
    if channel not in {'configured', 'smtp'}:
        return 'not_configured'
    host = os.getenv('SMTP_HOST', '').strip()
    if not host:
        return 'not_configured'
    if _capture_host(host):
        return 'not_configured'
    return 'smtp'


def transport_settings(channel):
    if channel not in {'configured', 'smtp'}:
        raise ValueError('Only real SMTP delivery is supported')
    host = os.environ['SMTP_HOST']
    if resolve_email_channel(channel) != 'smtp':
        raise ValueError('Real SMTP delivery requires a configured SMTP host')
    use_ssl = os.getenv('SMTP_SSL', 'false').lower() == 'true'
    use_starttls = os.getenv('SMTP_STARTTLS', 'false').lower() == 'true'
    if use_ssl and use_starttls:
        raise ValueError('Choose SSL or STARTTLS, not both')
    username, password = os.getenv('SMTP_USERNAME'), os.getenv('SMTP_PASSWORD')
    if username and not password:
        raise ValueError('SMTP password is missing')
    return {'host': host, 'port': int(os.getenv('SMTP_PORT', '465' if use_ssl else '587')),
            'sender': os.environ['SMTP_FROM'],
            'use_ssl': use_ssl, 'use_starttls': use_starttls,
            'username': username, 'password': password}


class Mailer:
    def send(self, *, recipient: str, subject: str, body: str, message_id: str, channel='configured'):
        try:
            settings = transport_settings(channel)
            message = EmailMessage()
            sender = settings['sender']
            message['From'], message['To'], message['Subject'] = sender, recipient, subject
            message['Date'] = format_datetime(datetime.now(timezone.utc))
            message['Message-ID'] = f'<ibanking-{message_id}@notifications.ibanking.test>'
            message.set_content(body)
        except (ValueError, TypeError, KeyError) as error:
            raise MailError(type(error).__name__) from None
        use_ssl, use_starttls = settings['use_ssl'], settings['use_starttls']
        try:
            username, password = settings['username'], settings['password']
            options = {'host': settings['host'], 'port': settings['port'], 'timeout': 10}
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
