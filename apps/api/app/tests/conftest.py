import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.core.db as db_module
from app.core.db import Base
from app.main import app


@pytest.fixture()
def client(monkeypatch):
    """SQLite-backed TestClient for fast unit/integration tests of business
    logic. Row Level Security (architecture 01 §1) is Postgres-only and is
    verified separately against real Postgres — see architecture/09 §2 and
    STATUS.md for how to run those once docker-compose is available."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(db_module, "SessionLocal", TestingSessionLocal)

    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[db_module.get_db] = override_get_db

    class FakeRedis:
        def __init__(self):
            self.store = {}

        def set(self, key, value, ex=None):
            self.store[key] = value

        def get(self, key):
            return self.store.get(key)

        def expire(self, key, ttl):
            pass

    import app.auth.router as auth_router_module
    import app.core.tenancy as tenancy_module

    fake_redis = FakeRedis()
    monkeypatch.setattr(tenancy_module, "redis_client", fake_redis)
    monkeypatch.setattr(auth_router_module, "redis_client", fake_redis)

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
