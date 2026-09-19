import os
import sys
from pathlib import Path

# Set test-only env defaults before importing app.main (which tries to create_app on import)
# Use SQLite in-memory database for the module-level app creation (never actually used in tests)
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("API_KEY", "test-key-placeholder")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

# Add project root to Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.models import Base  # noqa: E402


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as container:
        yield container


@pytest.fixture
def database_url(postgres_container):
    url = postgres_container.get_connection_url()
    engine = create_engine(url, future=True)
    Base.metadata.drop_all(engine)
    engine.dispose()
    return url


@pytest.fixture
def pg_engine(postgres_container):
    engine = create_engine(postgres_container.get_connection_url(), future=True)
    Base.metadata.drop_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(pg_engine):
    Base.metadata.create_all(pg_engine)
    SessionLocal = sessionmaker(bind=pg_engine, future=True)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def api_client(database_url):
    from app.config import Settings  # noqa: E402
    from app.main import create_app  # noqa: E402

    settings = Settings(database_url=database_url, api_key="test-key")
    app = create_app(settings)
    client = TestClient(app)
    client.headers.update({"X-API-Key": "test-key"})
    return client
