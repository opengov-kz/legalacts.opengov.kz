# Legalacts Extended Data Model Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat `Document`/`Comment` schema in `backend/db/models.py` with the `LegalAct`-centric schema (snapshots/provenance, normalized lookups, comment channels) designed in the spec below, introduce Alembic, and keep the external API v1 contract byte-identical so the frontend needs no changes.

**Architecture:** New SQLAlchemy models (`LegalAct`, `GovernmentBody`, `ActType`, `Comment` with `comment_channel`, `LegalActSnapshot`) replace `Document`/`Comment`; a single Alembic baseline revision creates the schema (no migration from the old schema — pre-production, disposable data). `scraper/store.py` gets snapshot-on-change logic keyed on SHA-256 + a handful of trigger fields. `app/routers/documents.py` and `app/routers/analytics.py` become a thin adapter over the new schema via SQLAlchemy `association_proxy`, so `app/schemas/*` and the JSON shape stay unchanged.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x, Alembic, FastAPI, pytest + testcontainers (postgres:16-alpine), PostgreSQL 16.

**Spec:** `docs/superpowers/specs/2026-09-22-legalacts-data-model-design.md`

## Global Constraints

- External API v1 contract (`GET /documents`, `/documents/{id}`, `/analytics/summary`, `/analytics/timeseries`, `/crawl/status`) must return the exact same field names/shapes as today — no frontend changes in this plan.
- Content-change detection uses SHA-256 (spec: "Для документов вычислять SHA-256").
- Comment channel default is `6` (the "Комментарий" tab, `typeComment=6`) — this plan does not add scraping of the other 7 tabs, only the column to support it later.
- Internal-clock timestamps (`first_seen_at`, `last_checked_at`, `captured_at`, `discovered_at`, `processed_at`) are `DateTime(timezone=True)` in UTC. Source-provided date/time strings (`created_date`, `discussion_end_date`, `commented_at_raw`) stay as raw strings — source timezone is unconfirmed.
- One Alembic baseline revision creates the new schema directly; no revision reproduces the old flat schema.
- `USER_AGENT` in `backend/scraper/run.py` must stay ASCII/Latin-1 encodable (existing constraint, unaffected but touched by this plan — do not break `test_user_agent_is_latin1_encodable`).
- Deliberate deviation from the spec's literal wording: the spec's comments-table description says `first_seen_at` is unchanged, but that field is the same class of internal-clock timestamp as `LegalAct.first_seen_at` and `CrawlQueueEntry.discovered_at`/`processed_at`. This plan converts `Comment.first_seen_at` to `DateTime(timezone=True)` too, for consistency with the rest of the internal-clock fields — leaving it as the only remaining string would be an arbitrary inconsistency the spec missed.

---

### Task 1: New schema + Alembic baseline migration

**Files:**
- Modify: `backend/db/models.py`
- Modify: `backend/db/session.py`
- Modify: `backend/requirements.txt`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/0001_baseline_schema.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_db.py`
- Modify: `backend/app/schemas/crawl.py`
- Modify: `backend/tests/test_crawl_router.py`
- Test: `backend/tests/test_db.py`, `backend/tests/test_crawl_router.py`

**Interfaces:**
- Produces: ORM classes `GovernmentBody(id, name)`, `ActType(id, name)`, `LegalAct(id, external_id, section, url, title_ru, title_kk, status, act_type_id, government_body_id, created_date, discussion_end_date, comments_total, likes_count, dislikes_count, content_sha256_ru, content_sha256_kk, first_seen_at, last_checked_at)` with association proxies `LegalAct.doc_type`/`LegalAct.government_body` (str, read from the joined lookup row's `.name`), `Comment(id, legal_act_id, external_comment_id, parent_external_comment_id, comment_channel, author_name, body, article_ref, status, commented_at_raw, first_seen_at)`, `LegalActSnapshot(id, legal_act_id, captured_at, raw_html_ru, raw_html_kk, content_sha256_ru, content_sha256_kk, title_ru, title_kk, status, act_type_id, government_body_id, created_date, discussion_end_date, comments_total, likes_count, dislikes_count)`, `CrawlQueueEntry` (unchanged columns, `discovered_at`/`processed_at` now `DateTime(timezone=True)`). Pytest fixtures `postgres_container` (session-scoped), `database_url`/`pg_engine`/`db_session`/`api_client` (function-scoped, schema reset + `alembic upgrade head` applied before every test).

- [ ] **Step 1: Write the new `backend/db/models.py`**

```python
from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class GovernmentBody(Base):
    __tablename__ = "government_bodies"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)


class ActType(Base):
    __tablename__ = "act_types"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)


class LegalAct(Base):
    __tablename__ = "legal_acts"

    id = Column(Integer, primary_key=True)
    external_id = Column(Integer, nullable=False, unique=True)
    section = Column(String, nullable=False)
    url = Column(String, nullable=False)
    title_ru = Column(String)
    title_kk = Column(String)
    status = Column(String)
    act_type_id = Column(Integer, ForeignKey("act_types.id"))
    government_body_id = Column(Integer, ForeignKey("government_bodies.id"))
    created_date = Column(String)
    discussion_end_date = Column(String)
    comments_total = Column(Integer)
    likes_count = Column(Integer)
    dislikes_count = Column(Integer)
    content_sha256_ru = Column(String(64))
    content_sha256_kk = Column(String(64))
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_checked_at = Column(DateTime(timezone=True), nullable=False)

    act_type_ref = relationship("ActType")
    government_body_ref = relationship("GovernmentBody")
    doc_type = association_proxy("act_type_ref", "name")
    government_body = association_proxy("government_body_ref", "name")

    comments = relationship("Comment", back_populates="legal_act", order_by="Comment.id")
    snapshots = relationship(
        "LegalActSnapshot", back_populates="legal_act", order_by="LegalActSnapshot.captured_at"
    )


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        UniqueConstraint(
            "legal_act_id", "external_comment_id", "comment_channel",
            name="uq_comment_legal_act_external_id_channel",
        ),
    )

    id = Column(Integer, primary_key=True)
    legal_act_id = Column(Integer, ForeignKey("legal_acts.id"), nullable=False)
    external_comment_id = Column(Integer, nullable=False)
    parent_external_comment_id = Column(Integer)
    comment_channel = Column(Integer, nullable=False, default=6)
    author_name = Column(String)
    body = Column(Text, nullable=False)
    article_ref = Column(String)
    status = Column(String)
    commented_at_raw = Column(String)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)

    legal_act = relationship("LegalAct", back_populates="comments")


class LegalActSnapshot(Base):
    __tablename__ = "legal_act_snapshots"
    __table_args__ = (
        Index("ix_legal_act_snapshots_legal_act_id_captured_at", "legal_act_id", "captured_at"),
    )

    id = Column(Integer, primary_key=True)
    legal_act_id = Column(Integer, ForeignKey("legal_acts.id"), nullable=False)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    raw_html_ru = Column(Text)
    raw_html_kk = Column(Text)
    content_sha256_ru = Column(String(64))
    content_sha256_kk = Column(String(64))
    title_ru = Column(String)
    title_kk = Column(String)
    status = Column(String)
    act_type_id = Column(Integer, ForeignKey("act_types.id"))
    government_body_id = Column(Integer, ForeignKey("government_bodies.id"))
    created_date = Column(String)
    discussion_end_date = Column(String)
    comments_total = Column(Integer)
    likes_count = Column(Integer)
    dislikes_count = Column(Integer)

    legal_act = relationship("LegalAct", back_populates="snapshots")


class CrawlQueueEntry(Base):
    __tablename__ = "crawl_queue"

    url = Column(String, primary_key=True)
    page_type = Column(String, nullable=False)
    section = Column(String)
    status = Column(String, nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text)
    discovered_at = Column(DateTime(timezone=True), nullable=False)
    processed_at = Column(DateTime(timezone=True))
```

- [ ] **Step 2: Update `backend/db/session.py` to stop auto-creating the schema**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def create_engine_and_session_factory(database_url):
    engine = create_engine(database_url, future=True)
    session_factory = sessionmaker(bind=engine, future=True)
    return engine, session_factory
```

- [ ] **Step 3: Add Alembic to `backend/requirements.txt`**

Insert `alembic>=1.13,<2` on its own line, directly after the `sqlalchemy>=2.0,<3` line, so the file reads:

```text
requests>=2.31,<3
beautifulsoup4>=4.12,<5
lxml>=4.9,<6
pytest>=7.4,<8
sqlalchemy>=2.0,<3
alembic>=1.13,<2
psycopg2-binary>=2.9,<3
fastapi>=0.115,<1
uvicorn[standard]>=0.30,<1
pydantic-settings>=2.4,<3
testcontainers[postgres]>=4.7,<5
httpx>=0.27,<1
```

Run: `cd backend && .venv/Scripts/pip install -r requirements.txt` (Linux/macOS: `.venv/bin/pip install -r requirements.txt`)
Expected: `alembic` installs without errors.

