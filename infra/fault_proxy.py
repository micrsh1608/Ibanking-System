"""Acceptance-only HTTP fault proxy. Not started by the normal Compose project."""
import asyncio
import os
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Request, HTTPException, Response
from pydantic import BaseModel, Field
from typing import Literal

app = FastAPI(title='Local acceptance fault proxy')
rules = {}
events = []


class Rule(BaseModel):
    path: str = Field(pattern=r'^/internal/')
    mode: Literal['delay_after', 'error_before']
    seconds: float = Field(default=14, ge=0, le=60)
    remaining: int = Field(default=1, ge=-1, le=100)


@app.post('/__faults')
def configure(rule: Rule):
    rules[rule.path] = rule.model_dump()
    return {'configured': True}


@app.delete('/__faults')
def clear():
    rules.clear()
    events.clear()
    return {'cleared': True}


@app.get('/__faults')
def inspect():
    return {'rules': list(rules.values()), 'events': events[-100:]}


@app.api_route('/{path:path}', methods=['GET', 'POST'])
async def forward(path: str, request: Request):
    path = '/' + path
    rule = rules.get(path)
    if rule is not None and rule['remaining'] != 0:
        rule = dict(rule)
        if rules[path]['remaining'] > 0:
            rules[path]['remaining'] -= 1
    else:
        rule = None
    if rule and rule['mode'] == 'error_before':
        raise HTTPException(503, 'Acceptance-only simulated outage')
    headers = {name: request.headers[name] for name in ('authorization', 'x-internal-key', 'content-type', 'idempotency-key', 'x-request-id') if name in request.headers}
    async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
        response = await client.request(request.method, os.environ['FAULT_TARGET_URL'] + path,
            params=list(request.query_params.multi_items()), headers=headers, content=await request.body())
    if rule and rule['mode'] == 'delay_after':
        events.append({'path': path, 'upstream_status': response.status_code,
            'committed_reply_delayed_at': datetime.now(timezone.utc).isoformat()})
        await asyncio.sleep(rule['seconds'])
    return Response(response.content, status_code=response.status_code,
        headers={'content-type': response.headers.get('content-type', 'application/json')})
