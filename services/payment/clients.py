"""Bounded REST calls. An unknown result is retried with the same UUID by recovery."""
import os

import httpx
from shared.observability import tracing_headers


class UpstreamError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(detail)


class Services:
    def request(self, service, method, path, *, token=None, body=None):
        base = os.getenv(f'{service.upper()}_SERVICE_URL',
            'http://127.0.0.1:8001' if service == 'account' else 'http://127.0.0.1:8003')
        headers = {'Authorization': f'Bearer {token}'} if token else {'X-Internal-Key': os.environ['INTERNAL_API_KEY']}
        headers.update(tracing_headers())
        try:
            with httpx.Client(timeout=httpx.Timeout(10, connect=3), trust_env=False) as client:
                response = client.request(method, base + path, headers=headers, json=body)
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            raise UpstreamError(503, f'{service}: chưa xác định được kết quả') from None
        if response.status_code >= 400:
            detail = payload.get('detail', 'Upstream error') if isinstance(payload, dict) else 'Upstream error'
            raise UpstreamError(response.status_code, str(detail))
        if not isinstance(payload, dict):
            raise UpstreamError(503, f'{service}: phản hồi không hợp lệ')
        return payload

    def payer(self, token):
        return (self.request('account', 'GET', '/users/me', token=token),
            self.request('account', 'GET', '/accounts/me', token=token))

    def invoices(self, mssv):
        from urllib.parse import urlencode
        return self.request('tuition', 'GET', '/internal/tuition/invoices?' + urlencode({'mssv': mssv}))

    def reserve(self, payment):
        return self.request('tuition', 'POST', '/internal/tuition/reservations', body={
            'payment_id': payment.payment_id, 'mssv': payment.mssv,
            'items': [{'invoice_id': item.invoice_id, 'version': item.invoice_version} for item in payment.items],
            'expected_total': format(payment.total_amount, '.2f'),
            'require_all_unpaid': payment.selection_mode == 'ALL_UNPAID'})

    def reservation(self, payment_id, action=None):
        path = f'/internal/tuition/reservations/{payment_id}'
        return self.request('tuition', 'POST' if action else 'GET', path + (f'/{action}' if action else ''))

    def account(self, payment, action):
        return self.request('account', 'POST', f'/internal/accounts/{action}', body={
            'payment_id': payment.payment_id, 'account_id': payment.account_id,
            'payer_user_id': payment.payer_user_id, 'amount': format(payment.total_amount, '.2f')})

    def operation(self, payment_id):
        return self.request('account', 'GET', f'/internal/account-operations/{payment_id}')


def get_services():
    return Services()
