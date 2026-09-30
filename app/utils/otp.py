import secrets
import string


def generate_otp(length: int = 6) -> str:
    digits = string.digits
    return "".join(secrets.choice(digits) for _ in range(length))
