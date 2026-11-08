"""Read only synthetic acceptance emails, without printing message content or codes."""
import time
import os

import httpx
import re


def all_codes_for(payment_id):
    """Synthetic test codes, kept in test memory; useful when a payment has resends."""
    base='http://127.0.0.1:'+('8026' if os.getenv('IBANKING_TEST_PROFILE')=='isolated' else '8025')
    codes=[]
    with httpx.Client(timeout=5,trust_env=False) as client:
        response=client.get(base+'/api/v1/search',params={'query':'"'+payment_id+'"'});response.raise_for_status()
        for summary in response.json()['messages']:
            if 'mã xác thực' not in summary['Subject'].lower():continue
            message=client.get(base+'/api/v1/message/'+summary['ID']);message.raise_for_status()
            codes+=re.findall(r'Mã OTP của bạn:\s*(\d{6})',message.json()['Text'])
    return codes


def message_for(payment_id, *, receipt=False, email_verification=False, timeout=30):
    deadline = time.monotonic() + timeout
    phrase = 'xác minh email' if email_verification else 'thành công' if receipt else 'mã xác thực'
    base = 'http://127.0.0.1:' + ('8026' if os.getenv('IBANKING_TEST_PROFILE') == 'isolated' else '8025')
    with httpx.Client(timeout=5, trust_env=False) as client:
        while time.monotonic() < deadline:
            response = client.get(base + '/api/v1/search', params={'query': '"' + payment_id + '"'})
            response.raise_for_status()
            for summary in response.json()['messages']:
                if phrase in summary['Subject'].lower():
                    result = client.get(base + '/api/v1/message/' + summary['ID'])
                    result.raise_for_status()
                    return result.json()
            time.sleep(.25)
    raise AssertionError('Expected acceptance email was not received: ' + payment_id)
