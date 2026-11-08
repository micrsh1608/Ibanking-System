import asyncio
import json
import logging
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared import observability as obs


@pytest.fixture
def events():
    records = []
    class Capture(logging.Handler):
        def emit(self, record):
            records.append(json.loads(record.getMessage()))
    handler = Capture()
    obs.logger.addHandler(handler)
    try:
        yield records
    finally:
        obs.logger.removeHandler(handler)


@pytest.mark.parametrize('service', ['account', 'payment', 'tuition'])
def test_services_return_valid_request_ids_for_success_and_auth_errors(service):
    from importlib import import_module
    app = import_module(f'services.{service}.main').app
    key = str(uuid4())
    with TestClient(app) as client:
        assert client.get('/health', headers={'X-Request-ID': key}).headers['X-Request-ID'] == key
        response = client.get('/not-a-route', headers={'X-Request-ID': 'invalid'})
        assert response.status_code == 404
        UUID(response.headers['X-Request-ID'])
        assert response.headers['X-Request-ID'] != key


def test_logs_use_route_templates_and_exclude_credentials_queries_and_error_messages(events):
    app = FastAPI()
    app.add_middleware(obs.RequestContextMiddleware, service='example')
    @app.get('/student/{mssv}')
    def lookup(mssv: str):
        return {'ok': True}
    @app.get('/broken')
    def broken():
        raise RuntimeError('PRIVATE-ERROR-TEXT')
    with TestClient(app) as client:
        client.get('/student/PRIVATE-STUDENT?email=PRIVATE-EMAIL', headers={'Authorization': 'Bearer PRIVATE-TOKEN'})
        error = client.get('/broken')
    assert error.status_code == 500
    UUID(error.headers['X-Request-ID'])
    assert events[0]['route'] == '/student/{mssv}'
    assert events[-1]['exception_type'] == 'RuntimeError'
    assert 'PRIVATE-' not in json.dumps(events) + error.text


def test_concurrent_requests_keep_separate_context_and_reset_it_afterwards():
    app = FastAPI()
    app.add_middleware(obs.RequestContextMiddleware, service='example')
    @app.get('/context')
    async def context():
        before = obs.current_request_id()
        await asyncio.sleep(.02)
        assert before == obs.current_request_id()
        return {'request_id': before}
    async def exercise():
        keys = [str(uuid4()) for _ in range(8)]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            responses = await asyncio.gather(*(client.get('/context', headers={'X-Request-ID': key}) for key in keys))
        assert [response.json()['request_id'] for response in responses] == keys
        assert [response.headers['X-Request-ID'] for response in responses] == keys
        assert obs.current_request_id() is None
    asyncio.run(exercise())


def test_gateway_preserves_correlation_but_does_not_forward_browser_internal_key(monkeypatch):
    from services.account.main import app
    from services.account import gateway
    captured = []
    real_client = httpx.AsyncClient
    def upstream(request):
        captured.append(request)
        return httpx.Response(200, json={'ok': True})
    monkeypatch.setattr(gateway.httpx, 'AsyncClient', lambda **options: real_client(transport=httpx.MockTransport(upstream), **options))
    key = str(uuid4())
    with TestClient(app) as client:
        response = client.get('/api/v1/payments', headers={'Authorization': 'Bearer test-only', 'X-Request-ID': key, 'X-Internal-Key': 'must-not-forward'})
    assert response.status_code == 200
    assert captured[0].headers['X-Request-ID'] == key
    assert 'X-Internal-Key' not in captured[0].headers


def test_payment_rest_calls_propagate_the_current_request_and_background_context(monkeypatch):
    from services.payment import clients
    captured = []
    real_client = httpx.Client
    def upstream(request):
        captured.append(request)
        return httpx.Response(200, json={'status': 'ok'})
    monkeypatch.setattr(clients.httpx, 'Client', lambda **options: real_client(transport=httpx.MockTransport(upstream), **options))
    with obs.trace_context():
        key = obs.current_request_id()
        clients.Services().request('tuition', 'GET', '/internal/tuition/invoices')
        clients.Services().request('account', 'GET', '/users/me', token='test-only')
    assert all(request.headers['X-Request-ID'] == key for request in captured)
    assert obs.current_request_id() is None


def test_logger_failure_does_not_change_the_http_result(monkeypatch):
    app = FastAPI()
    app.add_middleware(obs.RequestContextMiddleware, service='example')
    @app.get('/ok')
    def ok():
        return {'ok': True}
    def fail(*args, **kwargs):
        raise OSError('log device unavailable')
    monkeypatch.setattr(obs.logger, 'info', fail)
    with TestClient(app) as client:
        assert client.get('/ok').json() == {'ok': True}
