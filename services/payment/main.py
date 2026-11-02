import os
from contextlib import asynccontextmanager
from threading import Event, Thread

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from services.payment.clients import UpstreamError
from services.payment.database import engine
from services.payment.recovery import run
from services.payment.routes import router
from services.payment.outbox import run as run_mail


@asynccontextmanager
async def lifespan(app):
    stop = Event()
    workers = []
    if os.getenv('PAYMENT_RECOVERY_ENABLED', 'true').lower() == 'true':
        workers.append(Thread(target=run, args=(stop,), name='payment-recovery', daemon=True))
    if os.getenv('PAYMENT_MAIL_ENABLED', 'true').lower() == 'true':
        workers.append(Thread(target=run_mail, args=(stop,), name='payment-mail', daemon=True))
    for worker in workers:
        worker.start()
    try:
        yield
    finally:
        stop.set()
        for worker in workers:
            worker.join(timeout=15)


app = FastAPI(title='Payment Service', version='0.2.0', lifespan=lifespan)
app.include_router(router)


@app.exception_handler(UpstreamError)
async def upstream_error(request: Request, error: UpstreamError):
    return JSONResponse(status_code=503 if error.status >= 500 else error.status, content={'detail': error.detail})


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, error: SQLAlchemyError):
    return JSONResponse(status_code=503, content={'detail': 'Database chưa xác nhận kết quả; tra cứu/thử lại cùng payment_id'})


@app.get('/')
def root():
    return {'service': 'payment-service', 'version': '0.2.0'}


@app.get('/health')
def health():
    return {'service': 'payment-service', 'status': 'ok'}


@app.get('/health/db')
def database_health():
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
        return {'database': 'payment_db', 'status': 'connected'}
    except SQLAlchemyError:
        raise HTTPException(503, 'Không kết nối được database') from None
