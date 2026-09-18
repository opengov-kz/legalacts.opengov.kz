# Backend: PostgreSQL+SQLAlchemy+FastAPI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the scraper into `backend/`, replace its SQLite storage with PostgreSQL via SQLAlchemy, and add a FastAPI read API over the collected data — while preserving all current scraping behavior.

**Architecture:** SQLAlchemy declarative models (`backend/db/models.py`) are the single schema source, used both by the scraper's storage layer (`backend/scraper/queue.py`, `backend/scraper/store.py`) and by the FastAPI app (`backend/app/`). The scraper's crawl loop (`backend/scraper/run.py`) is unchanged in structure, only its persistence calls move from raw `sqlite3` to a SQLAlchemy `Session`. A separate `worker/loop.py` process calls `run()` on a sleep interval; the API process only reads.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x, psycopg2, FastAPI, uvicorn, pydantic-settings, pytest, testcontainers[postgres], Docker/docker-compose.

**Spec:** `docs/superpowers/specs/2026-09-18-backend-postgres-fastapi-design.md`

## Global Constraints

- Backend code lives entirely under `backend/`; Docker base image is `python:3.12-slim`.
- SQLAlchemy declarative ORM models in `backend/db/models.py` are the single source of schema truth for both scraper and API — no Alembic this phase; schema is created via `Base.metadata.create_all()`.
- `first_seen_at`, `last_checked_at`, `discovered_at`, `processed_at` stay `String` (ISO-8601 text, produced by `now_iso()`) — not `TIMESTAMPTZ`.
- No migration of existing `legalacts.db` data — every task starts from a fresh Postgres schema.
- FastAPI endpoints (except `/health`) require a static `X-API-Key` header, checked against the `API_KEY` setting.
- Any test that touches the database runs against a real PostgreSQL instance via `testcontainers[postgres]`, never SQLite — SQLite and Postgres diverge on `INSERT ... ON CONFLICT` dialect and this must not go untested.

---

### Task 1: Move scraper into `backend/`, add new dependencies

**Files:**
- Move: `scraper/` → `backend/scraper/`
- Move: `tests/` → `backend/tests/`
- Move: `requirements.txt` → `backend/requirements.txt`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Produces: `backend/` as the root package directory for all subsequent tasks (everything imports as if `backend/` is on `sys.path`, exactly as `tests/conftest.py` already arranges via `project_root = Path(__file__).parent.parent`).

- [ ] **Step 1: Move the directories with git mv**

```bash
git mv scraper backend/scraper
git mv tests backend/tests
git mv requirements.txt backend/requirements.txt
```

- [ ] **Step 2: Update `backend/requirements.txt` with the new dependencies**

```
requests>=2.31,<3
beautifulsoup4>=4.12,<5
lxml>=4.9,<6
pytest>=7.4,<8
sqlalchemy>=2.0,<3
psycopg2-binary>=2.9,<3
fastapi>=0.115,<1
uvicorn[standard]>=0.30,<1
pydantic-settings>=2.4,<3
testcontainers[postgres]>=4.7,<5
```

- [ ] **Step 3: Install dependencies and run the moved test suite unchanged**

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
.venv/Scripts/pytest -v
```

Expected: all 43 previously-passing tests still PASS from the new location (nothing about storage has changed yet — this step only proves the move didn't break imports or `tests/conftest.py`'s `sys.path` setup).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: move scraper into backend/, add Postgres/FastAPI dependencies"
```

---

### Task 2: SQLAlchemy models and session factory

**Files:**
- Create: `backend/db/__init__.py` (empty)
- Create: `backend/db/models.py`
- Create: `backend/db/session.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_db.py` (replace SQLite-based content entirely)
- Delete: `backend/scraper/db.py`

**Interfaces:**
- Produces: `Base` (declarative base), `Document`, `Comment`, `CrawlQueueEntry` (ORM models, exact field sets below) from `db.models`; `create_engine_and_session_factory(database_url) -> tuple[Engine, sessionmaker]` from `db.session`.

- [ ] **Step 1: Write `backend/db/models.py`**

```python
from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True)
    external_id = Column(Integer, nullable=False, unique=True)
    section = Column(String, nullable=False)
    url = Column(String, nullable=False)
    title_ru = Column(String)
    title_kk = Column(String)
    status = Column(String)
    doc_type = Column(String)
    government_body = Column(String)
    created_date = Column(String)
    discussion_end_date = Column(String)
    comments_total = Column(Integer)
    likes_count = Column(Integer)
    dislikes_count = Column(Integer)
    raw_html_ru = Column(Text)
    raw_html_kk = Column(Text)
    first_seen_at = Column(String, nullable=False)
    last_checked_at = Column(String, nullable=False)

    comments = relationship("Comment", back_populates="document", order_by="Comment.id")


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        UniqueConstraint("document_id", "external_comment_id", name="uq_comment_document_external_id"),
    )

    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    external_comment_id = Column(Integer, nullable=False)
    parent_external_comment_id = Column(Integer)
    author_name = Column(String)
    body = Column(Text, nullable=False)
    article_ref = Column(String)
    status = Column(String)
    commented_at_raw = Column(String)
    first_seen_at = Column(String, nullable=False)

    document = relationship("Document", back_populates="comments")


class CrawlQueueEntry(Base):
    __tablename__ = "crawl_queue"

    url = Column(String, primary_key=True)
    page_type = Column(String, nullable=False)
    section = Column(String)
    status = Column(String, nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text)
    discovered_at = Column(String, nullable=False)
    processed_at = Column(String)
```

- [ ] **Step 2: Write `backend/db/session.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base


def create_engine_and_session_factory(database_url):
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    return engine, session_factory
```

- [ ] **Step 3: Add testcontainers fixtures to `backend/tests/conftest.py`**

```python
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

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
```

`database_url` gives a clean (dropped) schema and lets a function like `run()` create its own engine/session; `db_session` gives a ready-to-use session with tables already created, for tests that call storage functions directly.

- [ ] **Step 4: Replace `backend/tests/test_db.py` entirely**

```python
from sqlalchemy import inspect


def test_create_all_creates_expected_tables(pg_engine):
    from db.models import Base

    Base.metadata.create_all(pg_engine)
    tables = set(inspect(pg_engine).get_table_names())
    assert {"documents", "comments", "crawl_queue"}.issubset(tables)


def test_documents_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("documents")}
    assert columns == {
        "id", "external_id", "section", "url", "title_ru", "title_kk",
        "status", "doc_type", "government_body", "created_date",
        "discussion_end_date", "comments_total", "likes_count",
        "dislikes_count", "raw_html_ru", "raw_html_kk", "first_seen_at",
        "last_checked_at",
    }


def test_comments_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("comments")}
    assert columns == {
        "id", "document_id", "external_comment_id",
        "parent_external_comment_id", "author_name", "body", "article_ref",
        "status", "commented_at_raw", "first_seen_at",
    }


def test_crawl_queue_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("crawl_queue")}
    assert columns == {
        "url", "page_type", "section", "status", "attempts", "last_error",
        "discovered_at", "processed_at",
    }
```