- [ ] **Step 4: Create `backend/alembic.ini`**

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 5: Create `backend/alembic/env.py`**

```python
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url():
    return os.environ.get("DATABASE_URL") or config.get_main_option("sqlalchemy.url")


def run_migrations_offline():
    url = get_url()
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 6: Create `backend/alembic/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade():
    ${upgrades if upgrades else "pass"}


def downgrade():
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 7: Create `backend/alembic/versions/0001_baseline_schema.py`**

```python
"""baseline schema: government_bodies, act_types, legal_acts, comments, legal_act_snapshots, crawl_queue

Revision ID: 0001
Revises:
Create Date: 2026-09-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "government_bodies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.UniqueConstraint("name", name="uq_government_bodies_name"),
    )
    op.create_table(
        "act_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.UniqueConstraint("name", name="uq_act_types_name"),
    )
    op.create_table(
        "legal_acts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("title_ru", sa.String()),
        sa.Column("title_kk", sa.String()),
        sa.Column("status", sa.String()),
        sa.Column("act_type_id", sa.Integer(), sa.ForeignKey("act_types.id")),
        sa.Column("government_body_id", sa.Integer(), sa.ForeignKey("government_bodies.id")),
        sa.Column("created_date", sa.String()),
        sa.Column("discussion_end_date", sa.String()),
        sa.Column("comments_total", sa.Integer()),
        sa.Column("likes_count", sa.Integer()),
        sa.Column("dislikes_count", sa.Integer()),
        sa.Column("content_sha256_ru", sa.String(length=64)),
        sa.Column("content_sha256_kk", sa.String(length=64)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("external_id", name="uq_legal_acts_external_id"),
    )
    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legal_act_id", sa.Integer(), sa.ForeignKey("legal_acts.id"), nullable=False),
        sa.Column("external_comment_id", sa.Integer(), nullable=False),
        sa.Column("parent_external_comment_id", sa.Integer()),
        sa.Column("comment_channel", sa.Integer(), nullable=False, server_default="6"),
        sa.Column("author_name", sa.String()),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("article_ref", sa.String()),
        sa.Column("status", sa.String()),
        sa.Column("commented_at_raw", sa.String()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "legal_act_id", "external_comment_id", "comment_channel",
            name="uq_comment_legal_act_external_id_channel",
        ),
    )
    op.create_table(
        "legal_act_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legal_act_id", sa.Integer(), sa.ForeignKey("legal_acts.id"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_html_ru", sa.Text()),
        sa.Column("raw_html_kk", sa.Text()),
        sa.Column("content_sha256_ru", sa.String(length=64)),
        sa.Column("content_sha256_kk", sa.String(length=64)),
        sa.Column("title_ru", sa.String()),
        sa.Column("title_kk", sa.String()),
        sa.Column("status", sa.String()),
        sa.Column("act_type_id", sa.Integer(), sa.ForeignKey("act_types.id")),
        sa.Column("government_body_id", sa.Integer(), sa.ForeignKey("government_bodies.id")),
        sa.Column("created_date", sa.String()),
        sa.Column("discussion_end_date", sa.String()),
        sa.Column("comments_total", sa.Integer()),
        sa.Column("likes_count", sa.Integer()),
        sa.Column("dislikes_count", sa.Integer()),
    )
    op.create_index(
        "ix_legal_act_snapshots_legal_act_id_captured_at",
        "legal_act_snapshots", ["legal_act_id", "captured_at"],
    )
    op.create_table(
        "crawl_queue",
        sa.Column("url", sa.String(), primary_key=True),
        sa.Column("page_type", sa.String(), nullable=False),
        sa.Column("section", sa.String()),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )


def downgrade():
    op.drop_table("crawl_queue")
    op.drop_index("ix_legal_act_snapshots_legal_act_id_captured_at", table_name="legal_act_snapshots")
    op.drop_table("legal_act_snapshots")
    op.drop_table("comments")
    op.drop_table("legal_acts")
    op.drop_table("act_types")
    op.drop_table("government_bodies")
```

- [ ] **Step 8: Rewrite `backend/tests/conftest.py` to migrate instead of `create_all`**

```python
import os
import sys
from pathlib import Path

# Set test-only env defaults before importing app.main (which tries to create_app on import)
# Use SQLite in-memory database for the module-level app creation (never actually used in tests)
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("API_KEY", "test-key-placeholder")

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

# Add project root to Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

ALEMBIC_INI = project_root / "alembic.ini"


def _reset_schema(url):
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def _run_migrations(url):
    os.environ["DATABASE_URL"] = url
    cfg = Config(str(ALEMBIC_INI))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as container:
        yield container


@pytest.fixture
def database_url(postgres_container):
    url = postgres_container.get_connection_url()
    _reset_schema(url)
    _run_migrations(url)
    return url


@pytest.fixture
def pg_engine(database_url):
    engine = create_engine(database_url, future=True)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(pg_engine):
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
```

- [ ] **Step 9: Rewrite `backend/tests/test_db.py`**

```python
from sqlalchemy import inspect


def test_migration_creates_expected_tables(pg_engine):
    tables = set(inspect(pg_engine).get_table_names())
    assert {
        "legal_acts", "comments", "crawl_queue",
        "government_bodies", "act_types", "legal_act_snapshots",
    }.issubset(tables)


def test_legal_acts_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("legal_acts")}
    assert columns == {
        "id", "external_id", "section", "url", "title_ru", "title_kk", "status",
        "act_type_id", "government_body_id", "created_date", "discussion_end_date",
        "comments_total", "likes_count", "dislikes_count",
        "content_sha256_ru", "content_sha256_kk", "first_seen_at", "last_checked_at",
    }


def test_comments_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("comments")}
    assert columns == {
        "id", "legal_act_id", "external_comment_id", "parent_external_comment_id",
        "comment_channel", "author_name", "body", "article_ref", "status",
        "commented_at_raw", "first_seen_at",
    }


def test_legal_act_snapshots_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("legal_act_snapshots")}
    assert columns == {
        "id", "legal_act_id", "captured_at", "raw_html_ru", "raw_html_kk",
        "content_sha256_ru", "content_sha256_kk", "title_ru", "title_kk", "status",
        "act_type_id", "government_body_id", "created_date", "discussion_end_date",
        "comments_total", "likes_count", "dislikes_count",
    }


def test_crawl_queue_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("crawl_queue")}
    assert columns == {
        "url", "page_type", "section", "status", "attempts", "last_error",
        "discovered_at", "processed_at",
    }


def test_government_bodies_and_act_types_tables_have_expected_columns(db_session):
    gb_columns = {col["name"] for col in inspect(db_session.bind).get_columns("government_bodies")}
    at_columns = {col["name"] for col in inspect(db_session.bind).get_columns("act_types")}
    assert gb_columns == {"id", "name"}
    assert at_columns == {"id", "name"}
```

- [ ] **Step 10: Update `backend/app/schemas/crawl.py` for the new `CrawlQueueEntry` timestamp types**

```python
import datetime
from typing import Optional

from pydantic import BaseModel


class CrawlStatusCountOut(BaseModel):
    page_type: str
    status: str
    count: int


class CrawlErrorOut(BaseModel):
    url: str
    page_type: str
    last_error: Optional[str] = None
    processed_at: Optional[datetime.datetime] = None


class CrawlStatusOut(BaseModel):
    counts: list[CrawlStatusCountOut]
    last_processed_at: Optional[datetime.datetime] = None
    recent_errors: list[CrawlErrorOut]
```

`backend/app/routers/crawl.py` needs no code change — field names are identical, only the underlying Python type flowing through changed from `str` to `datetime.datetime` (Pydantic still serializes it to the same ISO-8601 JSON string).

- [ ] **Step 11: Rewrite `backend/tests/test_crawl_router.py` to seed with `datetime` values**

```python
import datetime

from db.models import CrawlQueueEntry
from db.session import create_engine_and_session_factory

UTC = datetime.timezone.utc


def _seed(database_url, entries):
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    for entry in entries:
        session.add(CrawlQueueEntry(**entry))
    session.commit()
    session.close()


def test_crawl_status_reports_counts_by_page_type_and_status(database_url, api_client):
    _seed(database_url, [
        dict(url="u1", page_type="document", status="done",
             discovered_at=datetime.datetime(2026, 9, 1, tzinfo=UTC),
             processed_at=datetime.datetime(2026, 9, 1, 1, tzinfo=UTC)),
        dict(url="u2", page_type="document", status="pending",
             discovered_at=datetime.datetime(2026, 9, 1, tzinfo=UTC)),
        dict(url="u3", page_type="list", status="error", last_error="timeout",
             discovered_at=datetime.datetime(2026, 9, 1, tzinfo=UTC),
             processed_at=datetime.datetime(2026, 9, 1, 2, tzinfo=UTC)),
    ])

    response = api_client.get("/crawl/status")

    assert response.status_code == 200
    body = response.json()
    counts = {(row["page_type"], row["status"]): row["count"] for row in body["counts"]}
    assert counts == {
        ("document", "done"): 1,
        ("document", "pending"): 1,
        ("list", "error"): 1,
    }
    assert body["last_processed_at"] == "2026-09-01T02:00:00+00:00"
    assert len(body["recent_errors"]) == 1
    assert body["recent_errors"][0]["last_error"] == "timeout"


def test_crawl_status_requires_api_key(database_url):
    from app.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(Settings(database_url=database_url, api_key="expected-key"))
    client = TestClient(app)

    assert client.get("/crawl/status").status_code in (401, 422)
```

