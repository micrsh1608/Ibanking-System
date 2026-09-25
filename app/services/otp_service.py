import secrets
import hashlib
from datetime import datetime, timedelta, timezone

def generate_otp():
    """Generate a 6-digit OTP."""
    return f"{secrets.randbelow(1_000_000):06d}"

def hash_otp(otp:str) -> str:
    """Hash OTP before stroring it."""
    return hashlib.sha256(otp.encode()).hexdigest()

def get_otp_expiry():
    """OTP expires after 5 minutes."""
    return datetime.now(timezone.utc) + timedelta(minutes=5)