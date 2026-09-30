import os

os.environ["DATABASE_URL"] = "sqlite:///./test_tuition.db"

import pytest
from fastapi.testclient import TestClient

from app.db.database import Base, engine
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)
