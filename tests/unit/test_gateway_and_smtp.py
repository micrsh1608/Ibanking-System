import httpx
import pytest

from services.payment.mailer import Mailer, MailError


def test_gateway_only_forwards_public_auth_and_preserves_payment_conflicts(stack, monkeypatch):
    from services.account import gateway
    original = httpx.AsyncClient
    seen = []
    def receive(request):
        seen.append(request)
        return httpx.Response(409, json={'payment_id': 'test-id', 'status': 'FAILED'})
    monkeypatch.setattr(gateway.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(receive), **kwargs))
    key = '11111111-1111-4111-8111-111111111111'
    result = stack.account.post(f'/api/v1/payments/{key}/process', headers={**stack.headers, **stack.internal})
    assert result.status_code == 409 and result.json()['status'] == 'FAILED'
    assert 'x-internal-key' not in seen[0].headers
    assert seen[0].headers['authorization'] == stack.headers['Authorization']
    assert stack.account.post(f'/api/v1/payments/{key}/refund', headers=stack.headers).status_code == 422
    assert len(seen) == 1


@pytest.mark.parametrize('mode', ['starttls', 'ssl'])
def test_smtp_supports_authenticated_tls_without_logging_credentials(monkeypatch, mode):
    from services.payment import mailer
    calls = []
    class SMTP:
        def __init__(self, **kwargs): calls.append(('connection', kwargs))
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def starttls(self, **kwargs): calls.append(('tls', bool(kwargs['context'])))
        def login(self, username, password): calls.append(('login', username))
        def send_message(self, message, **kwargs):
            assert message['Message-ID'] == '<ibanking-test@notifications.ibanking.test>'
            calls.append(('send', kwargs['to_addrs']))
            return {}
    monkeypatch.setattr(mailer.smtplib, 'SMTP_SSL' if mode == 'ssl' else 'SMTP', SMTP)
    for name, value in {'SMTP_HOST': 'smtp.example.test', 'SMTP_PORT': '465' if mode == 'ssl' else '587',
            'SMTP_STARTTLS': str(mode == 'starttls'), 'SMTP_SSL': str(mode == 'ssl'),
            'SMTP_USERNAME': 'sender@example.test', 'SMTP_PASSWORD': 'synthetic-test-only'}.items():
        monkeypatch.setenv(name, value)
    Mailer().send(recipient='receiver@example.test', subject='Test', body='Test body', message_id='test')
    assert ('login', 'sender@example.test') in calls
    assert ('send', ['receiver@example.test']) in calls
    assert any(call[0] == 'tls' for call in calls) == (mode == 'starttls')


def test_smtp_rejects_conflicting_tls_configuration(monkeypatch):
    monkeypatch.setenv('SMTP_SSL', 'true')
    monkeypatch.setenv('SMTP_STARTTLS', 'true')
    with pytest.raises(MailError):
        Mailer().send(recipient='receiver@example.test', subject='Test', body='Test body', message_id='test')
