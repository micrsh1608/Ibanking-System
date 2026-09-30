from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.otp import router as otp_router
from app.api.tuition import router as tuition_router
from app.core.config import settings
from app.db.database import Base, engine
from app.models import OTP, Student, Tuition  # noqa: F401


Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="TV2 - Tra cuu hoc phi va OTP cho phan he thanh toan hoc phi iBanking.",
)

app.include_router(tuition_router)
app.include_router(otp_router)

static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/demo", StaticFiles(directory=static_dir, html=True), name="demo")


@app.get("/")
def root():
    return {
        "service": "TV2 - Tuition & OTP Service",
        "status": "running",
        "docs": "/docs",
        "demo": "/demo/index.html",
    }


@app.get("/health")
def health():
    return {"status": "UP"}