- [ ] **Step 12: Run the full backend suite**

Run: `cd backend && .venv/Scripts/pytest tests/test_db.py tests/test_crawl_router.py -v`
Expected: all tests PASS. (Other test files still reference the old `Document`/`upsert_document` API at this point and will fail — that's expected; they're fixed in later tasks. Do not run the full suite yet.)

- [ ] **Step 13: Commit**

```bash
git add backend/db/models.py backend/db/session.py backend/requirements.txt \
  backend/alembic.ini backend/alembic/env.py backend/alembic/script.py.mako \
  backend/alembic/versions/0001_baseline_schema.py backend/tests/conftest.py \
  backend/tests/test_db.py backend/app/schemas/crawl.py backend/tests/test_crawl_router.py
git commit -m "feat: replace flat schema with LegalAct/snapshot model, add Alembic"
```

---

### Task 2: Storage layer — `upsert_legal_act` with snapshots, `upsert_comments` with channel

**Files:**
- Modify: `backend/scraper/store.py`
- Test: `backend/tests/test_store.py`

**Interfaces:**
- Consumes: `db.models.{LegalAct, Comment, LegalActSnapshot, GovernmentBody, ActType}` from Task 1.
- Produces: `store.upsert_legal_act(session, external_id, section, url, fields, now) -> int` (returns `legal_act.id`; `fields` is the same dict shape the parsers already produce, keyed `title_ru`/`title_kk`/`status`/`doc_type`/`government_body`/`created_date`/`discussion_end_date`/`comments_total`/`likes_count`/`dislikes_count`/`raw_html_ru`/`raw_html_kk`; `now` is a `datetime.datetime`), `store.upsert_comments(session, legal_act_id, comments, comment_channel, now)`. Both are consumed by Task 3 (`scraper/run.py`).

- [ ] **Step 1: Write the failing tests in `backend/tests/test_store.py`**

```python
import datetime
import hashlib

from scraper import store

UTC = datetime.timezone.utc
T1 = datetime.datetime(2026, 9, 1, tzinfo=UTC)
T2 = datetime.datetime(2026, 9, 15, tzinfo=UTC)


def _fields(**overrides):
    base = dict(
        title_ru="Title_RU_001", title_kk="Title_KK_001",
        status="Status_Value_001", doc_type="DocType_Value_001",
        government_body="Body_Value_001", created_date="2026-01-01",
        discussion_end_date="2026-12-31", comments_total=42,
        likes_count=99, dislikes_count=88,
        raw_html_ru="<html>content_ru_001</html>",
        raw_html_kk="<html>content_kk_001</html>",
    )
    base.update(overrides)
    return base


def test_upsert_legal_act_inserts_new_row_and_creates_snapshot(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 15906353, "npa_section_001",
        "https://legalacts.test/npa/view?id=15906353", _fields(), T1,
    )

    from db.models import ActType, GovernmentBody, LegalAct, LegalActSnapshot
    row = db_session.get(LegalAct, legal_act_id)

    assert row.external_id == 15906353
    assert row.section == "npa_section_001"
    assert row.url == "https://legalacts.test/npa/view?id=15906353"
    assert row.title_ru == "Title_RU_001"
    assert row.title_kk == "Title_KK_001"
    assert row.status == "Status_Value_001"
    assert row.doc_type == "DocType_Value_001"
    assert row.government_body == "Body_Value_001"
    assert row.created_date == "2026-01-01"
    assert row.discussion_end_date == "2026-12-31"
    assert row.comments_total == 42
    assert row.likes_count == 99
    assert row.dislikes_count == 88
    assert row.first_seen_at == T1
    assert row.last_checked_at == T1

    government_body = db_session.query(GovernmentBody).filter_by(name="Body_Value_001").one()
    act_type = db_session.query(ActType).filter_by(name="DocType_Value_001").one()
    assert row.government_body_id == government_body.id
    assert row.act_type_id == act_type.id

    snapshots = db_session.query(LegalActSnapshot).filter_by(legal_act_id=legal_act_id).all()
    assert len(snapshots) == 1
    assert snapshots[0].raw_html_ru == "<html>content_ru_001</html>"
    assert snapshots[0].raw_html_kk == "<html>content_kk_001</html>"
    assert snapshots[0].content_sha256_ru == hashlib.sha256(
        "<html>content_ru_001</html>".encode("utf-8")
    ).hexdigest()
    assert snapshots[0].captured_at == T1


def test_upsert_legal_act_updates_existing_and_preserves_first_seen_at(db_session):
    store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(title_ru="V1"), T1)
    store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(title_ru="V2"), T2)

    from db.models import LegalAct
    row = db_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 1)
    ).fetchone()
    assert row.title_ru == "V2"
    assert row.first_seen_at == T1
    assert row.last_checked_at == T2


def test_upsert_legal_act_keeps_kk_fields_when_not_provided(db_session):
    store.upsert_legal_act(
        db_session, 1, "npa", "url1",
        _fields(title_ru="V1", title_kk="KK1", raw_html_kk="<html>kk1</html>"), T1,
    )
    fields_v2 = _fields(title_ru="V2")
    fields_v2.pop("title_kk")
    fields_v2.pop("raw_html_kk")
    store.upsert_legal_act(db_session, 1, "npa", "url1", fields_v2, T2)

    from db.models import LegalAct, LegalActSnapshot
    row = db_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 1)
    ).fetchone()
    assert row.title_kk == "KK1"

    latest_snapshot = db_session.execute(
        LegalActSnapshot.__table__.select()
        .where(LegalActSnapshot.legal_act_id == row.id)
        .order_by(LegalActSnapshot.captured_at.desc())
        .limit(1)
    ).fetchone()
    assert latest_snapshot.raw_html_kk == "<html>kk1</html>"


def test_upsert_legal_act_reuses_existing_lookup_rows_for_same_name(db_session):
    store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    store.upsert_legal_act(db_session, 2, "npa", "url2", _fields(), T1)

    from db.models import ActType, GovernmentBody
    assert db_session.query(GovernmentBody).filter_by(name="Body_Value_001").count() == 1
    assert db_session.query(ActType).filter_by(name="DocType_Value_001").count() == 1


def test_upsert_legal_act_does_not_create_new_snapshot_when_nothing_changed(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T2)

    from db.models import LegalActSnapshot
    snapshots = db_session.query(LegalActSnapshot).filter_by(legal_act_id=legal_act_id).all()
    assert len(snapshots) == 1


def test_upsert_legal_act_creates_new_snapshot_when_status_changes(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(status="A"), T1)
    store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(status="B"), T2)

    from db.models import LegalActSnapshot
    snapshots = (
        db_session.query(LegalActSnapshot)
        .filter_by(legal_act_id=legal_act_id)
        .order_by(LegalActSnapshot.captured_at)
        .all()
    )
    assert [s.status for s in snapshots] == ["A", "B"]
    assert [s.captured_at for s in snapshots] == [T1, T2]


def test_upsert_comments_inserts_and_preserves_first_seen_at_on_update(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    comment = {
        "external_id": 100, "parent_external_id": None, "author_name": "A",
        "body": "text", "article_ref": None, "status": "rejected",
        "commented_at_raw": "10/09 - 11:05",
    }
    store.upsert_comments(db_session, legal_act_id, [comment], 6, T1)

    updated_comment = dict(comment, status="accepted")
    store.upsert_comments(db_session, legal_act_id, [updated_comment], 6, T2)

    from db.models import Comment
    row = db_session.execute(
        Comment.__table__.select().where(
            Comment.legal_act_id == legal_act_id, Comment.external_comment_id == 100,
            Comment.comment_channel == 6,
        )
    ).fetchone()
    assert row.status == "accepted"
    assert row.first_seen_at == T1


def test_upsert_comments_skips_comment_with_none_external_id(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    comments = [
        {"external_id": 100, "parent_external_id": None, "author_name": "A",
         "body": "text A", "article_ref": None, "status": "accepted",
         "commented_at_raw": "10/09 - 11:05"},
        {"external_id": None, "parent_external_id": None, "author_name": "B",
         "body": "text with no id", "article_ref": None, "status": None,
         "commented_at_raw": None},
        {"external_id": 101, "parent_external_id": None, "author_name": "C",
         "body": "text C", "article_ref": None, "status": "rejected",
         "commented_at_raw": "11/09 - 12:00"},
    ]

    store.upsert_comments(db_session, legal_act_id, comments, 6, T1)

    from db.models import Comment
    rows = db_session.execute(
        Comment.__table__.select()
        .where(Comment.legal_act_id == legal_act_id)
        .order_by(Comment.external_comment_id)
    ).fetchall()
    assert [row.external_comment_id for row in rows] == [100, 101]


def test_upsert_comments_same_external_id_different_channel_creates_separate_rows(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    comment = {
        "external_id": 100, "parent_external_id": None, "author_name": "A",
        "body": "public comment", "article_ref": None, "status": None,
        "commented_at_raw": "10/09 - 11:05",
    }
    expert_comment = dict(comment, body="expert comment")

    store.upsert_comments(db_session, legal_act_id, [comment], 6, T1)
    store.upsert_comments(db_session, legal_act_id, [expert_comment], 8, T1)

    from db.models import Comment
    rows = db_session.execute(
        Comment.__table__.select()
        .where(Comment.legal_act_id == legal_act_id, Comment.external_comment_id == 100)
        .order_by(Comment.comment_channel)
    ).fetchall()
    assert [(r.comment_channel, r.body) for r in rows] == [(6, "public comment"), (8, "expert comment")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/pytest tests/test_store.py -v`
