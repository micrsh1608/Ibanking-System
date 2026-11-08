"""Request correlation and allowlisted JSON logs, without request bodies or secrets."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import time
from uuid import UUID, uuid4

from starlette.responses import JSONResponse

_request_id = ContextVar('ibanking_request_id', default=None)
logger = logging.getLogger('ibanking.events')
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def normalize_request_id(value=None):
    try:
        return str(UUID(value)) if isinstance(value, str) and len(value) <= 36 else str(uuid4())
    except ValueError:
        return str(uuid4())


def current_request_id():
    return _request_id.get()


def tracing_headers():
    value = current_request_id()
    return {'X-Request-ID': value} if value else {}


@contextmanager
def trace_context():
    """Background retries get their own request ID; payment_id links retry attempts."""
    token = _request_id.set(current_request_id() or str(uuid4()))
    try:
        yield
    finally:
        _request_id.reset(token)


def log_event(service, event, **fields):
    # A fixed allowlist prevents accidental logging of email, OTP, tokens or SQL.
    allowed = {'method', 'route', 'status', 'duration_ms', 'payment_id', 'phase', 'exception_type'}
    record = {'timestamp': datetime.now(timezone.utc).isoformat(), 'service': service,
              'event': event, 'request_id': current_request_id()}
    record.update({key: value for key, value in fields.items() if key in allowed})
    try:
        logger.info(json.dumps(record, ensure_ascii=True, separators=(',', ':')))
    except Exception:
        # Logging must never change the outcome of a committed payment.
        pass


class RequestContextMiddleware:
    def __init__(self, app, service):
        self.app, self.service = app, service

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        supplied = next((value.decode('ascii', errors='ignore') for key, value in scope['headers']
                         if key.lower() == b'x-request-id'), None)
        request_id = normalize_request_id(supplied)
        token = _request_id.set(request_id)
        started, status, response_started, exception_type = time.perf_counter(), 500, False, None

        async def correlated_send(message):
            nonlocal status, response_started
            if message['type'] == 'http.response.start':
                response_started, status = True, message['status']
                headers = [(key, value) for key, value in message.get('headers', []) if key.lower() != b'x-request-id']
                message = dict(message, headers=headers + [(b'x-request-id', request_id.encode('ascii'))])
            await send(message)

        try:
            await self.app(scope, receive, correlated_send)
        except Exception as error:
            exception_type = type(error).__name__
            if response_started:
                raise
            response = JSONResponse({'detail': 'Lỗi máy chủ; dùng X-Request-ID để đối chiếu.'}, status_code=500)
            await response(scope, receive, correlated_send)
        finally:
            try:
                route = getattr(scope.get('route'), 'path', 'unmatched')
                fields = {'method': scope['method'], 'route': route, 'status': status,
                          'duration_ms': round((time.perf_counter() - started) * 1000, 3)}
                payment_id = scope.get('path_params', {}).get('payment_id')
                if payment_id:
                    try:
                        fields['payment_id'] = str(UUID(str(payment_id)))
                    except ValueError:
                        pass
                if exception_type:
                    fields['exception_type'] = exception_type
                log_event(self.service, 'http_request', **fields)
            finally:
                _request_id.reset(token)
