"""Compatibility entry point. Prefer services.payment.main:app for new commands."""
from services.payment.main import app

__all__ = ["app"]
