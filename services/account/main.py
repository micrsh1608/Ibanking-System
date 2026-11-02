from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from services.account.routes import router
from services.account.database import engine
from services.account.internal_routes import router as internal_router
from fastapi.staticfiles import StaticFiles
from shared.config import PROJECT_ROOT
from services.account.gateway import router as gateway_router


app = FastAPI(
    title="Account Service",
    description="Dịch vụ quản lý tài khoản iBanking",
    version="0.1.0",
)

app.include_router(router)
app.include_router(internal_router)
app.include_router(gateway_router)

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

FRONTEND_DIR = PROJECT_ROOT / "frontend"

app.mount(
    "/ui",
    StaticFiles(directory=str(FRONTEND_DIR), html=True),
    name="ui",
)