Expected: FAIL — `store.upsert_legal_act` does not exist yet (old `store.py` only has `upsert_document`).

- [ ] **Step 3: Rewrite `backend/scraper/store.py`**

```python
import hashlib

from sqlalchemy import select

from db.models import ActType, Comment, GovernmentBody, LegalAct, LegalActSnapshot

SNAPSHOT_TRIGGER_FIELDS = (
    "status", "discussion_end_date", "comments_total", "likes_count",
    "dislikes_count", "content_sha256_ru", "content_sha256_kk",
)


def _sha256(text):
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _get_or_create(session, model, name):
    if not name:
        return None
    existing = session.execute(select(model).where(model.name == name)).scalar_one_or_none()
    if existing is not None:
        return existing
    obj = model(name=name)
    session.add(obj)
    session.flush()
    return obj


def upsert_legal_act(session, external_id, section, url, fields, now):
    existing = session.execute(
        select(LegalAct).where(LegalAct.external_id == external_id)
    ).scalar_one_or_none()

    previous_snapshot = None
    if existing is not None:
        previous_snapshot = session.execute(
            select(LegalActSnapshot)
            .where(LegalActSnapshot.legal_act_id == existing.id)
            .order_by(LegalActSnapshot.captured_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    title_kk = fields.get("title_kk") or (existing.title_kk if existing else None)
    raw_html_ru = fields.get("raw_html_ru")
    raw_html_kk = fields.get("raw_html_kk") or (
        previous_snapshot.raw_html_kk if previous_snapshot else None
    )

    government_body = _get_or_create(session, GovernmentBody, fields.get("government_body"))
    act_type = _get_or_create(session, ActType, fields.get("doc_type"))

    content_sha256_ru = _sha256(raw_html_ru)
    content_sha256_kk = _sha256(raw_html_kk)

    values = {
        "section": section,
        "url": url,
        "title_ru": fields.get("title_ru"),
        "title_kk": title_kk,
        "status": fields.get("status"),
        "act_type_id": act_type.id if act_type else None,
        "government_body_id": government_body.id if government_body else None,
        "created_date": fields.get("created_date"),
        "discussion_end_date": fields.get("discussion_end_date"),
        "comments_total": fields.get("comments_total"),
        "likes_count": fields.get("likes_count"),
        "dislikes_count": fields.get("dislikes_count"),
        "content_sha256_ru": content_sha256_ru,
        "content_sha256_kk": content_sha256_kk,
    }

    changed = existing is None or any(
        getattr(existing, key) != values[key] for key in SNAPSHOT_TRIGGER_FIELDS
    )

    if existing is None:
        legal_act = LegalAct(external_id=external_id, first_seen_at=now, last_checked_at=now, **values)
        session.add(legal_act)
        session.flush()
    else:
        for key, value in values.items():
            setattr(existing, key, value)
        existing.last_checked_at = now
        legal_act = existing

    if changed:
        session.add(LegalActSnapshot(
            legal_act_id=legal_act.id,
            captured_at=now,
            raw_html_ru=raw_html_ru,
            raw_html_kk=raw_html_kk,
            content_sha256_ru=content_sha256_ru,
            content_sha256_kk=content_sha256_kk,
            title_ru=values["title_ru"],
            title_kk=title_kk,
            status=values["status"],
            act_type_id=values["act_type_id"],
            government_body_id=values["government_body_id"],
            created_date=values["created_date"],
            discussion_end_date=values["discussion_end_date"],
            comments_total=values["comments_total"],
            likes_count=values["likes_count"],
            dislikes_count=values["dislikes_count"],
        ))

    session.commit()
    return legal_act.id


def upsert_comments(session, legal_act_id, comments, comment_channel, now):
    for comment in comments:
        if comment["external_id"] is None:
            continue

        existing = session.execute(
            select(Comment).where(
                Comment.legal_act_id == legal_act_id,
                Comment.external_comment_id == comment["external_id"],
                Comment.comment_channel == comment_channel,
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(Comment(
                legal_act_id=legal_act_id,
                external_comment_id=comment["external_id"],
                parent_external_comment_id=comment["parent_external_id"],
                comment_channel=comment_channel,
                author_name=comment["author_name"],
                body=comment["body"],
                article_ref=comment["article_ref"],
                status=comment["status"],
                commented_at_raw=comment["commented_at_raw"],
                first_seen_at=now,
            ))
        else:
            existing.parent_external_comment_id = comment["parent_external_id"]
            existing.author_name = comment["author_name"]
            existing.body = comment["body"]
            existing.article_ref = comment["article_ref"]
            existing.status = comment["status"]
            existing.commented_at_raw = comment["commented_at_raw"]

    session.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/pytest tests/test_store.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scraper/store.py backend/tests/test_store.py
git commit -m "feat: snapshot-on-change upsert_legal_act, channel-aware upsert_comments"
```

---

### Task 3: Scraper orchestration — `run.py` + `queue` timestamp callers

**Files:**
- Modify: `backend/scraper/run.py`
- Modify: `backend/tests/test_queue.py`
- Modify: `backend/tests/test_run.py`
- Test: `backend/tests/test_queue.py`, `backend/tests/test_run.py`

**Interfaces:**
- Consumes: `store.upsert_legal_act`/`store.upsert_comments` from Task 2; `queue.enqueue`/`mark_done`/`mark_error`/`requeue_stale_documents`/`requeue_stale_lists` from `backend/scraper/queue.py` (unchanged code — only the timestamp *type* passed in changes from `str` to `datetime.datetime`, since the column is now `DateTime(timezone=True)`).
- Produces: `run_module.now() -> datetime.datetime` (replaces `now_iso()`), `run_module.DEFAULT_COMMENT_CHANNEL = 6`, `run_module.process_list_entry`/`process_document_entry`/`run`/`main` (same signatures as before).

`backend/scraper/queue.py` itself needs **no code change** — every function just assigns whatever value it's given to a SQLAlchemy column; only its callers change what type they pass.

- [ ] **Step 1: Write the failing tests — rewrite `backend/tests/test_queue.py`**

