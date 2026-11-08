"""Account email ownership proof against the isolated SQL Server/Mailpit stack."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

from tests.integration import backend_acceptance as a
from tests.integration.mailpit import message_for


def main():
    if a.PROFILE!='isolated':raise RuntimeError('Email verification acceptance requires isolated Mailpit')
    checks=[]
    def passed(name):checks.append({'name':name,'result':'PASS'});print('PASS:',name,flush=True)
    actor=a.new_user();other=a.new_user()
    with a.AccountSession.begin() as db:db.get(a.User,actor['user_id']).email_verified_at=None
    original=a.check(a.request('account','GET','/users/me',headers=actor['headers']))
    target=uuid4().hex+'@example.test'
    data={name:original[name] for name in ('full_name','email','phone','identity_number')}
    data.update(email=target,full_name='Confirmed Inbox Owner',current_password=actor['password'])
    pending=a.check(a.request('account','PUT','/users/me',headers=actor['headers'],body=data),(202,))
    assert pending['email']==original['email'] and pending['email_verified'] is False and pending['pending_email']==target
    mssv,ids=a.new_student(['1000000.00'])
    assert a.request('payment','POST','/api/v1/payments',headers=actor['headers']|{'Idempotency-Key':str(uuid4())},body={'mssv':mssv,'terms_accepted':True}).status_code==409
    assert a.state(actor)==(Decimal('10000000.00'),[])
    passed('SMTP acceptance leaves unverified candidate inactive and cannot create a payment')
    challenge=pending['email_verification']['challenge_id']
    message=message_for(challenge,email_verification=True)
    assert message['To'][0]['Address']==target
    value=re.search(r'Mã xác minh email của bạn:\s*(\d{6})',message['Text']).group(1)
    def confirm(headers,code):return a.request('account','POST','/users/me/email-verification/confirm',headers=headers,body={'challenge_id':challenge,'code':code})
    assert confirm(other['headers'],value).status_code==409
    assert confirm(actor['headers'],'000000' if value!='000000' else '111111').status_code==400
    barrier=Barrier(3)
    def once(_):barrier.wait(timeout=10);return confirm(actor['headers'],value).status_code
    with ThreadPoolExecutor(max_workers=3) as pool:statuses=list(pool.map(once,range(3)))
    assert statuses.count(200)==1 and all(status in (200,409) for status in statuses)
    verified=a.check(a.request('account','GET','/users/me',headers=actor['headers']))
    assert verified['email']==target and verified['email_verified'] is True and verified['full_name']=='Confirmed Inbox Owner'
    assert confirm(actor['headers'],value).status_code==409
    passed('Proof is delivered to the candidate, bound to its owner and consumed once under concurrent confirmation')
    actor['email']=target
    payment=a.create(actor,mssv);a.verify(actor,payment)
    assert a.check(a.process(actor,payment),(200,202))['status'] in {'SUCCEEDED','PROCESSING','PENDING_RECONCILIATION'}
    assert a.terminal(actor,payment)['status']=='SUCCEEDED'
    receipt=message_for(payment['payment_id'],receipt=True)
    assert receipt['To'][0]['Address']==target
    assert a.state(actor)[0]==Decimal('9000000.00') and len(a.state(actor)[1])==1
    passed('Only after proof, transaction OTP and successful receipt go to the verified address')
    mssv,_=a.new_student(['1000000.00']);old=a.create(actor,mssv)
    with a.AccountSession.begin() as db:db.get(a.User,actor['user_id']).email_code_sent_at=a.utcnow()-timedelta(seconds=61)
    next_target=uuid4().hex+'@example.test';data['email']=next_target
    pending=a.check(a.request('account','PUT','/users/me',headers=actor['headers'],body=data),(202,))
    old_challenge=pending['email_verification']['challenge_id']
    old_code=re.search(r'Mã xác minh email của bạn:\s*(\d{6})',message_for(old_challenge,email_verification=True)['Text']).group(1)
    with a.AccountSession.begin() as db:
        row=db.get(a.User,actor['user_id']);row.email_code_expires_at=a.utcnow()-timedelta(seconds=1);row.email_code_sent_at=a.utcnow()-timedelta(seconds=61)
    assert a.request('account','POST','/users/me/email-verification/confirm',headers=actor['headers'],body={'challenge_id':old_challenge,'code':old_code}).status_code==400
    pending=a.check(a.request('account','POST','/users/me/email-verification/resend',headers=actor['headers'],body={'current_password':actor['password']}),(202,))
    challenge=pending['email_verification']['challenge_id']
    assert challenge!=old_challenge
    value=re.search(r'Mã xác minh email của bạn:\s*(\d{6})',message_for(challenge,email_verification=True)['Text']).group(1)
    assert value!=old_code and confirm(actor['headers'],old_code).status_code==400
    assert confirm(actor['headers'],value).status_code==200
    assert a.request('payment','POST','/api/v1/payments/'+old['payment_id']+'/send-otp',headers=actor['headers']).status_code==409
    passed('Expired/resend codes cannot activate email; a draft with a superseded recipient cannot send payment OTP')
    with a.AccountSession.begin() as db:db.get(a.User,actor['user_id']).email_code_sent_at=a.utcnow()-timedelta(seconds=61)
    data['email']=uuid4().hex+'@example.test'
    pending=a.check(a.request('account','PUT','/users/me',headers=actor['headers'],body=data),(202,))
    result=a.check(a.request('account','DELETE','/users/me/email-verification',headers=actor['headers']))
    assert result['email']==next_target and result['email_verified'] is True and result['pending_email'] is None
    assert a.state(actor)[0]==Decimal('9000000.00') and len(a.state(actor)[1])==1
    passed('Cancel keeps the previously verified recipient and never changes money effects')
    (a.ROOT/'artifacts/email-verification-acceptance.json').write_text(json.dumps({'status':'PASS','profile':'isolated','project':a.project,'checks':checks},ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':main()
