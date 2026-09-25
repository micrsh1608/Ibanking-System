from fastapi import FastAPI

from app.api.payments import router as payment_router

app = FastAPI(
    title="Ibanking System",
    version="1.0.0"
)

app.include_router(payment_router)

@app.get("/")
def root():
    return {
        "message": "Ibanking System is running"
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy"
    }