- [ ] **Step 5: Delete the superseded SQLite schema module**

```bash
git rm backend/scraper/db.py
```

- [ ] **Step 6: Run the new tests**

Run: `cd backend && .venv/Scripts/pytest tests/test_db.py -v`
Expected: PASS (first run pulls the `postgres:16-alpine` image — requires Docker running locally).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: add SQLAlchemy models and Postgres session factory"
```

---

### Task 3: Rewrite `queue.py` on SQLAlchemy

**Files:**
- Modify: `backend/scraper/queue.py`
- Modify: `backend/tests/test_queue.py` (replace entirely)

**Interfaces:**
- Consumes: `Document`, `Comment`, `CrawlQueueEntry` from `db.models` (Task 2).
- Produces: `enqueue(session, url, page_type, discovered_at, section=None)`, `next_pending(session, page_type) -> str | None`, `section_for(session, url) -> str | None`, `mark_done(session, url, processed_at)`, `mark_error(session, url, error_message, processed_at)`, `requeue_stale_documents(session, older_than_iso)`, `requeue_stale_lists(session, older_than_iso)` — same names and semantics as before, first argument is now a SQLAlchemy `Session` instead of a `sqlite3.Connection`.

- [ ] **Step 1: Write the failing tests in `backend/tests/test_queue.py`**

```python
from scraper import queue


def test_enqueue_then_next_pending_returns_url(db_session):
    queue.enqueue(db_session, "https://example.test/list", "list", "2026-09-15T00:00:00+00:00")
    assert queue.next_pending(db_session, "list") == "https://example.test/list"
    assert queue.next_pending(db_session, "document") is None


def test_enqueue_is_idempotent_for_same_url(db_session):
    queue.enqueue(db_session, "https://example.test/list", "list", "2026-09-15T00:00:00+00:00")
    queue.enqueue(db_session, "https://example.test/list", "list", "2026-09-15T00:05:00+00:00")
    from db.models import CrawlQueueEntry
    count = db_session.query(CrawlQueueEntry).count()
    assert count == 1


def test_mark_done_removes_url_from_pending(db_session):
    queue.enqueue(db_session, "https://example.test/list", "list", "2026-09-15T00:00:00+00:00")
    queue.mark_done(db_session, "https://example.test/list", "2026-09-15T00:05:00+00:00")
    assert queue.next_pending(db_session, "list") is None

    from db.models import CrawlQueueEntry
    row = db_session.get(CrawlQueueEntry, "https://example.test/list")
    assert row.status == "done"
    assert row.processed_at == "2026-09-15T00:05:00+00:00"
    assert row.attempts == 1


def test_mark_error_records_message_and_keeps_out_of_pending(db_session):
    queue.enqueue(db_session, "https://example.test/list", "list", "2026-09-15T00:00:00+00:00")
    queue.mark_error(db_session, "https://example.test/list", "timeout", "2026-09-15T00:05:00+00:00")
    assert queue.next_pending(db_session, "list") is None

    from db.models import CrawlQueueEntry
    row = db_session.get(CrawlQueueEntry, "https://example.test/list")
    assert row.status == "error"
    assert row.last_error == "timeout"


def test_enqueue_stores_section_and_section_for_reads_it_back(db_session):
    queue.enqueue(
        db_session, "https://example.test/npa/view?id=1", "document",
        "2026-09-15T00:00:00+00:00", section="arv",
    )
    assert queue.section_for(db_session, "https://example.test/npa/view?id=1") == "arv"


def test_section_for_returns_none_for_unknown_url(db_session):
    assert queue.section_for(db_session, "https://example.test/missing") is None


def test_requeue_stale_documents_resets_old_done_documents_only(db_session):
    queue.enqueue(db_session, "https://example.test/doc-old", "document", "2026-09-14T00:00:00+00:00")
    queue.enqueue(db_session, "https://example.test/doc-new", "document", "2026-09-14T00:00:00+00:00")
    queue.enqueue(db_session, "https://example.test/list", "list", "2026-09-14T00:00:00+00:00")
    queue.mark_done(db_session, "https://example.test/doc-old", "2026-09-01T00:00:00+00:00")
    queue.mark_done(db_session, "https://example.test/doc-new", "2026-09-14T00:00:00+00:00")
    queue.mark_done(db_session, "https://example.test/list", "2026-09-01T00:00:00+00:00")

    queue.requeue_stale_documents(db_session, "2026-09-10T00:00:00+00:00")

    assert queue.next_pending(db_session, "document") == "https://example.test/doc-old"

    from db.models import CrawlQueueEntry
    assert db_session.get(CrawlQueueEntry, "https://example.test/doc-new").status == "done"
    assert db_session.get(CrawlQueueEntry, "https://example.test/list").status == "done"


def test_requeue_stale_lists_resets_old_done_lists_only(db_session):
    queue.enqueue(db_session, "https://example.test/list-old", "list", "2026-09-14T00:00:00+00:00")
    queue.enqueue(db_session, "https://example.test/list-new", "list", "2026-09-14T00:00:00+00:00")
    queue.enqueue(db_session, "https://example.test/doc", "document", "2026-09-14T00:00:00+00:00")
    queue.mark_done(db_session, "https://example.test/list-old", "2026-09-01T00:00:00+00:00")
    queue.mark_done(db_session, "https://example.test/list-new", "2026-09-14T00:00:00+00:00")
    queue.mark_done(db_session, "https://example.test/doc", "2026-09-01T00:00:00+00:00")

    queue.requeue_stale_lists(db_session, "2026-09-10T00:00:00+00:00")

    assert queue.next_pending(db_session, "list") == "https://example.test/list-old"

    from db.models import CrawlQueueEntry
    assert db_session.get(CrawlQueueEntry, "https://example.test/list-new").status == "done"
    assert db_session.get(CrawlQueueEntry, "https://example.test/doc").status == "done"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/pytest tests/test_queue.py -v`
Expected: FAIL (`scraper.queue` still expects a `sqlite3.Connection` and uses `?`-style SQL).

- [ ] **Step 3: Rewrite `backend/scraper/queue.py`**

```python
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models import CrawlQueueEntry


def enqueue(session, url, page_type, discovered_at, section=None):
    stmt = (
        pg_insert(CrawlQueueEntry)
        .values(
            url=url, page_type=page_type, section=section,
            status="pending", attempts=0, discovered_at=discovered_at,
        )
        .on_conflict_do_nothing(index_elements=["url"])
    )
    session.execute(stmt)
    session.commit()


