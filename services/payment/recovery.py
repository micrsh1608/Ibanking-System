"""Recovery uses persisted intent, never an in-memory queue or an expired user token."""
import argparse
import logging
from threading import Event

from sqlalchemy import or_, select

from services.payment.coordinator import process_payment
from services.payment.database import SessionLocal
from services.payment.models.payment import PaymentTransaction
from shared.time import utcnow
from shared.observability import trace_context, log_event

logger = logging.getLogger(__name__)


def reconcile_once():
    with SessionLocal() as db:
        keys = db.scalars(select(PaymentTransaction.payment_id).where(
            PaymentTransaction.status.in_(['PROCESSING', 'PENDING_RECONCILIATION']),
            or_(PaymentTransaction.next_retry_at.is_(None), PaymentTransaction.next_retry_at <= utcnow())
        ).order_by(PaymentTransaction.updated_at).limit(50)).all()
    for key in keys:
        with trace_context():
            try:
                result = process_payment(key)
                log_event('payment', 'recovery', payment_id=key, status=result.status)
            except Exception as error:
                log_event('payment', 'recovery_error', payment_id=key, exception_type=type(error).__name__)
    return len(keys)


def run(stop: Event):
    while not stop.is_set():
        try:
            reconcile_once()
        except Exception as error:
            logger.warning('Recovery unavailable: %s', type(error).__name__)
        stop.wait(5)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    if args.once:
        reconcile_once()
    else:
        run(Event())
