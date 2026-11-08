"""OTP/commit acceptance on the explicitly isolated Mailpit/SQL stack only."""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from tests.integration import backend_acceptance as a
from tests.integration.mailpit import all_codes_for, message_for
from services.payment.models.payment import EmailOutbox, PaymentTransaction
from services.payment.otp import allocate_code, code_fingerprint, hash_otp
from services.tuition.models import TuitionInvoice


def code_for(key):
    return re.search(r'Mã OTP của bạn:\s*(\d{6})',message_for(key)['Text']).group(1)


def send(user,payment):
    result=a.check(a.request('payment','POST','/api/v1/payments/'+payment['payment_id']+'/send-otp',headers=user['headers']),(202,))
    assert not {'otp','otp_hash','otp_fingerprint'} & set(result)
    return result


def verify(user,payment,challenge,code):
    return a.request('payment','POST','/api/v1/payments/'+payment['payment_id']+'/verify-otp',headers=user['headers'],
        body={'challenge_id':challenge['challenge_id'],'otp':code})


def draft(user):
    mssv,_=a.new_student(['1000000.00'])
    return a.create(user,mssv)


def shared_otp_and_shared_tuition(passed):
    """Two authenticated payers: foreign OTP fails, and correct OTPs cannot double-pay."""
    users = [a.new_user(), a.new_user()]
    mssv, invoice_ids = a.new_student(['2000000.00', '3000000.00'])
    payments = [a.create(user, mssv) for user in users]
    challenges = [send(user, payment) for user, payment in zip(users, payments)]
    codes = [code_for(payment['payment_id']) for payment in payments]
    assert codes[0] != codes[1]

    # Both sessions submit the SAME six digits, each against its own challenge.
    responses = a.parallel([
        lambda index=index: verify(users[index], payments[index], challenges[index], codes[0])
        for index in range(2)
    ])
    assert [response.status_code for response in responses] == [200, 400]
    assert verify(users[1], payments[1], challenges[0], codes[0]).status_code == 400
    assert verify(users[1], payments[0], challenges[0], codes[0]).status_code == 404
    assert a.process(users[1], payments[1]).status_code == 409
    assert all(a.state(user) == (Decimal('10000000.00'), []) for user in users)
    with a.TuitionSession() as db:
        assert all(db.get(TuitionInvoice, key).status == 'UNPAID' for key in invoice_ids)
    passed('Two payers submitting the same OTP cannot verify each other or debit either account')

    # Give the losing verifier its own valid code, then process both public APIs
    # concurrently. The Tuition reservation must win BEFORE any Account debit.
    assert verify(users[1], payments[1], challenges[1], codes[1]).status_code == 200
    responses = a.parallel([
        lambda user=user, payment=payment: a.process(user, payment)
        for user, payment in zip(users, payments)
    ])
    for response in responses:
        a.check(response, (200, 202, 409))
    results = [a.terminal(user, payment) for user, payment in zip(users, payments)]
    assert sorted(result['status'] for result in results) == ['FAILED', 'SUCCEEDED']
    winner = next(index for index, result in enumerate(results) if result['status'] == 'SUCCEEDED')
    loser = 1 - winner
    winner_key = payments[winner]['payment_id']
    assert a.state(users[winner]) == (Decimal('5000000.00'), [(winner_key, 'DEBIT', Decimal('5000000.00'))])
    assert a.state(users[loser]) == (Decimal('10000000.00'), [])
    with a.TuitionSession() as db:
        assert all(db.get(TuitionInvoice, key).status == 'PAID' and
                   db.get(TuitionInvoice, key).paid_payment_id == winner_key for key in invoice_ids)
    with a.PaymentSession() as db:
        events = list(db.scalars(select(EmailOutbox).where(
            EmailOutbox.payment_id.in_([payment['payment_id'] for payment in payments]))))
        assert len(events) == 1 and events[0].payment_id == winner_key
        assert events[0].recipient == users[winner]['email']
    # Replays keep the winner's single debit and never charge the loser later.
    assert a.check(a.process(users[winner], payments[winner]))['status'] == 'SUCCEEDED'
    assert a.check(a.process(users[loser], payments[loser]), (409,))['status'] == 'FAILED'
    assert a.state(users[winner])[0] == Decimal('5000000.00') and len(a.state(users[winner])[1]) == 1
    assert a.state(users[loser]) == (Decimal('10000000.00'), [])
    passed('Two correct OTPs for one MSSV commit exactly one 5M debit; the losing account keeps all 10M')


