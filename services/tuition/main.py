from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from services.tuition.database import engine
from services.tuition.routes import router
from services.tuition.internal_routes import router as internal_router

app = FastAPI(title='Tuition Service', version='0.1.0')
app.include_router(router)
app.include_router(internal_router)


@app.get('/health')
def health():
    return {'service': 'tuition-service', 'status': 'ok'}


@app.get('/health/db')
def health_db():
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        return {'database': 'tuition_db', 'status': 'connected'}
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail='Không kết nối được database') from None
