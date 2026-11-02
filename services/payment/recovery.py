"""Recovery uses persisted intent, never an in-memory queue or an expired user token."""
import argparse
import logging
from threading import Event

from sqlalchemy import or_, select

from services.payment.coordinator import process_payment
from services.payment.database import SessionLocal
from services.payment.models.payment import PaymentTransaction
from shared.time import utcnow

logger = logging.getLogger(__name__)


def reconcile_once():
    with SessionLocal() as db:
        keys = db.scalars(select(PaymentTransaction.payment_id).where(
            PaymentTransaction.status.in_(['PROCESSING', 'PENDING_RECONCILIATION']),
            or_(PaymentTransaction.next_retry_at.is_(None), PaymentTransaction.next_retry_at <= utcnow())
        ).order_by(PaymentTransaction.updated_at).limit(50)).all()
    for key in keys:
        try:
            result = process_payment(key)
            logger.info('payment_id=%s recovery_status=%s', key, result.status)
        except Exception as error:
            logger.warning('payment_id=%s recovery_error=%s', key, type(error).__name__)
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