def next_pending(session, page_type):
    stmt = (
        select(CrawlQueueEntry.url)
        .where(CrawlQueueEntry.page_type == page_type, CrawlQueueEntry.status == "pending")
        .order_by(CrawlQueueEntry.discovered_at)
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def section_for(session, url):
    stmt = select(CrawlQueueEntry.section).where(CrawlQueueEntry.url == url)
    return session.execute(stmt).scalar_one_or_none()


def mark_done(session, url, processed_at):
    entry = session.get(CrawlQueueEntry, url)
    entry.status = "done"
    entry.processed_at = processed_at
    entry.attempts += 1
    session.commit()


def mark_error(session, url, error_message, processed_at):
    entry = session.get(CrawlQueueEntry, url)
    entry.status = "error"
    entry.last_error = error_message
    entry.processed_at = processed_at
    entry.attempts += 1
    session.commit()


def requeue_stale_documents(session, older_than_iso):
    session.execute(
        update(CrawlQueueEntry)
        .where(
            CrawlQueueEntry.page_type == "document",
            CrawlQueueEntry.status == "done",
            CrawlQueueEntry.processed_at < older_than_iso,
        )
        .values(status="pending")
    )
    session.commit()


def requeue_stale_lists(session, older_than_iso):
    session.execute(
        update(CrawlQueueEntry)
        .where(
            CrawlQueueEntry.page_type == "list",
            CrawlQueueEntry.status == "done",
            CrawlQueueEntry.processed_at < older_than_iso,
        )
        .values(status="pending")
    )
    session.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/pytest tests/test_queue.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/scraper/queue.py backend/tests/test_queue.py
git commit -m "feat: rewrite crawl queue storage on SQLAlchemy/Postgres"
```

---

### Task 4: Rewrite `store.py` on SQLAlchemy

**Files:**
- Modify: `backend/scraper/store.py`
- Modify: `backend/tests/test_store.py` (replace entirely)

**Interfaces:**
- Consumes: `Document`, `Comment` from `db.models` (Task 2).
- Produces: `upsert_document(session, external_id, section, url, fields, now) -> int`, `upsert_comments(session, document_id, comments, now)` — same names/semantics as before, first argument is now a `Session`.

- [ ] **Step 1: Write the failing tests in `backend/tests/test_store.py`**

```python
from scraper import store


def test_upsert_document_inserts_new_row(db_session):
    fields = {
        "title_ru": "Title_RU_001", "title_kk": "Title_KK_001",
        "status": "Status_Value_001", "doc_type": "DocType_Value_001",
        "government_body": "Body_Value_001", "created_date": "2026-01-01",
        "discussion_end_date": "2026-12-31", "comments_total": 42,
        "likes_count": 99, "dislikes_count": 88,
        "raw_html_ru": "<html>content_ru_001</html>",
        "raw_html_kk": "<html>content_kk_001</html>",
    }
    doc_id = store.upsert_document(
        db_session, 15906353, "npa_section_001",
        "https://legalacts.test/npa/view?id=15906353", fields,
        "2026-09-15T00:00:00+00:00",
    )

    from db.models import Document
    row = db_session.get(Document, doc_id)

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
    assert row.raw_html_ru == "<html>content_ru_001</html>"
    assert row.raw_html_kk == "<html>content_kk_001</html>"
    assert row.first_seen_at == "2026-09-15T00:00:00+00:00"
    assert row.last_checked_at == "2026-09-15T00:00:00+00:00"


def test_upsert_document_updates_existing_and_preserves_first_seen_at(db_session):
    store.upsert_document(db_session, 1, "npa", "url1", {"title_ru": "V1"}, "2026-09-01T00:00:00+00:00")
    store.upsert_document(db_session, 1, "npa", "url1", {"title_ru": "V2"}, "2026-09-15T00:00:00+00:00")

    from db.models import Document
    row = db_session.execute(
        Document.__table__.select().where(Document.external_id == 1)
    ).fetchone()
    assert row.title_ru == "V2"
    assert row.first_seen_at == "2026-09-01T00:00:00+00:00"
    assert row.last_checked_at == "2026-09-15T00:00:00+00:00"


def test_upsert_document_keeps_kk_fields_when_not_provided(db_session):
    store.upsert_document(
        db_session, 1, "npa", "url1", {"title_ru": "V1", "title_kk": "KK1"},
        "2026-09-01T00:00:00+00:00",
    )
    store.upsert_document(db_session, 1, "npa", "url1", {"title_ru": "V2"}, "2026-09-15T00:00:00+00:00")

    from db.models import Document
    row = db_session.execute(
        Document.__table__.select().where(Document.external_id == 1)
    ).fetchone()
    assert row.title_kk == "KK1"


def test_upsert_comments_inserts_and_preserves_first_seen_at_on_update(db_session):
    doc_id = store.upsert_document(db_session, 1, "npa", "url1", {"title_ru": "V"}, "2026-09-01T00:00:00+00:00")
    comment = {
        "external_id": 100, "parent_external_id": None, "author_name": "A",
        "body": "text", "article_ref": None, "status": "rejected",
        "commented_at_raw": "10/09 - 11:05",
    }
    store.upsert_comments(db_session, doc_id, [comment], "2026-09-01T00:00:00+00:00")

    updated_comment = dict(comment, status="accepted")
    store.upsert_comments(db_session, doc_id, [updated_comment], "2026-09-15T00:00:00+00:00")

    from db.models import Comment
    row = db_session.execute(
        Comment.__table__.select().where(
            Comment.document_id == doc_id, Comment.external_comment_id == 100
        )
    ).fetchone()
    assert row.status == "accepted"
    assert row.first_seen_at == "2026-09-01T00:00:00+00:00"


def test_upsert_comments_skips_comment_with_none_external_id(db_session):
    doc_id = store.upsert_document(db_session, 1, "npa", "url1", {"title_ru": "V"}, "2026-09-01T00:00:00+00:00")
    comments = [
        {
            "external_id": 100, "parent_external_id": None, "author_name": "A",
            "body": "text A", "article_ref": None, "status": "accepted",
            "commented_at_raw": "10/09 - 11:05",
        },
        {
            "external_id": None, "parent_external_id": None, "author_name": "B",
            "body": "text with no id", "article_ref": None, "status": None,
            "commented_at_raw": None,
        },
        {
            "external_id": 101, "parent_external_id": None, "author_name": "C",
            "body": "text C", "article_ref": None, "status": "rejected",
            "commented_at_raw": "11/09 - 12:00",
        },
    ]

    store.upsert_comments(db_session, doc_id, comments, "2026-09-01T00:00:00+00:00")

    from db.models import Comment
    rows = db_session.execute(
        Comment.__table__.select()
        .where(Comment.document_id == doc_id)
        .order_by(Comment.external_comment_id)
    ).fetchall()
    assert [row.external_comment_id for row in rows] == [100, 101]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/pytest tests/test_store.py -v`
Expected: FAIL (`scraper.store` still expects a `sqlite3.Connection`).

- [ ] **Step 3: Rewrite `backend/scraper/store.py`**

```python
from sqlalchemy import select

from db.models import Comment, Document

DOCUMENT_FIELD_ORDER = [
    "section", "url", "title_ru", "title_kk", "status", "doc_type",
    "government_body", "created_date", "discussion_end_date",
    "comments_total", "likes_count", "dislikes_count", "raw_html_ru",
    "raw_html_kk",
]


def upsert_document(session, external_id, section, url, fields, now):
    existing = session.execute(
        select(Document).where(Document.external_id == external_id)
    ).scalar_one_or_none()

    title_kk = fields.get("title_kk") or (existing.title_kk if existing else None)
    raw_html_kk = fields.get("raw_html_kk") or (
        existing.raw_html_kk if existing else None
    )

    values = {
        "section": section,
        "url": url,
        "title_ru": fields.get("title_ru"),
        "title_kk": title_kk,
        "status": fields.get("status"),
        "doc_type": fields.get("doc_type"),
        "government_body": fields.get("government_body"),
        "created_date": fields.get("created_date"),
        "discussion_end_date": fields.get("discussion_end_date"),
        "comments_total": fields.get("comments_total"),
        "likes_count": fields.get("likes_count"),
        "dislikes_count": fields.get("dislikes_count"),
        "raw_html_ru": fields.get("raw_html_ru"),
        "raw_html_kk": raw_html_kk,
    }

    if existing is None:
        document = Document(
            external_id=external_id, first_seen_at=now, last_checked_at=now, **values,
        )
        session.add(document)
        session.commit()
        return document.id

    for key, value in values.items():
        setattr(existing, key, value)
    existing.last_checked_at = now
    session.commit()
    return existing.id


def upsert_comments(session, document_id, comments, now):
    for comment in comments:
        if comment["external_id"] is None:
            continue

        existing = session.execute(
            select(Comment).where(
                Comment.document_id == document_id,
                Comment.external_comment_id == comment["external_id"],
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(Comment(
                document_id=document_id,
                external_comment_id=comment["external_id"],
                parent_external_comment_id=comment["parent_external_id"],
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

`upsert_document`/`upsert_comments` use a read-then-write pattern (matching the original SQLite code's shape) rather than `INSERT ... ON CONFLICT DO UPDATE`, because the "don't clobber kk fields with an empty value" and "never touch first_seen_at on update" rules are easier to express correctly as plain Python branches than as a SQL `SET` clause. `queue.enqueue` (Task 3) is the one place that genuinely needs atomic upsert semantics (`ON CONFLICT DO NOTHING`) since it's a pure idempotent insert with no conditional field logic.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/pytest tests/test_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/scraper/store.py backend/tests/test_store.py
git commit -m "feat: rewrite document/comment storage on SQLAlchemy/Postgres"
```

---

### Task 5: Port `run.py` to SQLAlchemy sessions

**Files:**
- Modify: `backend/scraper/run.py`
- Modify: `backend/tests/test_run.py` (replace entirely)

**Interfaces:**
- Consumes: `queue.*`/`store.*` (Tasks 3-4), `create_engine_and_session_factory` (Task 2), `Fetcher`/`scraper.parsers.*` (unchanged).
- Produces: `process_list_entry(session, fetcher, url, section="npa")`, `process_document_entry(session, fetcher, url, section="npa")`, `run(database_url, limit=None)`, `main()` — same names as before; `run()`'s first parameter is now a `database_url` connection string instead of a SQLite file path.

- [ ] **Step 1: Write the failing tests in `backend/tests/test_run.py`**

```python
from pathlib import Path
from types import SimpleNamespace

from scraper import queue
from scraper import run as run_module
from db.session import create_engine_and_session_factory

FIXTURES = Path(__file__).parent / "fixtures"


class StubFetcher:
    def __init__(self, pages, status_codes=None):
        self._pages = {url: list(v) if isinstance(v, list) else [v] for url, v in pages.items()}
        self._status_codes = dict(status_codes or {})
        self.calls = []
        self.lang_calls = []

    def get(self, url):
        self.calls.append(url)
        remaining = self._pages.get(url)
        html = ""
        if remaining:
            html = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        status_code = self._status_codes.get(url, 200)
        return SimpleNamespace(text=html, status_code=status_code)

    def set_language(self, lang, location="/"):
        self.lang_calls.append(lang)


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

    from db.models import Comment, Document
    doc = db_session.execute(
        Document.__table__.select().where(Document.external_id == 15906353)
    ).fetchone()
    assert doc.section == "withdraw"
    assert doc.status == "Архив"
    assert doc.title_kk.startswith("Қазақстан Республикасы")
    assert doc.raw_html_ru == ru_html
    assert doc.raw_html_kk == kk_html

    comment_count = db_session.execute(
        Comment.__table__.select().where(Comment.document_id == doc.id)
    ).fetchall()
    assert len(comment_count) == 20
    assert fetcher.lang_calls == ["kk", "ru"]


def test_process_document_entry_404_stores_nothing(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=404404"
    fetcher = StubFetcher({}, status_codes={url: 404})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    from db.models import Document
    assert db_session.execute(Document.__table__.select()).fetchone() is None
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


def test_run_marks_broken_entry_as_error_and_continues_processing_others(database_url, monkeypatch):
    ru_html = (FIXTURES / "document_with_comments.html").read_text(encoding="utf-8")
    kk_html = (FIXTURES / "document_with_comments_kk.html").read_text(encoding="utf-8")

    bad_url = "https://legalacts.egov.kz/npa/view?id=99999999"
    good_url = "https://legalacts.egov.kz/npa/view?id=15906353"

    _, SessionLocal = create_engine_and_session_factory(database_url)
    seed_session = SessionLocal()
    queue.enqueue(seed_session, bad_url, "document", "2020-01-01T00:00:00+00:00", section="npa")
    queue.enqueue(seed_session, good_url, "document", "2020-01-01T00:00:01+00:00", section="npa")
    seed_session.close()

    fetcher = FlakyStubFetcher({good_url: [ru_html, kk_html]}, fail_urls={bad_url})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(database_url, limit=2)

    check_session = SessionLocal()
    from db.models import CrawlQueueEntry, Document

    bad_row = check_session.get(CrawlQueueEntry, bad_url)
    assert bad_row.status == "error"
    assert bad_row.last_error

    good_row = check_session.get(CrawlQueueEntry, good_url)
    assert good_row.status == "done"

    doc = check_session.execute(
        Document.__table__.select().where(Document.external_id == 15906353)
    ).fetchone()
    assert doc is not None
    assert doc.status == "Архив"

    failed_doc = check_session.execute(
        Document.__table__.select().where(Document.external_id == 99999999)
    ).fetchone()
    assert failed_doc is None
    check_session.close()


def test_run_marks_404_document_entry_done_not_error(database_url, monkeypatch):
    url = "https://legalacts.egov.kz/npa/view?id=404404"

    _, SessionLocal = create_engine_and_session_factory(database_url)
    seed_session = SessionLocal()
    queue.enqueue(seed_session, url, "document", "2020-01-01T00:00:00+00:00", section="npa")
    seed_session.close()

    fetcher = StubFetcher({}, status_codes={url: 404})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(database_url, limit=1)

    check_session = SessionLocal()
    from db.models import CrawlQueueEntry, Document
    row = check_session.get(CrawlQueueEntry, url)
    assert row.status == "done"
    assert row.last_error is None
    assert check_session.execute(Document.__table__.select()).fetchone() is None
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
    entry.processed_at = "2020-01-01T00:00:00+00:00"
    session.commit()
    session.close()

    run_module.run(database_url, limit=1)

    assert fetcher.calls.count(seed_url) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/pytest tests/test_run.py -v`
Expected: FAIL (`run()` still takes a SQLite path; `process_list_entry`/`process_document_entry` still expect `sqlite3.Connection`).

- [ ] **Step 3: Rewrite `backend/scraper/run.py`**

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

SEED_LIST_URLS = [
    ("npa", f"{BASE_URL}/list"),
    ("npa", f"{BASE_URL}/list?status=IN_ARCHIVE"),
    ("kdrp", f"{BASE_URL}/list?types[0]=7001&types[1]=7002"),
    ("arv", f"{BASE_URL}/Arvlist"),
    ("arv", f"{BASE_URL}/Arvlist?status=IN_ARCHIVE"),
    ("withdraw", f"{BASE_URL}/application/withdraw"),
]


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def seed_queue(session):
    discovered = now_iso()
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

    discovered = now_iso()
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

    timestamp = now_iso()
    document_id = store.upsert_document(session, external_id, section, url, fields, timestamp)
    store.upsert_comments(session, document_id, parsed_comments, timestamp)


def run(database_url, limit=None):
    engine, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()

    has_pending = (
        queue.next_pending(session, "list") is not None
        or queue.next_pending(session, "document") is not None
    )
    if not has_pending:
        seed_queue(session)

    stale_threshold = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=STALE_AFTER_DAYS)
    ).isoformat()
    queue.requeue_stale_documents(session, stale_threshold)
    queue.requeue_stale_lists(session, stale_threshold)

    fetcher = Fetcher(USER_AGENT)
    processed = 0

    while limit is None or processed < limit:
        list_url = queue.next_pending(session, "list")
        if list_url is not None:
            section = queue.section_for(session, list_url) or "npa"
            try:
                process_list_entry(session, fetcher, list_url, section=section)
                queue.mark_done(session, list_url, now_iso())
            except Exception as exc:
                queue.mark_error(session, list_url, str(exc), now_iso())
            processed += 1
            continue

        document_url = queue.next_pending(session, "document")
        if document_url is not None:
            section = queue.section_for(session, document_url) or "npa"
            try:
                process_document_entry(session, fetcher, document_url, section=section)
                queue.mark_done(session, document_url, now_iso())
            except Exception as exc:
                queue.mark_error(session, document_url, str(exc), now_iso())
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/pytest tests/test_run.py -v`
Expected: PASS

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/pytest -v`
Expected: all tests PASS (parser/fetch tests untouched, db/queue/store/run tests now on Postgres).

- [ ] **Step 6: Commit**

```bash
git add backend/scraper/run.py backend/tests/test_run.py
git commit -m "feat: port crawl orchestration to SQLAlchemy sessions"
```

---

### Task 6: Worker process (scheduled crawl loop)

**Files:**
- Create: `backend/worker/__init__.py` (empty)
- Create: `backend/worker/loop.py`
- Create: `backend/tests/test_worker_loop.py`

**Interfaces:**
- Consumes: `scraper.run.run(database_url, limit=None)` (Task 5).
- Produces: `worker.loop.main(sleep_func=time.sleep)` — reads `DATABASE_URL`, `SCRAPE_INTERVAL_SECONDS` (default `3600`), `WORKER_LIMIT` (optional) from the environment.

- [ ] **Step 1: Write the failing test**

```python
import pytest

from worker import loop as loop_module


class StopLoop(Exception):
    pass


def test_main_calls_run_then_sleeps_with_configured_interval(monkeypatch):
    calls = []

    def fake_run(database_url, limit=None):
        calls.append(("run", database_url, limit))

    def fake_sleep(seconds):
        calls.append(("sleep", seconds))
        raise StopLoop()

    monkeypatch.setenv("DATABASE_URL", "postgresql://test/db")
    monkeypatch.setenv("SCRAPE_INTERVAL_SECONDS", "42")
    monkeypatch.setenv("WORKER_LIMIT", "10")
    monkeypatch.setattr(loop_module, "run", fake_run)

    with pytest.raises(StopLoop):
        loop_module.main(sleep_func=fake_sleep)

    assert calls == [("run", "postgresql://test/db", 10), ("sleep", 42)]


def test_main_defaults_limit_to_none_when_unset(monkeypatch):
    calls = []

    def fake_run(database_url, limit=None):
        calls.append(("run", database_url, limit))

    def fake_sleep(seconds):
        calls.append(("sleep", seconds))
        raise StopLoop()

    monkeypatch.setenv("DATABASE_URL", "postgresql://test/db")
    monkeypatch.delenv("SCRAPE_INTERVAL_SECONDS", raising=False)
    monkeypatch.delenv("WORKER_LIMIT", raising=False)
    monkeypatch.setattr(loop_module, "run", fake_run)

    with pytest.raises(StopLoop):
        loop_module.main(sleep_func=fake_sleep)

    assert calls == [("run", "postgresql://test/db", None), ("sleep", 3600)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/pytest tests/test_worker_loop.py -v`
Expected: FAIL (`worker` package doesn't exist yet).

- [ ] **Step 3: Write `backend/worker/loop.py`**

```python
import os
import time

from scraper.run import run


def main(sleep_func=time.sleep):
    database_url = os.environ["DATABASE_URL"]
    interval = int(os.environ.get("SCRAPE_INTERVAL_SECONDS", "3600"))
    limit_raw = os.environ.get("WORKER_LIMIT")
    limit = int(limit_raw) if limit_raw else None

    while True:
        run(database_url, limit=limit)
        sleep_func(interval)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/pytest tests/test_worker_loop.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/worker backend/tests/test_worker_loop.py
git commit -m "feat: add scheduled scrape worker loop"
```

---

### Task 7: FastAPI settings, DB session dependency, API-key auth

**Files:**
- Create: `backend/app/__init__.py` (empty)
- Create: `backend/app/config.py`
- Create: `backend/app/deps.py`
- Create: `backend/tests/test_config.py`
- Create: `backend/tests/test_deps.py`

**Interfaces:**
- Produces: `Settings` (pydantic-settings model with `database_url: str`, `api_key: str`) from `app.config`; `get_db(request) -> Iterator[Session]`, `require_api_key(request, x_api_key)` from `app.deps` (both expect `request.app.state.settings` and, for `get_db`, `request.app.state.session_factory` to be set — done by `create_app()` in Task 12).

- [ ] **Step 1: Write the failing test in `backend/tests/test_config.py`**

```python
from app.config import Settings


def test_settings_reads_database_url_and_api_key_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("API_KEY", "secret123")

    settings = Settings()

    assert settings.database_url == "postgresql://u:p@h/db"
    assert settings.api_key == "secret123"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/pytest tests/test_config.py -v`
Expected: FAIL (`app.config` doesn't exist).

- [ ] **Step 3: Write `backend/app/config.py`**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    api_key: str
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Write the failing test in `backend/tests/test_deps.py`**

```python
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.deps import require_api_key


def _make_test_app(api_key):
    app = FastAPI()
    app.state.settings = Settings(database_url="postgresql://unused/db", api_key=api_key)

    @app.get("/protected", dependencies=[Depends(require_api_key)])
    def protected():
        return {"ok": True}

    return app


def test_require_api_key_rejects_missing_header():
    client = TestClient(_make_test_app("expected-key"))
    assert client.get("/protected").status_code == 422


def test_require_api_key_rejects_wrong_key():
    client = TestClient(_make_test_app("expected-key"))
    response = client.get("/protected", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_require_api_key_accepts_correct_key():
    client = TestClient(_make_test_app("expected-key"))
    response = client.get("/protected", headers={"X-API-Key": "expected-key"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/pytest tests/test_deps.py -v`
Expected: FAIL (`app.deps` doesn't exist).

- [ ] **Step 7: Write `backend/app/deps.py`**

```python
from typing import Iterator

from fastapi import Header, HTTPException, Request, status
from sqlalchemy.orm import Session


def get_db(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def require_api_key(request: Request, x_api_key: str = Header(...)) -> None:
    if x_api_key != request.app.state.settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/pytest tests/test_deps.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/__init__.py backend/app/config.py backend/app/deps.py backend/tests/test_config.py backend/tests/test_deps.py
git commit -m "feat: add FastAPI settings, DB session dependency, API-key auth"
```

---

### Task 8: `app.main.create_app()` and `/health`

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/tests/test_main.py`
- Modify: `backend/tests/conftest.py` (add `api_client` fixture)

**Interfaces:**
- Consumes: `Settings` (Task 7), `create_engine_and_session_factory` (Task 2).
- Produces: `create_app(settings=None) -> FastAPI`. Sets `app.state.settings`, `app.state.session_factory`, mounts `/health`. Later tasks add `app.include_router(...)` calls here.

- [ ] **Step 1: Write the failing test in `backend/tests/test_main.py`**

```python
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_endpoint_works_without_api_key(database_url):
    app = create_app(Settings(database_url=database_url, api_key="unused"))
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/pytest tests/test_main.py -v`
Expected: FAIL (`app.main` doesn't exist).

- [ ] **Step 3: Write `backend/app/main.py`**

```python
from fastapi import FastAPI

from app.config import Settings
from db.session import create_engine_and_session_factory


def create_app(settings=None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="legalacts backend")

    _, session_factory = create_engine_and_session_factory(settings.database_url)
    app.state.settings = settings
    app.state.session_factory = session_factory

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
```

`app = create_app()` at import time is only exercised by `uvicorn app.main:app` in the container, where `DATABASE_URL`/`API_KEY` are always set; it is never imported by tests (tests always call `create_app(settings)` explicitly with a testcontainers URL).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 5: Add the `api_client` fixture to `backend/tests/conftest.py`**

```python
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def api_client(database_url):
    settings = Settings(database_url=database_url, api_key="test-key")
    app = create_app(settings)
    client = TestClient(app)
    client.headers.update({"X-API-Key": "test-key"})
    return client
```

(Add this alongside the existing imports/fixtures from Task 2 — `pytest` and `Path`/`sys` are already imported at the top of the file.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/tests/test_main.py backend/tests/conftest.py
git commit -m "feat: add FastAPI app factory with /health endpoint"
```

---

### Task 9: `GET /documents` and `GET /documents/{id}`

**Files:**
- Create: `backend/app/schemas/__init__.py` (empty)
- Create: `backend/app/schemas/documents.py`
- Create: `backend/app/routers/__init__.py` (empty)
- Create: `backend/app/routers/documents.py`
- Modify: `backend/app/main.py` (register router)
- Create: `backend/tests/test_documents_router.py`

**Interfaces:**
- Consumes: `Document`, `Comment` (Task 2), `get_db`/`require_api_key` (Task 7), `api_client`/`database_url` fixtures (Tasks 2, 8).
- Produces: `router` (`APIRouter`, prefix `/documents`) exported from `app.routers.documents`, included by `create_app()`.

- [ ] **Step 1: Write the failing tests in `backend/tests/test_documents_router.py`**

```python
from db.models import Comment, Document
from db.session import create_engine_and_session_factory


def _seed_document(database_url, **overrides):
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    defaults = dict(
        external_id=1, section="npa", url="https://example.test/1",
        title_ru="Title", status="active",
        first_seen_at="2026-09-01T00:00:00+00:00",
        last_checked_at="2026-09-01T00:00:00+00:00",
    )
    defaults.update(overrides)
    document = Document(**defaults)
    session.add(document)
    session.commit()
    document_id = document.id
    session.close()
    return document_id


def test_list_documents_filters_by_section(database_url, api_client):
    _seed_document(database_url, external_id=1, section="npa", url="https://example.test/1")
    _seed_document(database_url, external_id=2, section="arv", url="https://example.test/2")

    response = api_client.get("/documents", params={"section": "arv"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["section"] == "arv"


def test_get_document_returns_404_for_missing_id(api_client):
    response = api_client.get("/documents/999999")
    assert response.status_code == 404


def test_get_document_includes_comments(database_url, api_client):
    document_id = _seed_document(database_url, external_id=3, section="npa", url="https://example.test/3")
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    session.add(Comment(
        document_id=document_id, external_comment_id=10, body="text",
        first_seen_at="2026-09-01T00:00:00+00:00",
    ))
    session.commit()
    session.close()

    response = api_client.get(f"/documents/{document_id}")

    assert response.status_code == 200
    body = response.json()
    assert len(body["comments"]) == 1
    assert body["comments"][0]["body"] == "text"


def test_documents_endpoint_requires_api_key(database_url):
    from app.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app(Settings(database_url=database_url, api_key="expected-key"))
    client = TestClient(app)

    assert client.get("/documents").status_code in (401, 422)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/pytest tests/test_documents_router.py -v`
Expected: FAIL (`app.routers.documents` doesn't exist, not registered).

- [ ] **Step 3: Write `backend/app/schemas/documents.py`**

```python
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
    first_seen_at: str
    last_checked_at: str


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
    first_seen_at: str


class DocumentDetailOut(DocumentListItemOut):
    comments: list[CommentOut]
```

- [ ] **Step 4: Write `backend/app/routers/documents.py`**

```python
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db, require_api_key
from app.schemas.documents import DocumentDetailOut, DocumentListItemOut
from db.models import Document

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(require_api_key)])

PAGE_SIZE = 20


@router.get("", response_model=list[DocumentListItemOut])
def list_documents(
    section: Optional[str] = None,
    status_filter: Optional[str] = None,
    page: int = 1,
    db: Session = Depends(get_db),
):
    stmt = select(Document)
    if section is not None:
        stmt = stmt.where(Document.section == section)
    if status_filter is not None:
        stmt = stmt.where(Document.status == status_filter)
    stmt = stmt.order_by(Document.id).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    return db.execute(stmt).scalars().all()


@router.get("/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: int, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document
```

`status_filter` (not `status`) avoids shadowing FastAPI's own `status` module used elsewhere in the app; the query parameter itself is still named `status` for API consumers via `Query(alias="status")` — see Step 4a.

- [ ] **Step 4a: Add the query alias so the URL parameter is `status`, not `status_filter`**

Modify the `list_documents` signature in `backend/app/routers/documents.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
```

```python
    status_filter: Optional[str] = Query(default=None, alias="status"),
```

- [ ] **Step 5: Register the router in `backend/app/main.py`**

```python
from app.routers import documents
```

```python
    app.include_router(documents.router)
```

Insert this line right after `app.state.session_factory = session_factory` and before the `/health` route definition.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/pytest tests/test_documents_router.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas backend/app/routers/documents.py backend/app/routers/__init__.py backend/app/main.py backend/tests/test_documents_router.py
git commit -m "feat: add GET /documents and GET /documents/{id}"
```

---

### Task 10: `GET /analytics/summary` and `GET /analytics/timeseries`

**Files:**
- Create: `backend/app/schemas/analytics.py`
- Create: `backend/app/routers/analytics.py`
- Modify: `backend/app/main.py` (register router)
- Create: `backend/tests/test_analytics_router.py`

**Interfaces:**
- Consumes: `Document`, `Comment` (Task 2), `get_db`/`require_api_key` (Task 7).
- Produces: `router` (`APIRouter`, prefix `/analytics`) exported from `app.routers.analytics`.

Scope note: `/analytics/timeseries` buckets by `first_seen_at` only (our own `now_iso()` output, guaranteed ISO-8601), not by `created_date` (free-text scraped from the source site in an unverified format — see `scraper/parsers/document_page.py`). Bucketing by `created_date` is deferred until its real format is confirmed against live data.

- [ ] **Step 1: Write the failing tests in `backend/tests/test_analytics_router.py`**

```python
from db.models import Comment, Document
from db.session import create_engine_and_session_factory


def _seed(database_url, documents, comments=()):
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    for doc in documents:
        session.add(Document(**doc))
    session.commit()
    for comment in comments:
        session.add(Comment(**comment))
    session.commit()
    session.close()


def test_analytics_summary_counts_by_section_and_status(database_url, api_client):
    _seed(database_url, [
        dict(external_id=1, section="npa", url="u1", status="active",
             first_seen_at="2026-09-01T00:00:00+00:00", last_checked_at="2026-09-01T00:00:00+00:00"),
        dict(external_id=2, section="npa", url="u2", status="archived",
             first_seen_at="2026-09-02T00:00:00+00:00", last_checked_at="2026-09-02T00:00:00+00:00"),
        dict(external_id=3, section="arv", url="u3", status="active",
             first_seen_at="2026-09-03T00:00:00+00:00", last_checked_at="2026-09-03T00:00:00+00:00"),
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
             first_seen_at="2026-09-01T10:00:00+00:00", last_checked_at="2026-09-01T10:00:00+00:00"),
        dict(external_id=2, section="npa", url="u2",
             first_seen_at="2026-09-01T18:00:00+00:00", last_checked_at="2026-09-01T18:00:00+00:00"),
        dict(external_id=3, section="npa", url="u3",
             first_seen_at="2026-09-02T09:00:00+00:00", last_checked_at="2026-09-02T09:00:00+00:00"),
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

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/pytest tests/test_analytics_router.py -v`
Expected: FAIL (`app.routers.analytics` doesn't exist).

- [ ] **Step 3: Write `backend/app/schemas/analytics.py`**

```python
from typing import Optional

from pydantic import BaseModel


class SectionCount(BaseModel):
    section: str
    count: int


class StatusCount(BaseModel):
    status: Optional[str]
    count: int


class AnalyticsSummaryOut(BaseModel):
    documents_by_section: list[SectionCount]
    documents_by_status: list[StatusCount]
    total_documents: int
    total_comments: int


class TimeseriesPoint(BaseModel):
    bucket: str
    count: int
```

- [ ] **Step 4: Write `backend/app/routers/analytics.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import TIMESTAMP, func, select
from sqlalchemy.orm import Session

from app.deps import get_db, require_api_key
from app.schemas.analytics import AnalyticsSummaryOut, SectionCount, StatusCount, TimeseriesPoint
from db.models import Comment, Document

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(require_api_key)])


@router.get("/summary", response_model=AnalyticsSummaryOut)
def analytics_summary(db: Session = Depends(get_db)):
    by_section = db.execute(
        select(Document.section, func.count(Document.id)).group_by(Document.section)
    ).all()
    by_status = db.execute(
        select(Document.status, func.count(Document.id)).group_by(Document.status)
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

    bucket = func.date_trunc(interval, Document.first_seen_at.cast(TIMESTAMP(timezone=True)))
    stmt = (
        select(bucket.label("bucket"), func.count(Document.id))
        .group_by("bucket")
        .order_by("bucket")
    )
    rows = db.execute(stmt).all()
    return [TimeseriesPoint(bucket=bucket_value.isoformat(), count=count) for bucket_value, count in rows]
```

- [ ] **Step 5: Register the router in `backend/app/main.py`**

```python
from app.routers import analytics, documents
```

```python
    app.include_router(documents.router)
    app.include_router(analytics.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/pytest tests/test_analytics_router.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/analytics.py backend/app/routers/analytics.py backend/app/main.py backend/tests/test_analytics_router.py
git commit -m "feat: add analytics summary and timeseries endpoints"
```

---

### Task 11: `GET /crawl/status`

**Files:**
- Create: `backend/app/schemas/crawl.py`
- Create: `backend/app/routers/crawl.py`
- Modify: `backend/app/main.py` (register router)
- Create: `backend/tests/test_crawl_router.py`

**Interfaces:**
- Consumes: `CrawlQueueEntry` (Task 2), `get_db`/`require_api_key` (Task 7).
- Produces: `router` (`APIRouter`, prefix `/crawl`) exported from `app.routers.crawl`.

- [ ] **Step 1: Write the failing tests in `backend/tests/test_crawl_router.py`**

```python
from db.models import CrawlQueueEntry
from db.session import create_engine_and_session_factory


def _seed(database_url, entries):
    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    for entry in entries:
        session.add(CrawlQueueEntry(**entry))
    session.commit()
    session.close()


def test_crawl_status_reports_counts_by_page_type_and_status(database_url, api_client):
    _seed(database_url, [
        dict(url="u1", page_type="document", status="done", discovered_at="2026-09-01T00:00:00+00:00", processed_at="2026-09-01T01:00:00+00:00"),
        dict(url="u2", page_type="document", status="pending", discovered_at="2026-09-01T00:00:00+00:00"),
        dict(url="u3", page_type="list", status="error", last_error="timeout", discovered_at="2026-09-01T00:00:00+00:00", processed_at="2026-09-01T02:00:00+00:00"),
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

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/pytest tests/test_crawl_router.py -v`
Expected: FAIL (`app.routers.crawl` doesn't exist).

- [ ] **Step 3: Write `backend/app/schemas/crawl.py`**

```python
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
    processed_at: Optional[str] = None


class CrawlStatusOut(BaseModel):
    counts: list[CrawlStatusCountOut]
    last_processed_at: Optional[str] = None
    recent_errors: list[CrawlErrorOut]
```

- [ ] **Step 4: Write `backend/app/routers/crawl.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_db, require_api_key
from app.schemas.crawl import CrawlErrorOut, CrawlStatusCountOut, CrawlStatusOut
from db.models import CrawlQueueEntry

router = APIRouter(prefix="/crawl", tags=["crawl"], dependencies=[Depends(require_api_key)])

ERROR_LIMIT = 20


@router.get("/status", response_model=CrawlStatusOut)
def crawl_status(db: Session = Depends(get_db)):
    counts = db.execute(
        select(CrawlQueueEntry.page_type, CrawlQueueEntry.status, func.count(CrawlQueueEntry.url))
        .group_by(CrawlQueueEntry.page_type, CrawlQueueEntry.status)
    ).all()
    last_processed_at = db.execute(select(func.max(CrawlQueueEntry.processed_at))).scalar_one()
    errors = db.execute(
        select(CrawlQueueEntry)
        .where(CrawlQueueEntry.status == "error")
        .order_by(CrawlQueueEntry.processed_at.desc())
        .limit(ERROR_LIMIT)
    ).scalars().all()

    return CrawlStatusOut(
        counts=[CrawlStatusCountOut(page_type=pt, status=st, count=c) for pt, st, c in counts],
        last_processed_at=last_processed_at,
        recent_errors=[
            CrawlErrorOut(url=e.url, page_type=e.page_type, last_error=e.last_error, processed_at=e.processed_at)
            for e in errors
        ],
    )
```

- [ ] **Step 5: Register the router in `backend/app/main.py`**

```python
from app.routers import analytics, crawl, documents
```

```python
    app.include_router(documents.router)
    app.include_router(analytics.router)
    app.include_router(crawl.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/pytest tests/test_crawl_router.py -v`
Expected: PASS

- [ ] **Step 7: Run the full backend test suite**

Run: `cd backend && .venv/Scripts/pytest -v`
Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/crawl.py backend/app/routers/crawl.py backend/app/main.py backend/tests/test_crawl_router.py
git commit -m "feat: add GET /crawl/status"
```

---

### Task 12: Dockerfile and docker-compose

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`
- Create: `docker-compose.yml`
- Create: `.env.example`

**Interfaces:**
- Produces: a buildable `backend` image runnable as either `api` or `worker`; a `docker-compose.yml` wiring `db`, `api`, `worker`.

- [ ] **Step 1: Write `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write `backend/.dockerignore`**

```
.venv/
__pycache__/
*.pyc
tests/
.pytest_cache/
```

- [ ] **Step 3: Write `.env.example` at the repo root**

```
POSTGRES_DB=legalacts
POSTGRES_USER=legalacts
POSTGRES_PASSWORD=change-me
DATABASE_URL=postgresql://legalacts:change-me@db:5432/legalacts
API_KEY=change-me-too
SCRAPE_INTERVAL_SECONDS=3600
WORKER_LIMIT=
```

- [ ] **Step 4: Write `docker-compose.yml` at the repo root**

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10

  api:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    environment:
      DATABASE_URL: ${DATABASE_URL}
      API_KEY: ${API_KEY}
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy

  worker:
    build: ./backend
    command: python -m worker.loop
    environment:
      DATABASE_URL: ${DATABASE_URL}
      SCRAPE_INTERVAL_SECONDS: ${SCRAPE_INTERVAL_SECONDS}
      WORKER_LIMIT: ${WORKER_LIMIT}
    depends_on:
      db:
        condition: service_healthy

volumes:
  pgdata:
```

- [ ] **Step 5: Build and start the stack, verify manually**

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
curl http://localhost:8000/health
curl -H "X-API-Key: change-me-too" http://localhost:8000/crawl/status
docker compose logs worker --tail=50
```

Expected: `docker compose ps` shows `db`, `api`, `worker` all running/healthy; `/health` returns `{"status": "ok"}`; `/crawl/status` returns an empty-counts JSON body (no crawl has run yet, or the worker has already started seeding — either is fine, this just proves the API can reach Postgres); the worker log shows it invoking `run()`.

- [ ] **Step 6: Tear down and commit**

```bash
docker compose down
git add backend/Dockerfile backend/.dockerignore docker-compose.yml .env.example
git commit -m "feat: containerize backend api and worker with docker-compose"
```

---

### Task 13: Update root CLAUDE.md for the new structure

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the `## Setup`, `## Commands`, and `## Architecture` sections**

Replace the existing `Setup`/`Commands`/`Architecture` sections (which describe the pre-split root-level `scraper/`/`tests/`/`requirements.txt` layout) with a version reflecting:
- `backend/` now holds the scraper, storage layer, and FastAPI app; setup/test commands run from inside `backend/` (`cd backend && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt`, `.venv/Scripts/pytest -v`).
- Storage is PostgreSQL via SQLAlchemy (`backend/db/models.py`, `backend/db/session.py`), not SQLite — note that DB-touching tests require Docker (testcontainers spins up `postgres:16-alpine`).
- `backend/scraper/run.py`'s `run(database_url, limit=None)` now takes a Postgres connection string (`DATABASE_URL` env var, or `--database-url` override), not a SQLite file path.
- `backend/worker/loop.py` runs the scrape on a schedule (`SCRAPE_INTERVAL_SECONDS`); `backend/app/` is the FastAPI read API (`/documents`, `/analytics/*`, `/crawl/status`, `/health`), authenticated via `X-API-Key`.
- `docker compose up --build` at the repo root runs the whole stack (`db`, `api`, `worker`); `frontend` will be added in a later stage (see `docs/superpowers/plans/` for the frontend plan once it exists).
- Point at both specs: `docs/superpowers/specs/2026-09-15-legalacts-scraper-design.md` (original scraper design) and `docs/superpowers/specs/2026-09-18-backend-postgres-fastapi-design.md` (this backend split).

Keep the "Известные ограничения" section's scraper-level facts (comments_total vs parsed comments, robots.txt handling, USER_AGENT ASCII constraint) — those are unchanged by this migration.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for backend/ split (Postgres+SQLAlchemy+FastAPI)"
```

---

## Self-Review Notes

- **Spec coverage:** §1 structure → Task 1; §2 models → Task 2; §3 storage/orchestration → Tasks 3-5; §4 FastAPI endpoints → Tasks 9-11 (all five endpoints plus `/health` from Task 8); §5 worker → Task 6; §6 Docker/compose → Task 12; §7 testing (testcontainers, parser tests untouched) → woven into Tasks 2-11 via the `db_session`/`database_url`/`api_client` fixtures. §8 (decisions log) has no dedicated task — it's a rationale record, not a deliverable.
- **Type consistency checked:** `run(database_url, limit=None)` signature is identical across Task 5's implementation, Task 6's worker, and Task 8/9/10/11's test fixtures (`database_url` fixture value passed straight through). `create_engine_and_session_factory` return order `(engine, session_factory)` is consistent everywhere it's called. Router prefixes (`/documents`, `/analytics`, `/crawl`) match the spec's endpoint table.
- **Known scope trim (flagged inline, Task 10):** `/analytics/timeseries` only buckets by `first_seen_at`, not `created_date` — the latter's real-world text format from the source site isn't verified against live data.
