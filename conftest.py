"""Shared fixtures: a fresh SQLite database per test, a TestClient, and user helpers."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.auth import create_user as _create_user
from core.db import Base, get_db
from main import app

TEST_PASSWORD = "test-password"


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False)
    engine.dispose()


@pytest.fixture
def db(session_factory):
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def client(session_factory):
    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app, follow_redirects=False)
    app.dependency_overrides.clear()


@pytest.fixture
def create_user(db):
    """create_user("name", ["role", ...]) -> User, committed, password TEST_PASSWORD."""

    def _create(username, roles=()):
        user = _create_user(db, username, TEST_PASSWORD, list(roles))
        db.commit()
        return user

    return _create


@pytest.fixture
def login_as(client, create_user):
    """login_as("name", ["role", ...]) -> User; creates the user and logs the client in."""

    def _login(username, roles=()):
        user = create_user(username, roles)
        response = client.post("/login", data={"username": username, "password": TEST_PASSWORD})
        assert response.status_code == 303, response.text
        return user

    return _login
