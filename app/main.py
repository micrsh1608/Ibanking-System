from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.routes import router
from app.database import engine
from app.internal_routes import router as internal_router
from pathlib import Path
from fastapi.staticfiles import StaticFiles


app = FastAPI(
    title="Account Service",
    description="Dịch vụ quản lý tài khoản iBanking",
    version="0.1.0",
)

app.include_router(router)
app.include_router(internal_router)

@app.get("/health")
def health():
    return {
        "service": "account-service",
        "status": "ok",
    }


@app.get("/health/db")
def database_health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "database": "account_db",
            "status": "connected",
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Không kết nối được SQL Server",
        ) from None

FRONTEND_DIR = (
    Path(__file__).resolve().parent.parent / "Front-end"
)

app.mount(
    "/ui",
    StaticFiles(directory=str(FRONTEND_DIR), html=True),
    name="ui",
)