"""Atomic receipt events and at-least-once SMTP delivery, independent of debiting."""
import logging
from datetime import timedelta
from threading import Event
from uuid import uuid4

from sqlalchemy import or_, select

from services.payment.database import SessionLocal, engine
from services.payment.email_templates import receipt_message
from services.payment.mailer import MailError, get_mailer
from services.payment.models.payment import EmailOutbox
from shared.locking import session_lock
from shared.time import utcnow

logger = logging.getLogger(__name__)


def enqueue_receipt(db, payment):
    existing = db.scalar(select(EmailOutbox).where(EmailOutbox.payment_id == payment.payment_id,
        EmailOutbox.event_type == 'PAYMENT_SUCCEEDED'))
    if existing is None:
        subject, body = receipt_message(payment)
        db.add(EmailOutbox(id=str(uuid4()), payment_id=payment.payment_id, event_type='PAYMENT_SUCCEEDED',
            recipient=payment.payer_email, email_channel=payment.email_channel,
            subject=subject, body=body, status='PENDING', attempts=0))


def dispatch_once(mailer=None):
    mailer = mailer or get_mailer()
    with SessionLocal() as db:
        ids = db.scalars(select(EmailOutbox.id).where(EmailOutbox.status == 'PENDING',
            EmailOutbox.email_channel.in_(('configured', 'smtp')),
            or_(EmailOutbox.next_attempt_at.is_(None), EmailOutbox.next_attempt_at <= utcnow()))
            .order_by(EmailOutbox.created_at).limit(50)).all()
    delivered = 0
    for key in ids:
        with session_lock(engine, 'mail:' + key) as acquired:
            if not acquired:
                continue
            with SessionLocal() as db:
                row = db.get(EmailOutbox, key)
                if row.status != 'PENDING' or (row.next_attempt_at is not None and row.next_attempt_at > utcnow()):
                    continue
            # Closing the read session ends its transaction before opening SMTP.
            try:
                mailer.send(recipient=row.recipient, subject=row.subject, body=row.body,
                    message_id=row.id, channel=row.email_channel)
            except MailError as error:
                with SessionLocal.begin() as db:
                    pending = db.get(EmailOutbox, key)
                    pending.attempts += 1
                    pending.last_error = str(error)[:80]
                    pending.next_attempt_at = utcnow() + timedelta(seconds=min(300, 2 ** min(pending.attempts + 1, 8)))
                logger.warning('payment_id=%s receipt_pending error=%s', row.payment_id, str(error))
            else:
                with SessionLocal.begin() as db:
                    sent = db.get(EmailOutbox, key)
                    sent.status, sent.sent_at, sent.last_error = 'SENT', utcnow(), None
                    sent.attempts += 1
                    sent.next_attempt_at = None
                delivered += 1
    return delivered


def run(stop: Event):
    while not stop.is_set():
        try:
            dispatch_once()
        except Exception as error:
            logger.warning('Receipt worker unavailable: %s', type(error).__name__)
        stop.wait(2)
