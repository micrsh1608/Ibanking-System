from datetime import datetime, timezone


def utcnow() -> datetime:
    """SQL Server DATETIME stores UTC without an offset; APIs serialize it as UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