```python
import datetime

from scraper import queue

UTC = datetime.timezone.utc


def test_enqueue_then_next_pending_returns_url(db_session):
    queue.enqueue(db_session, "https://example.test/list", "list", datetime.datetime(2026, 9, 15, tzinfo=UTC))
    assert queue.next_pending(db_session, "list") == "https://example.test/list"
    assert queue.next_pending(db_session, "document") is None


def test_enqueue_is_idempotent_for_same_url(db_session):
    queue.enqueue(db_session, "https://example.test/list", "list", datetime.datetime(2026, 9, 15, tzinfo=UTC))
    queue.enqueue(db_session, "https://example.test/list", "list", datetime.datetime(2026, 9, 15, 0, 5, tzinfo=UTC))
    from db.models import CrawlQueueEntry
    count = db_session.query(CrawlQueueEntry).count()
    assert count == 1


def test_mark_done_removes_url_from_pending(db_session):
    queue.enqueue(db_session, "https://example.test/list", "list", datetime.datetime(2026, 9, 15, tzinfo=UTC))
    queue.mark_done(db_session, "https://example.test/list", datetime.datetime(2026, 9, 15, 0, 5, tzinfo=UTC))
    assert queue.next_pending(db_session, "list") is None

    from db.models import CrawlQueueEntry
    row = db_session.get(CrawlQueueEntry, "https://example.test/list")
    assert row.status == "done"
    assert row.processed_at == datetime.datetime(2026, 9, 15, 0, 5, tzinfo=UTC)
    assert row.attempts == 1


def test_mark_error_records_message_and_keeps_out_of_pending(db_session):
    queue.enqueue(db_session, "https://example.test/list", "list", datetime.datetime(2026, 9, 15, tzinfo=UTC))
    queue.mark_error(db_session, "https://example.test/list", "timeout", datetime.datetime(2026, 9, 15, 0, 5, tzinfo=UTC))
    assert queue.next_pending(db_session, "list") is None

    from db.models import CrawlQueueEntry
    row = db_session.get(CrawlQueueEntry, "https://example.test/list")
    assert row.status == "error"
    assert row.last_error == "timeout"


def test_enqueue_stores_section_and_section_for_reads_it_back(db_session):
    queue.enqueue(
        db_session, "https://example.test/npa/view?id=1", "document",
        datetime.datetime(2026, 9, 15, tzinfo=UTC), section="arv",
    )
    assert queue.section_for(db_session, "https://example.test/npa/view?id=1") == "arv"


def test_section_for_returns_none_for_unknown_url(db_session):
    assert queue.section_for(db_session, "https://example.test/missing") is None


def test_requeue_stale_documents_resets_old_done_documents_only(db_session):
    queue.enqueue(db_session, "https://example.test/doc-old", "document", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.enqueue(db_session, "https://example.test/doc-new", "document", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.enqueue(db_session, "https://example.test/list", "list", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.mark_done(db_session, "https://example.test/doc-old", datetime.datetime(2026, 9, 1, tzinfo=UTC))
    queue.mark_done(db_session, "https://example.test/doc-new", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.mark_done(db_session, "https://example.test/list", datetime.datetime(2026, 9, 1, tzinfo=UTC))

    queue.requeue_stale_documents(db_session, datetime.datetime(2026, 9, 10, tzinfo=UTC))

    assert queue.next_pending(db_session, "document") == "https://example.test/doc-old"

    from db.models import CrawlQueueEntry
    assert db_session.get(CrawlQueueEntry, "https://example.test/doc-new").status == "done"
    assert db_session.get(CrawlQueueEntry, "https://example.test/list").status == "done"


def test_requeue_stale_lists_resets_old_done_lists_only(db_session):
    queue.enqueue(db_session, "https://example.test/list-old", "list", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.enqueue(db_session, "https://example.test/list-new", "list", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.enqueue(db_session, "https://example.test/doc", "document", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.mark_done(db_session, "https://example.test/list-old", datetime.datetime(2026, 9, 1, tzinfo=UTC))
    queue.mark_done(db_session, "https://example.test/list-new", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.mark_done(db_session, "https://example.test/doc", datetime.datetime(2026, 9, 1, tzinfo=UTC))

    queue.requeue_stale_lists(db_session, datetime.datetime(2026, 9, 10, tzinfo=UTC))

    assert queue.next_pending(db_session, "list") == "https://example.test/list-old"

    from db.models import CrawlQueueEntry
    assert db_session.get(CrawlQueueEntry, "https://example.test/list-new").status == "done"
    assert db_session.get(CrawlQueueEntry, "https://example.test/doc").status == "done"
```

Run: `cd backend && .venv/Scripts/pytest tests/test_queue.py -v`
Expected: FAIL (passing a `datetime` into columns that Task 1 already migrated to `DateTime(timezone=True)` should actually work at the DB layer already — the point of this step is to confirm the test file itself now matches the Task-1 schema; if it already passes, that's fine, proceed. If Task 1 was not yet applied in your working tree, it will fail loudly on a missing/mismatched column type instead.)

- [ ] **Step 2: Rewrite `backend/scraper/run.py`**

```python
import argparse
import datetime
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from db.session import create_engine_and_session_factory
from scraper import queue, store
from scraper.fetch import Fetcher
from scraper.parsers import comments as comments_parser
from scraper.parsers import document_page, list_page

BASE_URL = "https://legalacts.egov.kz"
USER_AGENT = (
    "legalacts-research-bot/0.1 (personal research project; "
    "contact: k.nefyodov@qbs.kz)"
)
STALE_AFTER_DAYS = 7
DEFAULT_COMMENT_CHANNEL = 6  # вкладка «Комментарий» (typeComment=6)

SEED_LIST_URLS = [
    ("npa", f"{BASE_URL}/list"),
    ("npa", f"{BASE_URL}/list?status=IN_ARCHIVE"),
    ("kdrp", f"{BASE_URL}/list?types[0]=7001&types[1]=7002"),
    ("arv", f"{BASE_URL}/Arvlist"),
    ("arv", f"{BASE_URL}/Arvlist?status=IN_ARCHIVE"),
    ("withdraw", f"{BASE_URL}/application/withdraw"),
]


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def seed_queue(session):
    discovered = now()
    for section, url in SEED_LIST_URLS:
        queue.enqueue(session, url, "list", discovered, section=section)


def _current_page(url):
    query = dict(parse_qsl(urlsplit(url).query))
    return int(query.get("page", 1))


def _set_page_param(url, page):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["page"] = str(page)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def process_list_entry(session, fetcher, url, section="npa"):
    response = fetcher.get(url)
    if response.status_code == 404:
        return
    html = response.text

    discovered = now()
    for card in list_page.parse_list_page(html):
        queue.enqueue(session, card["url"], "document", discovered, section=section)

    total_pages = list_page.parse_total_pages(html)
    current_page = _current_page(url)
    if current_page < total_pages:
        queue.enqueue(
            session, _set_page_param(url, current_page + 1), "list", discovered, section=section
        )


def process_document_entry(session, fetcher, url, section="npa"):
    ru_response = fetcher.get(url)
    if ru_response.status_code == 404:
        return
    ru_html = ru_response.text
    fields = document_page.parse_document_page(ru_html)
    fields["title_ru"] = fields.pop("title")
    fields["raw_html_ru"] = ru_html

    fetcher.set_language("kk", location=url)
    try:
        kk_response = fetcher.get(url)
        kk_html = kk_response.text
        kk_fields = document_page.parse_document_page(kk_html)
        fields["title_kk"] = kk_fields["title"]
        fields["raw_html_kk"] = kk_html
    finally:
        fetcher.set_language("ru", location=url)

    external_id = int(dict(parse_qsl(urlsplit(url).query))["id"])
    parsed_comments = comments_parser.parse_comments(ru_html)

    timestamp = now()
    legal_act_id = store.upsert_legal_act(session, external_id, section, url, fields, timestamp)
    store.upsert_comments(session, legal_act_id, parsed_comments, DEFAULT_COMMENT_CHANNEL, timestamp)


def run(database_url, limit=None):
    engine, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()

    has_pending = (
        queue.next_pending(session, "list") is not None
        or queue.next_pending(session, "document") is not None
    )
    if not has_pending:
        seed_queue(session)

    stale_threshold = now() - datetime.timedelta(days=STALE_AFTER_DAYS)
    queue.requeue_stale_documents(session, stale_threshold)
    queue.requeue_stale_lists(session, stale_threshold)

    fetcher = Fetcher(USER_AGENT)
    fetcher.set_language("ru")
    processed = 0

    while limit is None or processed < limit:
        list_url = queue.next_pending(session, "list")
        if list_url is not None:
            section = queue.section_for(session, list_url) or "npa"
            try:
                process_list_entry(session, fetcher, list_url, section=section)
                queue.mark_done(session, list_url, now())
            except Exception as exc:
                session.rollback()
                queue.mark_error(session, list_url, str(exc), now())
            processed += 1
            continue

        document_url = queue.next_pending(session, "document")
        if document_url is not None:
            section = queue.section_for(session, document_url) or "npa"
            try:
                process_document_entry(session, fetcher, document_url, section=section)
                queue.mark_done(session, document_url, now())
            except Exception as exc:
                session.rollback()
                queue.mark_error(session, document_url, str(exc), now())
            processed += 1
            continue

        break

    session.close()
    engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Обход портала legalacts.egov.kz")
    parser.add_argument("--database-url", default=None, help="Override DATABASE_URL env var")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    database_url = args.database_url or os.environ["DATABASE_URL"]
    run(database_url, limit=args.limit)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run `test_queue.py` to verify it passes**

Run: `cd backend && .venv/Scripts/pytest tests/test_queue.py -v`
Expected: all PASS.

- [ ] **Step 4: Rewrite `backend/tests/test_run.py`**

```python
import datetime
from pathlib import Path
from types import SimpleNamespace

from scraper import queue
from scraper import run as run_module
from db.session import create_engine_and_session_factory

FIXTURES = Path(__file__).parent / "fixtures"
UTC = datetime.timezone.utc


class StubFetcher:
    def __init__(self, pages, status_codes=None):
        self._pages = {url: list(v) if isinstance(v, list) else [v] for url, v in pages.items()}
        self._status_codes = dict(status_codes or {})
        self.calls = []
        self.lang_calls = []
        self.events = []

    def get(self, url):
        self.calls.append(url)
        self.events.append(("get", url))
        remaining = self._pages.get(url)
        html = ""
        if remaining:
            html = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        status_code = self._status_codes.get(url, 200)
        return SimpleNamespace(text=html, status_code=status_code)

    def set_language(self, lang, location="/"):
        self.lang_calls.append(lang)
        self.events.append(("lang", lang))


class FlakyStubFetcher(StubFetcher):
    def __init__(self, pages, fail_urls=()):
        super().__init__(pages)
        self._fail_urls = set(fail_urls)

    def get(self, url):
        if url in self._fail_urls:
            self.calls.append(url)
            raise RuntimeError("simulated network failure")
        return super().get(url)


def test_user_agent_is_latin1_encodable():
    run_module.USER_AGENT.encode("latin-1")


def test_process_list_entry_enqueues_documents_and_next_page(db_session):
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE"
    fetcher = StubFetcher({url: list_html})

    run_module.process_list_entry(db_session, fetcher, url, section="npa")

    assert queue.next_pending(db_session, "document") is not None
    from db.models import CrawlQueueEntry
    doc_urls = db_session.execute(
        CrawlQueueEntry.__table__.select().where(CrawlQueueEntry.page_type == "document")
    ).fetchall()
    assert len(doc_urls) == 5
    assert queue.section_for(db_session, doc_urls[0].url) == "npa"

    page_rows = db_session.execute(
        CrawlQueueEntry.__table__.select().where(CrawlQueueEntry.page_type == "list")
    ).fetchall()
    assert len(page_rows) == 1
    assert "page=2" in page_rows[0].url
    assert "status=IN_ARCHIVE" in page_rows[0].url


def test_process_list_entry_stops_pagination_at_last_page(db_session):
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE&page=29852"
    fetcher = StubFetcher({url: list_html})

    run_module.process_list_entry(db_session, fetcher, url)

    from db.models import CrawlQueueEntry
    page_rows = db_session.execute(
        CrawlQueueEntry.__table__.select().where(CrawlQueueEntry.page_type == "list")
    ).fetchall()
    assert len(page_rows) == 0


def test_process_document_entry_stores_document_and_comments(db_session):
    ru_html = (FIXTURES / "document_with_comments.html").read_text(encoding="utf-8")
    kk_html = (FIXTURES / "document_with_comments_kk.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    fetcher = StubFetcher({url: [ru_html, kk_html]})

    run_module.process_document_entry(db_session, fetcher, url, section="withdraw")

    from db.models import Comment, LegalAct, LegalActSnapshot
    act = db_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 15906353)
    ).fetchone()
    assert act.section == "withdraw"
    assert act.status == "Архив"
    assert act.title_kk.startswith("Қазақстан Республикасы")

    snapshot = db_session.execute(
        LegalActSnapshot.__table__.select().where(LegalActSnapshot.legal_act_id == act.id)
    ).fetchone()
    assert snapshot.raw_html_ru == ru_html
    assert snapshot.raw_html_kk == kk_html

    comment_rows = db_session.execute(
        Comment.__table__.select().where(Comment.legal_act_id == act.id)
    ).fetchall()
    assert len(comment_rows) == 20
    assert all(row.comment_channel == run_module.DEFAULT_COMMENT_CHANNEL for row in comment_rows)
    assert fetcher.lang_calls == ["kk", "ru"]