def main():
    if a.PROFILE!='isolated':
        raise RuntimeError('OTP acceptance requires the isolated release stack; never use the real SMTP configuration')
    checks=[]
    def passed(name):checks.append({'name':name,'result':'PASS'});print('PASS:',name,flush=True)

    user=a.new_user()
    payments=[draft(user) for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        challenges=list(pool.map(lambda p:send(user,p),payments))
    codes=[code_for(payment['payment_id']) for payment in payments]
    assert len(set(codes))==len(codes)
    with a.PaymentSession() as db:
        fingerprints=[db.get(PaymentTransaction,p['payment_id']).otp_fingerprint for p in payments]
        assert len(set(fingerprints))==len(payments) and all(fingerprints)
    passed('Eight simultaneous SMTP OTP issues have distinct active codes and stored fingerprints')

    # Force a collision at the real SQL allocation boundary, independently of
    # random chance. Both transactions initially request the same code.
    forced=[draft(user) for _ in range(2)];barrier=Barrier(2)
    # Choose deterministic candidates outside every existing reservation.
    with a.PaymentSession() as db:
        occupied=set(db.scalars(select(PaymentTransaction.otp_fingerprint).where(PaymentTransaction.otp_fingerprint.is_not(None))))
    candidates=[f'{number:06d}' for number in range(1000) if code_fingerprint(f'{number:06d}') not in occupied][:3]
    def claim(index):
        samples=iter(candidates)
        barrier.wait(timeout=15)
        with a.PaymentSession.begin() as db:
            row=db.get(PaymentTransaction,forced[index]['payment_id']);now=a.utcnow()
            code=allocate_code(db,row,now,lambda:next(samples))
            row.challenge_id=str(uuid4());row.otp_expires_at=now+timedelta(minutes=5);row.otp_last_sent_at=now
            row.otp_hash=hash_otp(row,code)
            return row.otp_fingerprint
    with ThreadPoolExecutor(max_workers=2) as pool:claimed=list(pool.map(claim,range(2)))
    assert claimed[0]!=claimed[1]
    try:
        with a.PaymentSession.begin() as db:
            db.get(PaymentTransaction,forced[1]['payment_id']).otp_fingerprint=claimed[0]
            db.flush()
    except IntegrityError:pass
    else:raise AssertionError('SQL Server accepted a duplicate OTP fingerprint')
    with a.PaymentSession.begin() as db:
        for payment in forced:
            row=db.get(PaymentTransaction,payment['payment_id'])
            row.otp_fingerprint=row.otp_hash=row.challenge_id=row.otp_expires_at=row.otp_last_sent_at=None
    passed('SQL Server serializes a forced simultaneous collision and its unique index rejects duplicates')

    shared_otp_and_shared_tuition(passed)

    first,second=payments[:2]
    assert verify(user,second,challenges[1],codes[0]).status_code==400
    assert verify(user,second,challenges[0],codes[0]).status_code==400
    with a.PaymentSession.begin() as db:
        db.get(PaymentTransaction,first['payment_id']).otp_expires_at=a.utcnow()-timedelta(seconds=1)
    assert verify(user,first,challenges[0],codes[0]).status_code==400
    assert a.process(user,first).status_code==409
    assert a.state(user)==(Decimal('10000000.00'),[])
    passed('Wrong transaction/challenge and expired OTP cannot verify or debit')

    with a.PaymentSession.begin() as db:
        db.get(PaymentTransaction,first['payment_id']).otp_last_sent_at=a.utcnow()-timedelta(seconds=61)
    new=send(user,first)
    # Mailpit may return the older message first; match the new challenge using
    # the persisted keyed hash instead of printing or exposing candidate codes.
    if new['challenge_id']==challenges[0]['challenge_id']:raise AssertionError('Resend did not replace challenge')
    with a.PaymentSession() as db:
        row=db.get(PaymentTransaction,first['payment_id'])
        deadline=time.monotonic()+15
        new_code=None
        while time.monotonic()<deadline and new_code is None:
            new_code=next((code for code in all_codes_for(first['payment_id']) if hash_otp(row,code)==row.otp_hash),None)
            if new_code is None:time.sleep(.25)
        assert new_code is not None,'Resent OTP email did not arrive'
    assert new_code!=codes[0]
    assert verify(user,first,new,codes[0]).status_code==400
    assert verify(user,first,challenges[0],codes[0]).status_code==400
    passed('Resend invalidates the previous email code and previous challenge')

    barrier=Barrier(5)
    def once():barrier.wait(timeout=15);return verify(user,first,new,new_code).status_code
    with ThreadPoolExecutor(max_workers=5) as pool:statuses=list(pool.map(lambda _:once(),range(5)))
    assert statuses.count(200)==1 and all(status in (200,409) for status in statuses)
    passed('Five concurrent verifications consume the same OTP exactly once')

    assert a.check(a.process(user,first),(200,202))['status'] in {'SUCCEEDED','PROCESSING','PENDING_RECONCILIATION'}
    assert a.terminal(user,first)['status']=='SUCCEEDED'
    assert verify(user,first,new,new_code).status_code==409
    assert a.check(a.process(user,first))['status']=='SUCCEEDED'
    assert a.state(user)[0]==Decimal('9000000.00') and len(a.state(user)[1])==1
    key=first['payment_id'];receipt=message_for(key,receipt=True)
    assert receipt['To'][0]['Address']==user['email']
    assert first['mssv'] in receipt['Text'] and key in receipt['Text'] and '1.000.000,00' in receipt['Text']
    with a.TuitionSession() as db:assert all(db.get(TuitionInvoice,item['invoice_id']).status=='PAID' and db.get(TuitionInvoice,item['invoice_id']).paid_payment_id==key for item in first['items'])
    with a.PaymentSession() as db:
        assert db.get(PaymentTransaction,key).status=='SUCCEEDED'
        events=db.scalars(select(EmailOutbox).where(EmailOutbox.payment_id==key)).all()
        assert len(events)==1
    history=a.check(a.request('payment','GET','/api/v1/payments',headers=user['headers']))
    assert any(row['payment_id']==key and row['status']=='SUCCEEDED' for row in history['items'])
    passed('Successful payment agrees across balance/ledger/tuition/history and sends the receipt to its payer')

    expired=draft(user);challenge=send(user,expired);code=code_for(expired['payment_id'])
    assert verify(user,expired,challenge,code).status_code==200
    with a.PaymentSession.begin() as db:db.get(PaymentTransaction,expired['payment_id']).otp_expires_at=a.utcnow()-timedelta(seconds=1)
    assert a.process(user,expired).status_code==409
    assert a.state(user)[0]==Decimal('9000000.00') and len(a.state(user)[1])==1
    passed('Verification cannot start a payment after its original five-minute deadline')
    target=a.ROOT/'artifacts/otp-consistency-acceptance.json'
    target.write_text(json.dumps({'status':'PASS','checked_at_utc':a.utcnow().isoformat()+'Z','profile':a.PROFILE,'sql_server':'127.0.0.1,14331','checks':checks},ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()
