"""
Ortak test fixture'ları.
SQLite in-memory kullanarak PostgreSQL'e ihtiyaç duymadan tüm testler çalışır.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Models imported here so Base knows about all tables before create_all
import database.models  # noqa: F401

from database.db import Base, get_db
from main import app

TEST_DB_URL = "sqlite:///./test_shared.db"

engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def reset_db():
    """Her test öncesi tabloları sıfırdan oluştur, sonra temizle."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def registered_user(client):
    data = {"email": "user@test.com", "username": "testuser", "password": "pass12345"}
    client.post("/auth/register", json=data)
    return data


@pytest.fixture
def auth_headers(client, registered_user):
    res = client.post("/auth/login", json={
        "email": registered_user["email"],
        "password": registered_user["password"],
    })
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_tokens(client, registered_user):
    res = client.post("/auth/login", json={
        "email": registered_user["email"],
        "password": registered_user["password"],
    })
    return res.json()