def test_process_document_entry_404_stores_nothing(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=404404"
    fetcher = StubFetcher({}, status_codes={url: 404})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    from db.models import LegalAct
    assert db_session.execute(LegalAct.__table__.select()).fetchone() is None
    assert fetcher.calls == [url]
    assert fetcher.lang_calls == []


def test_process_list_entry_404_enqueues_nothing(db_session):
    url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE"
    fetcher = StubFetcher({}, status_codes={url: 404})

    run_module.process_list_entry(db_session, fetcher, url, section="npa")

    from db.models import CrawlQueueEntry
    assert db_session.execute(CrawlQueueEntry.__table__.select()).fetchall() == []


def test_run_seeds_queue_and_respects_limit(database_url, monkeypatch):
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    seed_url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE"

    monkeypatch.setattr(run_module, "SEED_LIST_URLS", [("npa", seed_url)])
    fake_fetcher = StubFetcher({seed_url: list_html})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fake_fetcher)

    run_module.run(database_url, limit=1)

    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    from db.models import CrawlQueueEntry
    doc_rows = session.execute(
        CrawlQueueEntry.__table__.select().where(CrawlQueueEntry.page_type == "document")
    ).fetchall()
    assert len(doc_rows) == 5
    assert queue.section_for(session, doc_rows[0].url) == "npa"
    session.close()


def test_run_switches_to_russian_before_first_document_fetch(database_url, monkeypatch):
    ru_html = (FIXTURES / "document_with_comments.html").read_text(encoding="utf-8")
    kk_html = (FIXTURES / "document_with_comments_kk.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/npa/view?id=15906353"

    _, SessionLocal = create_engine_and_session_factory(database_url)
    seed_session = SessionLocal()
    queue.enqueue(seed_session, url, "document", datetime.datetime(2020, 1, 1, tzinfo=UTC), section="npa")
    seed_session.close()

    fetcher = StubFetcher({url: [ru_html, kk_html]})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(database_url, limit=1)

    first_get_index = fetcher.events.index(("get", url))
    assert fetcher.events[:first_get_index] == [("lang", "ru")], (
        "run() must switch the session language to ru before the first document "
        "GET, otherwise a cold session defaults to kk and mislabels the response "
        "as raw_html_ru"
    )


def test_run_marks_broken_entry_as_error_and_continues_processing_others(database_url, monkeypatch):
    ru_html = (FIXTURES / "document_with_comments.html").read_text(encoding="utf-8")
    kk_html = (FIXTURES / "document_with_comments_kk.html").read_text(encoding="utf-8")

    bad_url = "https://legalacts.egov.kz/npa/view?id=99999999"
    good_url = "https://legalacts.egov.kz/npa/view?id=15906353"

    _, SessionLocal = create_engine_and_session_factory(database_url)
    seed_session = SessionLocal()
    queue.enqueue(seed_session, bad_url, "document", datetime.datetime(2020, 1, 1, tzinfo=UTC), section="npa")
    queue.enqueue(seed_session, good_url, "document", datetime.datetime(2020, 1, 1, 0, 0, 1, tzinfo=UTC), section="npa")
    seed_session.close()

    fetcher = FlakyStubFetcher({good_url: [ru_html, kk_html]}, fail_urls={bad_url})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(database_url, limit=2)

    check_session = SessionLocal()
    from db.models import CrawlQueueEntry, LegalAct

    bad_row = check_session.get(CrawlQueueEntry, bad_url)
    assert bad_row.status == "error"
    assert bad_row.last_error

    good_row = check_session.get(CrawlQueueEntry, good_url)
    assert good_row.status == "done"

    act = check_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 15906353)
    ).fetchone()
    assert act is not None
    assert act.status == "Архив"

    failed_act = check_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 99999999)
    ).fetchone()
    assert failed_act is None
    check_session.close()


def test_run_marks_404_document_entry_done_not_error(database_url, monkeypatch):
    url = "https://legalacts.egov.kz/npa/view?id=404404"

    _, SessionLocal = create_engine_and_session_factory(database_url)
    seed_session = SessionLocal()
    queue.enqueue(seed_session, url, "document", datetime.datetime(2020, 1, 1, tzinfo=UTC), section="npa")
    seed_session.close()

    fetcher = StubFetcher({}, status_codes={url: 404})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(database_url, limit=1)

    check_session = SessionLocal()
    from db.models import CrawlQueueEntry, LegalAct
    row = check_session.get(CrawlQueueEntry, url)
    assert row.status == "done"
    assert row.last_error is None
    assert check_session.execute(LegalAct.__table__.select()).fetchone() is None
    check_session.close()


def test_second_run_rediscovers_stale_list_page(database_url, monkeypatch):
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    seed_url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE&page=29852"

    monkeypatch.setattr(run_module, "SEED_LIST_URLS", [("npa", seed_url)])
    fetcher = StubFetcher({seed_url: list_html})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(database_url, limit=1)
    assert fetcher.calls.count(seed_url) == 1

    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    from db.models import CrawlQueueEntry
    entry = session.get(CrawlQueueEntry, seed_url)
    assert entry.status == "done"
    entry.processed_at = datetime.datetime(2020, 1, 1, tzinfo=UTC)
    session.commit()
    session.close()

    run_module.run(database_url, limit=1)

    assert fetcher.calls.count(seed_url) == 2
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/pytest tests/test_run.py tests/test_queue.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/scraper/run.py backend/tests/test_queue.py backend/tests/test_run.py
git commit -m "feat: scraper orchestration uses LegalAct/datetime timestamps"
```

---

### Task 4: API layer — documents and analytics routers become an adapter over the new schema

**Files:**
- Modify: `backend/app/schemas/documents.py`
- Modify: `backend/app/routers/documents.py`
- Modify: `backend/app/routers/analytics.py`
- Modify: `backend/tests/test_documents_router.py`
- Modify: `backend/tests/test_analytics_router.py`
- Test: `backend/tests/test_documents_router.py`, `backend/tests/test_analytics_router.py`

**Interfaces:**
- Consumes: `db.models.LegalAct` (with `.doc_type`/`.government_body` association proxies from Task 1).
- Produces: unchanged JSON shape for `GET /documents`, `GET /documents/{id}`, `GET /analytics/summary`, `GET /analytics/timeseries` (verified by the existing/updated router tests — this is the "no frontend changes" guarantee from the Global Constraints).

- [ ] **Step 1: Write the failing tests — rewrite `backend/tests/test_documents_router.py`**

```python
import datetime

