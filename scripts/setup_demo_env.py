"""Create Docker-only demo credentials without replacing an existing file."""
import secrets
from pathlib import Path


def main():
    target = Path(__file__).resolve().parents[1] / "infra" / "env" / "docker.env"
    try:
        with target.open("x", encoding="utf-8", newline="\n") as config:
            config.write(
                "# Local Docker demo only; keep this file private.\n"
                f"MSSQL_SA_PASSWORD=Demo_A1!{secrets.token_hex(20)}\n"
                f"JWT_SECRET_KEY={secrets.token_urlsafe(48)}\n"
                f"INTERNAL_API_KEY={secrets.token_urlsafe(48)}\n"
            )
    except FileExistsError:
        raise SystemExit("infra/env/docker.env already exists; kept unchanged.") from None
    print("Created infra/env/docker.env. No credentials were printed.")


if __name__ == "__main__":
    main()
