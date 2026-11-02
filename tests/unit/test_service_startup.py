"""Check entry points and static assets after the repository reorganization."""
from importlib import import_module

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("service", ["account", "payment", "tuition"])
def test_service_health_and_openapi(service):
    app = import_module(f"services.{service}.main").app
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert "/health" in response.json()["paths"]


def test_account_serves_relocated_frontend():
    from services.account.main import app

    with TestClient(app) as client:
        page = client.get("/ui/")
        assert page.status_code == 200
        assert "./app.js" in page.text
        assert "./style.css" in page.text
        assert client.get("/ui/app.js").status_code == 200
        assert client.get("/ui/style.css").status_code == 200