from db.models import Comment, LegalAct
from db.session import create_engine_and_session_factory

UTC = datetime.timezone.utc
T1 = datetime.datetime(2026, 9, 1, tzinfo=UTC)


def _seed_legal_act(database_url, **overrides):
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    defaults = dict(
        external_id=1, section="npa", url="https://example.test/1",
        title_ru="Title", status="active",
        first_seen_at=T1, last_checked_at=T1,
    )
    defaults.update(overrides)
    legal_act = LegalAct(**defaults)
    session.add(legal_act)
    session.commit()
    legal_act_id = legal_act.id
    session.close()
    return legal_act_id


def test_list_documents_filters_by_section(database_url, api_client):
    _seed_legal_act(database_url, external_id=1, section="npa", url="https://example.test/1")
    _seed_legal_act(database_url, external_id=2, section="arv", url="https://example.test/2")

    response = api_client.get("/documents", params={"section": "arv"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["section"] == "arv"


def test_get_document_returns_404_for_missing_id(api_client):
    response = api_client.get("/documents/999999")
    assert response.status_code == 404


def test_get_document_includes_comments(database_url, api_client):
    legal_act_id = _seed_legal_act(database_url, external_id=3, section="npa", url="https://example.test/3")
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    session.add(Comment(
        legal_act_id=legal_act_id, external_comment_id=10, comment_channel=6, body="text",
        first_seen_at=T1,
    ))
    session.commit()
    session.close()

    response = api_client.get(f"/documents/{legal_act_id}")

    assert response.status_code == 200
    body = response.json()
    assert len(body["comments"]) == 1
    assert body["comments"][0]["body"] == "text"


def test_get_document_resolves_government_body_and_doc_type_names(database_url, api_client):
    legal_act_id = _seed_legal_act(database_url, external_id=4, section="npa", url="https://example.test/4")
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    from db.models import ActType, GovernmentBody
    legal_act = session.get(LegalAct, legal_act_id)
    government_body = GovernmentBody(name="Министерство юстиции")
    act_type = ActType(name="Закон")
    session.add_all([government_body, act_type])
    session.flush()
    legal_act.government_body_id = government_body.id
    legal_act.act_type_id = act_type.id
    session.commit()
    session.close()

    response = api_client.get(f"/documents/{legal_act_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["government_body"] == "Министерство юстиции"
    assert body["doc_type"] == "Закон"


def test_documents_endpoint_requires_api_key(database_url):
    from app.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(Settings(database_url=database_url, api_key="expected-key"))
    client = TestClient(app)

    assert client.get("/documents").status_code in (401, 422)
```

Run: `cd backend && .venv/Scripts/pytest tests/test_documents_router.py -v`
Expected: FAIL — `db.models.LegalAct` requires `title_ru` etc. to already exist (it does, from Task 1); the router still queries the old `Document` model, so responses won't include a resolved `government_body`/`doc_type` correctly once the router itself changes shape. (If Task 1–3 are already applied and the router hasn't been touched yet, `test_get_document_resolves_government_body_and_doc_type_names` is the one guaranteed to fail — it names something the current adapter-less router can't yet do, since routers still import `Document`.)

- [ ] **Step 2: Rewrite `backend/app/schemas/documents.py`**

```python
import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class DocumentListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: int
    section: str
    url: str
    title_ru: Optional[str] = None
    title_kk: Optional[str] = None
    status: Optional[str] = None
    doc_type: Optional[str] = None
    government_body: Optional[str] = None
    created_date: Optional[str] = None
    discussion_end_date: Optional[str] = None
    comments_total: Optional[int] = None
    likes_count: Optional[int] = None
    dislikes_count: Optional[int] = None
    first_seen_at: datetime.datetime
    last_checked_at: datetime.datetime


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_comment_id: int
    parent_external_comment_id: Optional[int] = None
    author_name: Optional[str] = None
    body: str
    article_ref: Optional[str] = None
    status: Optional[str] = None
    commented_at_raw: Optional[str] = None
    first_seen_at: datetime.datetime


class DocumentDetailOut(DocumentListItemOut):
    comments: list[CommentOut]
```

- [ ] **Step 3: Rewrite `backend/app/routers/documents.py`**

```python
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.deps import get_db, require_api_key
from app.schemas.documents import DocumentDetailOut, DocumentListItemOut
from db.models import LegalAct

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(require_api_key)])

PAGE_SIZE = 20


@router.get("", response_model=list[DocumentListItemOut])
def list_documents(
    section: Optional[str] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
):
    stmt = select(LegalAct).options(
        joinedload(LegalAct.government_body_ref), joinedload(LegalAct.act_type_ref)
    )
    if section is not None:
        stmt = stmt.where(LegalAct.section == section)
    if status_filter is not None:
        stmt = stmt.where(LegalAct.status == status_filter)
    stmt = stmt.order_by(LegalAct.id).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    return db.execute(stmt).scalars().all()


@router.get("/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: int, db: Session = Depends(get_db)):
    legal_act = db.execute(
        select(LegalAct)
        .where(LegalAct.id == document_id)
        .options(joinedload(LegalAct.government_body_ref), joinedload(LegalAct.act_type_ref))
    ).scalar_one_or_none()
    if legal_act is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return legal_act
```

Note: `LegalAct` no longer has `raw_html_ru`/`raw_html_kk` columns at all (Task 1), so the `defer(...)` calls the old router used are gone — there's nothing left to defer.

- [ ] **Step 4: Rewrite `backend/app/routers/analytics.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_db, require_api_key
from app.schemas.analytics import AnalyticsSummaryOut, SectionCount, StatusCount, TimeseriesPoint
from db.models import Comment, LegalAct

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(require_api_key)])


@router.get("/summary", response_model=AnalyticsSummaryOut)
def analytics_summary(db: Session = Depends(get_db)):
    by_section = db.execute(
        select(LegalAct.section, func.count(LegalAct.id)).group_by(LegalAct.section)
    ).all()
    by_status = db.execute(
        select(LegalAct.status, func.count(LegalAct.id)).group_by(LegalAct.status)
    ).all()
    total_comments = db.execute(select(func.count(Comment.id))).scalar_one()

    return AnalyticsSummaryOut(
        documents_by_section=[SectionCount(section=s, count=c) for s, c in by_section],
        documents_by_status=[StatusCount(status=s, count=c) for s, c in by_status],
        total_documents=sum(c for _, c in by_section),
        total_comments=total_comments,
    )


@router.get("/timeseries", response_model=list[TimeseriesPoint])
def analytics_timeseries(interval: str = "day", db: Session = Depends(get_db)):
    if interval not in {"day", "week"}:
        raise HTTPException(status_code=400, detail="interval must be 'day' or 'week'")

    bucket = func.date_trunc(interval, LegalAct.first_seen_at)
    stmt = (
        select(bucket.label("bucket"), func.count(LegalAct.id))
        .group_by("bucket")
        .order_by("bucket")
    )
    rows = db.execute(stmt).all()
    return [TimeseriesPoint(bucket=bucket_value.isoformat(), count=count) for bucket_value, count in rows]
```

Note: `LegalAct.first_seen_at` is natively `DateTime(timezone=True)` now, so the `.cast(TIMESTAMP(timezone=True))` workaround the old code needed is gone — `date_trunc` runs directly against the column.

- [ ] **Step 5: Rewrite `backend/tests/test_analytics_router.py`**

```python
import datetime

from db.models import Comment, LegalAct
from db.session import create_engine_and_session_factory

UTC = datetime.timezone.utc


def _seed(database_url, acts, comments=()):
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    for act in acts:
        session.add(LegalAct(**act))
    session.commit()
    for comment in comments:
        session.add(Comment(**comment))
    session.commit()
    session.close()


