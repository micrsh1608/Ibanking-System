"""Same-origin public API gateway. Never forwards the internal API key."""
import os
from typing import Literal
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Request, Response

router = APIRouter(tags=['Web Gateway'])


async def forward(request, service, path):
    token = request.headers.get('authorization')
    if not token:
        raise HTTPException(401, 'Thiếu Bearer token')
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    key = request.headers.get('idempotency-key')
    if key:
        headers['Idempotency-Key'] = key
    body = await request.body()
    if len(body) > 16384:
        raise HTTPException(413, 'Nội dung yêu cầu quá lớn')
    base = os.getenv(f'{service.upper()}_SERVICE_URL',
        'http://127.0.0.1:8002' if service == 'payment' else 'http://127.0.0.1:8003')
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(40, connect=3), trust_env=False) as client:
            result = await client.request(request.method, base + path,
                params=list(request.query_params.multi_items()), headers=headers, content=body)
    except httpx.HTTPError:
        raise HTTPException(504, 'Máy chủ phản hồi chậm. Tra cứu hoặc thử lại bằng đúng mã giao dịch cũ.') from None
    return Response(result.content, status_code=result.status_code, headers={
        'Content-Type': result.headers.get('content-type', 'application/json'), 'Cache-Control': 'no-store'})


@router.get('/api/v1/tuition/{mssv}')
async def tuition(mssv: str, request: Request):
    if not 1 <= len(mssv) <= 24:
        raise HTTPException(422, 'MSSV không hợp lệ')
    return await forward(request, 'tuition', '/api/v1/tuition/' + quote(mssv, safe=''))


@router.get('/api/v1/payments')
@router.post('/api/v1/payments')
async def payments(request: Request):
    return await forward(request, 'payment', '/api/v1/payments')


@router.get('/api/v1/payments/{payment_id}')
async def payment(payment_id: UUID, request: Request):
    return await forward(request, 'payment', '/api/v1/payments/' + str(payment_id))


@router.post('/api/v1/payments/{payment_id}/{action}')
async def payment_action(payment_id: UUID, action: Literal['send-otp', 'verify-otp', 'process'], request: Request):
    return await forward(request, 'payment', f'/api/v1/payments/{payment_id}/{action}')
