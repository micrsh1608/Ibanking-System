"""SQL Server connection settings for Windows development and Linux containers."""
import os

from sqlalchemy import URL

from shared.config import PROJECT_ROOT  # Load .env before reading settings.


def _odbc_value(value: str) -> str:
    return "{" + value.replace("}", "}}") + "}"


def sqlserver_url(database: str, *, credential_prefix: str = "DB") -> URL:
    username = os.getenv(f"{credential_prefix}_USER") or os.getenv("DB_USER")
    password = os.getenv(f"{credential_prefix}_PASSWORD") or os.getenv("DB_PASSWORD")
    parts = [
        "DRIVER=" + _odbc_value(os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")),
        "SERVER=" + _odbc_value(os.environ["DB_SERVER"]),
        "DATABASE=" + _odbc_value(database),
        "Encrypt=yes",
        "TrustServerCertificate=" + os.getenv("DB_TRUST_SERVER_CERTIFICATE", "yes"),
    ]
    if username:
        if not password:
            raise ValueError(f"{credential_prefix}_PASSWORD (or DB_PASSWORD) is required")
        parts.extend(["UID=" + _odbc_value(username), "PWD=" + _odbc_value(password)])
    else:
        parts.append("Trusted_Connection=yes")
    return URL.create("mssql+pyodbc", query={"odbc_connect": ";".join(parts) + ";"})