def test_analytics_summary_counts_by_section_and_status(database_url, api_client):
    _seed(database_url, [
        dict(external_id=1, section="npa", url="u1", status="active",
             first_seen_at=datetime.datetime(2026, 9, 1, tzinfo=UTC),
             last_checked_at=datetime.datetime(2026, 9, 1, tzinfo=UTC)),
        dict(external_id=2, section="npa", url="u2", status="archived",
             first_seen_at=datetime.datetime(2026, 9, 2, tzinfo=UTC),
             last_checked_at=datetime.datetime(2026, 9, 2, tzinfo=UTC)),
        dict(external_id=3, section="arv", url="u3", status="active",
             first_seen_at=datetime.datetime(2026, 9, 3, tzinfo=UTC),
             last_checked_at=datetime.datetime(2026, 9, 3, tzinfo=UTC)),
    ])

    response = api_client.get("/analytics/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["total_documents"] == 3
    section_counts = {row["section"]: row["count"] for row in body["documents_by_section"]}
    assert section_counts == {"npa": 2, "arv": 1}


def test_analytics_timeseries_buckets_by_day(database_url, api_client):
    _seed(database_url, [
        dict(external_id=1, section="npa", url="u1",
             first_seen_at=datetime.datetime(2026, 9, 1, 10, tzinfo=UTC),
             last_checked_at=datetime.datetime(2026, 9, 1, 10, tzinfo=UTC)),
        dict(external_id=2, section="npa", url="u2",
             first_seen_at=datetime.datetime(2026, 9, 1, 18, tzinfo=UTC),
             last_checked_at=datetime.datetime(2026, 9, 1, 18, tzinfo=UTC)),
        dict(external_id=3, section="npa", url="u3",
             first_seen_at=datetime.datetime(2026, 9, 2, 9, tzinfo=UTC),
             last_checked_at=datetime.datetime(2026, 9, 2, 9, tzinfo=UTC)),
    ])

    response = api_client.get("/analytics/timeseries", params={"interval": "day"})

    assert response.status_code == 200
    body = response.json()
    counts = {point["bucket"][:10]: point["count"] for point in body}
    assert counts == {"2026-09-01": 2, "2026-09-02": 1}


def test_analytics_timeseries_rejects_invalid_interval(api_client):
    response = api_client.get("/analytics/timeseries", params={"interval": "month"})
    assert response.status_code == 400
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/pytest tests/test_documents_router.py tests/test_analytics_router.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/documents.py backend/app/routers/documents.py \
  backend/app/routers/analytics.py backend/tests/test_documents_router.py \
  backend/tests/test_analytics_router.py
git commit -m "feat: adapt documents/analytics API to LegalAct schema, contract unchanged"
```

---

### Task 5: Docker Compose migration step

**Files:**
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: `alembic upgrade head` from Task 1 (files already copied into the image by the existing `COPY . .` in `backend/Dockerfile` — no Dockerfile change needed).

- [ ] **Step 1: Update the `api` and `worker` service commands in `docker-compose.yml`**

Change:
```yaml
  api:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
```
to:
```yaml
  api:
    build: ./backend
    command: sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"
```

Change:
```yaml
  worker:
    build: ./backend
    command: python -m worker.loop
```
to:
```yaml
  worker:
    build: ./backend
    command: sh -c "alembic upgrade head && python -m worker.loop"
```

Leave every other line in `docker-compose.yml` (environment, ports, depends_on, healthcheck, `frontend`, `volumes`) exactly as-is.

- [ ] **Step 2: Validate the compose file**

Run: `docker compose config`
Expected: prints the fully resolved config with no errors (this only validates YAML/interpolation syntax — it does not require `.env` values to be real credentials, but `docker compose config` does require a `.env` file to exist per the project's existing setup instructions; if none is present locally, this step can be skipped and verified later when `.env` is available).

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: run alembic upgrade head before api/worker start"
```

---

### Task 6: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:** None — documentation only, no code interfaces.

- [ ] **Step 1: Update the Setup section's dependency list and add an Alembic note**

Find:
```
Docker-образ (`backend/Dockerfile`) использует `python:3.12-slim`; backend теперь рассчитан на запуск внутри контейнера. Основные зависимости: `requests`, `beautifulsoup4` + `lxml`, `fastapi`, `uvicorn`, `sqlalchemy`, `psycopg2-binary`, `pytest`, `testcontainers`.
```
Replace with:
```
Docker-образ (`backend/Dockerfile`) использует `python:3.12-slim`; backend теперь рассчитан на запуск внутри контейнера. Основные зависимости: `requests`, `beautifulsoup4` + `lxml`, `fastapi`, `uvicorn`, `sqlalchemy`, `alembic`, `psycopg2-binary`, `pytest`, `testcontainers`.

Схема БД версионируется через Alembic (`backend/alembic/`); `Base.metadata.create_all()` для прод/dev пути больше не используется — актуальную схему создаёт только `alembic upgrade head` (внутри Docker Compose это часть команды запуска `api`/`worker`; локально из `backend/`: `.venv/Scripts/alembic upgrade head`).
```

- [ ] **Step 2: Update the testcontainers note in the Commands section**

Find:
```
Тесты с БД требуют Docker (они спинят временный контейнер `postgres:16-alpine` через testcontainers).
```
Replace with:
```
Тесты с БД требуют Docker (они спинят временный контейнер `postgres:16-alpine` через testcontainers; фикстуры `tests/conftest.py` перед каждым тестом пересоздают схему `public` и прогоняют `alembic upgrade head`, так что миграции проверяются тем же прогоном, что и остальной код).
```

- [ ] **Step 3: Replace the storage-layer Architecture bullets**

Find:
```
- `backend/db/models.py` — ORM-модели (`Document`, `Comment`, `CrawlQueueEntry`) для таблиц в Postgres.
- `backend/db/session.py` — `create_engine_and_session_factory()`: создаёт engine и session factory, вызывает `Base.metadata.create_all()`.
```
Replace with:
```
- `backend/db/models.py` — ORM-модели: `LegalAct` (корневая сущность, замена `Document`), нормализованные справочники `GovernmentBody`/`ActType` (get-or-create по имени; `LegalAct.government_body`/`LegalAct.doc_type` — `association_proxy` на их `.name`, поэтому внешний JSON-контракт API не меняется), `Comment` (поле `comment_channel` — какая из 8 вкладок экспертного участия, `typeComment`; уникальность `(legal_act_id, external_comment_id, comment_channel)`), `LegalActSnapshot` (история изменений + сырой HTML + SHA-256 — единственное место, где сырой HTML вообще хранится, у `LegalAct` таких колонок нет), `CrawlQueueEntry`. Внутренние временные поля (`first_seen_at`, `last_checked_at`, `captured_at`, `discovered_at`, `processed_at`) — `DateTime(timezone=True)` (UTC); поля, пришедшие с источника как текст (`created_date`, `discussion_end_date`, `commented_at_raw`), остаются строками — таймзона источника не подтверждена. Дизайн: `docs/superpowers/specs/2026-09-22-legalacts-data-model-design.md`.
- `backend/db/session.py` — `create_engine_and_session_factory()`: создаёт engine и session factory; схему больше не создаёт — см. Alembic выше.
```

- [ ] **Step 4: Update the `store.py` bullet**

Find:
```
- `backend/scraper/store.py` — сохранение документов и комментариев в БД (upsert): `upsert_document`, `upsert_comments`. Сохраняет `first_seen_at`, обновляет `last_checked_at`; kk-поля не затираются, если при очередном обходе не пришли.
```
Replace with:
```
- `backend/scraper/store.py` — сохранение актов и комментариев в БД (upsert): `upsert_legal_act` (get-or-create для `GovernmentBody`/`ActType`; вставляет новую строку `LegalActSnapshot`, только если изменились статус/сроки/счётчики/хэш содержимого — идемпотентно для неизменного повторного обхода), `upsert_comments` (принимает `comment_channel`; сейчас всегда `6` — собирается только вкладка «Комментарий», остальные 7 подтверждённых вкладок экспертного участия пока не собираются). Сохраняет `first_seen_at`, обновляет `last_checked_at`; kk-поля не затираются, если при очередном обходе не пришли — включая `raw_html_kk`, который в этом случае переносится из последнего снапшота.
```

- [ ] **Step 5: Update the `run.py` bullet**

Find the sentence:
```
`backend/scraper/run.py` — оркестрация скрейпера: `process_list_entry`, `process_document_entry`, `run(database_url, limit=None)` (главный цикл: list-страницы обрабатываются раньше document-страниц), `main()` (CLI).
```
Replace with:
```
`backend/scraper/run.py` — оркестрация скрейпера: `process_list_entry`, `process_document_entry`, `run(database_url, limit=None)` (главный цикл: list-страницы обрабатываются раньше document-страниц), `main()` (CLI); внутренние переменные переименованы `document_id` → `legal_act_id` вслед за моделью, таймстемпы теперь реальные `datetime` (`scraper.run.now()`), а не ISO-строки.
```

- [ ] **Step 6: Verify no stale references remain**

Run: `grep -rn "upsert_document\|Base.metadata.create_all" CLAUDE.md`
Expected: no matches (both instances already replaced by Steps 1–5).

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document LegalAct schema and Alembic workflow in CLAUDE.md"
```

---

### Task 7: Full-suite verification

**Files:** none (verification only — no commit expected unless a fixup is needed).

- [ ] **Step 1: Run the entire backend test suite**

Run: `cd backend && .venv/Scripts/pytest -v`
Expected: all tests PASS (this includes the untouched parser/config/deps/fetch/worker-loop test files, which this plan does not modify — they should be unaffected).

- [ ] **Step 2: Validate the Docker Compose file once more, end to end**

Run: `docker compose config`
Expected: no errors.

- [ ] **Step 3: If any test fails, fix the root cause in the relevant task's files, re-run Step 1, and commit the fix separately** (`git commit -m "fix: <what was wrong>"`) — do not proceed to calling the migration done until the full suite is green.
