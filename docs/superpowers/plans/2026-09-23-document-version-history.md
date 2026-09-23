# Document Version History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect the full version-history chain of a legal act via `/application/viewcardhistory?id=<N>` into a new `DocumentVersion` table, so prior drafts of an act are preserved, not just its current state.

**Architecture:** New `DocumentVersion` model + Alembic migration on top of the existing `LegalAct` schema. `document_page.py` gets a `government_body` fallback (viewcardhistory pages lack `.gov-parent`) and a new `parse_version_info()` function. `run.py`'s `process_document_entry` walks the version chain backward after processing the current version, stopping as soon as it hits an already-known `external_id`.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x, Alembic, BeautifulSoup+lxml, pytest + testcontainers (postgres:16-alpine).

**Spec:** `docs/superpowers/specs/2026-09-23-document-version-history-design.md`

## Global Constraints

- `DocumentVersion` rows are insert-once and never updated — prior versions are immutable historical records. Before fetching `viewcardhistory?id=<N>`, check `document_version_exists(external_id)`; if true, stop walking the chain (everything further back was already collected in a prior crawl).
- Only the `ru` variant of a version page is collected — no `kk` fetch, no `title_kk`/`raw_html_kk` columns.
- `section == "arv"` skips version-chain walking entirely — that template has no "Версия проекта" field.
- No `content_sha256`/change-detection columns on `DocumentVersion` — nothing to detect, it's insert-once.
- The `government_body` fallback (`.gov-parent` → label text `"Государственный орган НПА:"`) must not change behavior for the existing `.view-npa`/`.blog-item` templates, which already have `.gov-parent` — the fallback only fires when `.gov-parent` is absent.
- Attached-file metadata (`/application/downloadattfilehistory?id=...`) is out of scope for this plan.

---

### Task 1: `DocumentVersion` schema + Alembic migration

**Files:**
- Modify: `backend/db/models.py`
- Create: `backend/alembic/versions/0002_document_versions.py`
- Modify: `backend/tests/test_db.py`
- Test: `backend/tests/test_db.py`

**Interfaces:**
- Produces: ORM class `DocumentVersion(id, legal_act_id, external_id, version_number, title_ru, status, act_type_id, government_body_id, created_date, discussion_end_date, raw_html_ru, first_seen_at)`, `LegalAct.document_versions` relationship. Consumed by Task 3 (`store.py`).

- [ ] **Step 1: Write the failing test — add to `backend/tests/test_db.py`**

```python
def test_document_versions_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("document_versions")}
    assert columns == {
        "id", "legal_act_id", "external_id", "version_number", "title_ru",
        "status", "act_type_id", "government_body_id", "created_date",
        "discussion_end_date", "raw_html_ru", "first_seen_at",
    }
```

Run: `cd backend && .venv/Scripts/pytest tests/test_db.py -v` (PowerShell + `$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"` + `dangerouslyDisableSandbox: true` — DB-touching tests on this machine only work that way, see below)
Expected: FAIL — table `document_versions` does not exist yet.

- [ ] **Step 2: Add `DocumentVersion` to `backend/db/models.py`**

Add this class after `LegalActSnapshot` (before `CrawlQueueEntry`):

```python
class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint(
            "legal_act_id", "version_number",
            name="uq_document_version_legal_act_version_number",
        ),
        Index("ix_document_versions_legal_act_id", "legal_act_id"),
    )

    id = Column(Integer, primary_key=True)
    legal_act_id = Column(Integer, ForeignKey("legal_acts.id"), nullable=False)
    external_id = Column(Integer, nullable=False, unique=True)
    version_number = Column(Integer)
    title_ru = Column(String)
    status = Column(String)
    act_type_id = Column(Integer, ForeignKey("act_types.id"))
    government_body_id = Column(Integer, ForeignKey("government_bodies.id"))
    created_date = Column(String)
    discussion_end_date = Column(String)
    raw_html_ru = Column(Text)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)

    legal_act = relationship("LegalAct", back_populates="document_versions")
```

Add the reverse relationship to `LegalAct`, right after the existing `snapshots = relationship(...)` line:

```python
    document_versions = relationship(
        "DocumentVersion", back_populates="legal_act", order_by="DocumentVersion.version_number"
    )
```

- [ ] **Step 3: Create `backend/alembic/versions/0002_document_versions.py`**

```python
"""document_versions: history of prior document versions via viewcardhistory

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legal_act_id", sa.Integer(), sa.ForeignKey("legal_acts.id"), nullable=False),
        sa.Column("external_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer()),
        sa.Column("title_ru", sa.String()),
        sa.Column("status", sa.String()),
        sa.Column("act_type_id", sa.Integer(), sa.ForeignKey("act_types.id")),
        sa.Column("government_body_id", sa.Integer(), sa.ForeignKey("government_bodies.id")),
        sa.Column("created_date", sa.String()),
        sa.Column("discussion_end_date", sa.String()),
        sa.Column("raw_html_ru", sa.Text()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("external_id", name="uq_document_versions_external_id"),
        sa.UniqueConstraint(
            "legal_act_id", "version_number",
            name="uq_document_version_legal_act_version_number",
        ),
    )
    op.create_index(
        "ix_document_versions_legal_act_id", "document_versions", ["legal_act_id"]
    )


def downgrade():
    op.drop_index("ix_document_versions_legal_act_id", table_name="document_versions")
    op.drop_table("document_versions")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && .venv/Scripts/pytest tests/test_db.py -v` (same PowerShell + `DOCKER_HOST` incantation)
Expected: all `test_db.py` tests PASS, including the new one.

- [ ] **Step 5: Commit**

```bash
git add backend/db/models.py backend/alembic/versions/0002_document_versions.py backend/tests/test_db.py
git commit -m "feat: add DocumentVersion schema for document version history"
```

---

### Task 2: Parser changes — `government_body` fallback + `parse_version_info`

**Files:**
- Modify: `backend/scraper/parsers/document_page.py`
- Modify: `backend/tests/test_document_page.py`
- Test: `backend/tests/test_document_page.py` (no DB needed — pure HTML parsing, plain `pytest`, no Docker/PowerShell required)

**Interfaces:**
- Produces: `document_page.parse_version_info(html) -> {"version_number": int | None, "previous_version_url": str | None}`. `document_page.parse_document_page(html)`'s `government_body` value now falls back to label text when `.gov-parent` is absent. Consumed by Task 4 (`run.py`).

- [ ] **Step 1: Write the failing tests — add to `backend/tests/test_document_page.py`**

```python
def test_parse_document_page_falls_back_to_government_body_label_when_gov_parent_absent():
    html = (
        '<div class="view-npa"><h2>Test</h2>'
        '<small><b>Государственный орган НПА:</b> город Караганды</small>'
        '</div>'
    )
    data = document_page.parse_document_page(html)
    assert data["government_body"] == "город Караганды"


def test_parse_version_info_returns_number_and_previous_url_when_present():
    html = (
        '<div class="view-npa"><h2>Test</h2>'
        '<small><b>Версия проекта:</b> Версия 2 '
        '( <a href="/application/viewcardhistory?id=52440">Версия 1</a> )</small>'
        '</div>'
    )
    data = document_page.parse_version_info(html)
    assert data["version_number"] == 2
    assert data["previous_version_url"] == "/application/viewcardhistory?id=52440"


def test_parse_version_info_returns_none_url_for_earliest_version():
    html = (
        '<div class="view-npa"><h2>Test</h2>'
        '<small><b>Версия проекта:</b> Версия 1</small>'
        '</div>'
    )
    data = document_page.parse_version_info(html)
    assert data["version_number"] == 1
    assert data["previous_version_url"] is None


def test_parse_version_info_returns_none_when_field_absent():
    html = '<div class="view-npa"><h2>Test</h2></div>'
    data = document_page.parse_version_info(html)
    assert data["version_number"] is None
    assert data["previous_version_url"] is None
```

Run: `cd backend && .venv/Scripts/pytest tests/test_document_page.py -v`
Expected: the two new `government_body`/existing-suite tests still pass (no code change yet means the fallback test FAILs), and `parse_version_info` tests FAIL with `AttributeError: module 'document_page' has no attribute 'parse_version_info'`.

- [ ] **Step 2: Rewrite `backend/scraper/parsers/document_page.py`**

```python
import re

from bs4 import BeautifulSoup

LABEL_MAP = {
    "status": "Статус:",
    "doc_type": "Тип НПА:",
    "created_date": "Дата создания:",
    "discussion_end_date": "Публичное обсуждение до:",
}

GOVERNMENT_BODY_LABEL = "Государственный орган НПА:"
VERSION_LABEL = "Версия проекта:"
VERSION_NUMBER_RE = re.compile(r"Версия\s+(\d+)")


def _label_text(soup, label):
    for small in soup.select(".view-npa small, .blog-item small"):
        b = small.find("b")
        if b is not None and b.get_text(strip=True) == label:
            b.extract()
            return small.get_text(strip=True)
    return None


def _government_body(soup):
    el = soup.select_one(".blog-info .gov-parent")
    if el is not None:
        return el.get_text(strip=True)
    return _label_text(soup, GOVERNMENT_BODY_LABEL)


def _count_by_class_prefix(soup, prefix):
    span = soup.find("span", class_=re.compile("^" + re.escape(prefix)))
    if span is None:
        return 0
    text = span.get_text(strip=True)
    return int(text) if text.isdigit() else 0


def parse_document_page(html):
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one(".view-npa h2, .blog-item h2")
    title = title_el.get_text(strip=True) if title_el else None

    fields = {key: _label_text(soup, label) for key, label in LABEL_MAP.items()}

    government_body = _government_body(soup)

    comments_total = 0
    comments_icon = soup.select_one('.blog-info i[title="Всего комментариев"]')
    if comments_icon is not None:
        li = comments_icon.find_parent("li")
        match = re.search(r"\d+", li.get_text()) if li else None
        if match:
            comments_total = int(match.group())

    return {
        "title": title,
        "status": fields["status"],
        "doc_type": fields["doc_type"],
        "created_date": fields["created_date"],
        "discussion_end_date": fields["discussion_end_date"],
        "government_body": government_body,
        "comments_total": comments_total,
        "likes_count": _count_by_class_prefix(soup, "likeCount-"),
        "dislikes_count": _count_by_class_prefix(soup, "dislikeCount-"),
    }


def parse_version_info(html):
    soup = BeautifulSoup(html, "lxml")
    for small in soup.select(".view-npa small, .blog-item small"):
        b = small.find("b")
        if b is None or b.get_text(strip=True) != VERSION_LABEL:
            continue
        text = small.get_text(" ", strip=True)
        match = VERSION_NUMBER_RE.search(text)
        version_number = int(match.group(1)) if match else None
        link = small.find("a", href=True)
        previous_version_url = link["href"] if link else None
        return {"version_number": version_number, "previous_version_url": previous_version_url}
    return {"version_number": None, "previous_version_url": None}
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/pytest tests/test_document_page.py -v`
Expected: all PASS, including the 4 existing tests (`document_no_comments.html`/`document_with_comments.html`/`document_with_comments_kk.html`/`document_arv_conclusion.html` all have `.gov-parent`, so the fallback path is never exercised for them — behavior unchanged).

- [ ] **Step 4: Commit**

```bash
git add backend/scraper/parsers/document_page.py backend/tests/test_document_page.py
git commit -m "feat: government_body fallback + parse_version_info for version-history pages"
```

---

### Task 3: Storage layer — `document_version_exists`, `upsert_document_version`

**Files:**
- Modify: `backend/scraper/store.py`
- Modify: `backend/tests/test_store.py`
- Test: `backend/tests/test_store.py`

**Interfaces:**
- Consumes: `db.models.DocumentVersion` from Task 1.
- Produces: `store.document_version_exists(session, external_id) -> bool`, `store.upsert_document_version(session, legal_act_id, external_id, fields, version_number, now)` (`fields` keyed like `parse_document_page`'s output, plus a `raw_html_ru` key the caller adds — same convention `upsert_legal_act` already uses). Consumed by Task 4 (`run.py`).

- [ ] **Step 1: Write the failing tests — add to `backend/tests/test_store.py`**

```python
def test_document_version_exists_returns_false_before_insert_and_true_after(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    assert store.document_version_exists(db_session, 200) is False

    store.upsert_document_version(
        db_session, legal_act_id, 200,
        {"title": "V1 title", "status": None, "doc_type": "Решение",
         "government_body": "Body A", "created_date": "01/01/2020",
         "discussion_end_date": "01/02/2020", "raw_html_ru": "<html>v1</html>"},
        1, T1,
    )
    assert store.document_version_exists(db_session, 200) is True


def test_upsert_document_version_stores_fields_and_reuses_lookup_rows(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)

    store.upsert_document_version(
        db_session, legal_act_id, 200,
        {"title": "V1 title", "status": None, "doc_type": "DocType_Value_001",
         "government_body": "Body_Value_001", "created_date": "01/01/2020",
         "discussion_end_date": "01/02/2020", "raw_html_ru": "<html>v1</html>"},
        1, T1,
    )

    from db.models import ActType, DocumentVersion, GovernmentBody
    row = db_session.query(DocumentVersion).filter_by(external_id=200).one()
    assert row.legal_act_id == legal_act_id
    assert row.version_number == 1
    assert row.title_ru == "V1 title"
    assert row.status is None
    assert row.created_date == "01/01/2020"
    assert row.discussion_end_date == "01/02/2020"
    assert row.raw_html_ru == "<html>v1</html>"
    assert row.first_seen_at == T1

    # _fields() (used to create the parent legal act) already created these
    # lookup rows with the same names — must be reused, not duplicated.
    assert db_session.query(GovernmentBody).filter_by(name="Body_Value_001").count() == 1
    assert db_session.query(ActType).filter_by(name="DocType_Value_001").count() == 1
```

Run: `cd backend && .venv/Scripts/pytest tests/test_store.py -v` (PowerShell + `DOCKER_HOST`)
Expected: FAIL — `store.document_version_exists`/`store.upsert_document_version` don't exist yet.

- [ ] **Step 2: Add to `backend/scraper/store.py`**

Change the import line at the top from:

```python
from db.models import ActType, Comment, GovernmentBody, LegalAct, LegalActSnapshot
```

to:

```python
from db.models import ActType, Comment, DocumentVersion, GovernmentBody, LegalAct, LegalActSnapshot
```

Append these two functions at the end of the file:

```python
def document_version_exists(session, external_id):
    return session.execute(
        select(DocumentVersion.id).where(DocumentVersion.external_id == external_id)
    ).scalar_one_or_none() is not None


def upsert_document_version(session, legal_act_id, external_id, fields, version_number, now):
    government_body = _get_or_create(session, GovernmentBody, fields.get("government_body"))
    act_type = _get_or_create(session, ActType, fields.get("doc_type"))

    session.add(DocumentVersion(
        legal_act_id=legal_act_id,
        external_id=external_id,
        version_number=version_number,
        title_ru=fields.get("title"),
        status=fields.get("status"),
        act_type_id=act_type.id if act_type else None,
        government_body_id=government_body.id if government_body else None,
        created_date=fields.get("created_date"),
        discussion_end_date=fields.get("discussion_end_date"),
        raw_html_ru=fields.get("raw_html_ru"),
        first_seen_at=now,
    ))
    session.commit()
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/pytest tests/test_store.py -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/scraper/store.py backend/tests/test_store.py
git commit -m "feat: document_version_exists / upsert_document_version storage functions"
```

---

### Task 4: Scraper orchestration — walk the version chain in `run.py`

**Files:**
- Modify: `backend/scraper/run.py`
- Modify: `backend/tests/test_run.py`
- Test: `backend/tests/test_run.py`

**Interfaces:**
- Consumes: `document_page.parse_version_info` (Task 2), `store.document_version_exists` / `store.upsert_document_version` (Task 3).
- Produces: `run_module._collect_prior_versions(session, fetcher, legal_act_id, next_url, timestamp)` (internal helper, but named here since the tests reference behavior through `process_document_entry`, not this function directly).

- [ ] **Step 1: Write the failing tests — add to `backend/tests/test_run.py`**

Add near the other `process_document_entry` tests (after `test_process_document_entry_skips_expert_channels_for_arv_section`):

```python
def test_process_document_entry_collects_full_version_chain(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    version2_url = "https://legalacts.egov.kz/application/viewcardhistory?id=200"
    version1_url = "https://legalacts.egov.kz/application/viewcardhistory?id=100"

    main_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<div class="blog-info"><span class="gov-parent">Main Body</span></div>'
        '<small><b>Статус:</b> Архив</small>'
        '<small><b>Версия проекта:</b> Версия 3 '
        '( <a href="/application/viewcardhistory?id=200">Версия 2</a> )</small>'
        '</div>'
    )
    version2_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<small><b>Статус:</b></small>'
        '<small><b>Версия проекта:</b> Версия 2 '
        '( <a href="/application/viewcardhistory?id=100">Версия 1</a> )</small>'
        '<small><b>Государственный орган НПА:</b> Version2 Body</small>'
        '</div>'
    )
    version1_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<small><b>Статус:</b></small>'
        '<small><b>Версия проекта:</b> Версия 1</small>'
        '<small><b>Государственный орган НПА:</b> Version1 Body</small>'
        '</div>'
    )

    fetcher = StubFetcher({
        url: main_html,
        version2_url: version2_html,
        version1_url: version1_html,
    })

    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    from db.models import DocumentVersion, LegalAct
    act = db_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 15906353)
    ).fetchone()

    versions = db_session.execute(
        DocumentVersion.__table__.select()
        .where(DocumentVersion.legal_act_id == act.id)
        .order_by(DocumentVersion.version_number)
    ).fetchall()
    versions_by_external_id = {v.external_id: v for v in versions}
    assert versions_by_external_id[100].version_number == 1
    assert versions_by_external_id[200].version_number == 2

    from db.models import GovernmentBody
    v200_body = db_session.get(GovernmentBody, versions_by_external_id[200].government_body_id)
    assert v200_body.name == "Version2 Body"

    assert fetcher.calls.count(version2_url) == 1
    assert fetcher.calls.count(version1_url) == 1


def test_process_document_entry_does_not_refetch_known_versions_on_recrawl(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    version1_url = "https://legalacts.egov.kz/application/viewcardhistory?id=100"

    main_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<div class="blog-info"><span class="gov-parent">Main Body</span></div>'
        '<small><b>Версия проекта:</b> Версия 2 '
        '( <a href="/application/viewcardhistory?id=100">Версия 1</a> )</small>'
        '</div>'
    )
    version1_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<small><b>Версия проекта:</b> Версия 1</small>'
        '</div>'
    )

    fetcher = StubFetcher({url: main_html, version1_url: version1_html})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")
    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    assert fetcher.calls.count(version1_url) == 1


def test_process_document_entry_skips_version_chain_for_arv_section(db_session):
    ru_html = (FIXTURES / "document_arv_conclusion.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/npa/viewArvConclusion?id=99999"
    fetcher = StubFetcher({url: [ru_html, ru_html]})

    run_module.process_document_entry(db_session, fetcher, url, section="arv")

    assert not any("viewcardhistory" in call_url for call_url in fetcher.calls)
```

Run: `cd backend && .venv/Scripts/pytest tests/test_run.py -v` (PowerShell + `DOCKER_HOST`)
Expected: the three new tests FAIL — `process_document_entry` doesn't walk the version chain yet, so no `DocumentVersion` rows are created and `fetcher.calls` never contains the `viewcardhistory` URLs (for the first two tests, the assertions checking those URLs *were* called will fail with `0 == 1`; the third test trivially passes since nothing calls `viewcardhistory` yet — same pattern as the expert-channels feature's arv test).

- [ ] **Step 2: Rewrite `backend/scraper/run.py`**

Change the import line at the top from:

```python
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
```

to:

```python
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
```

Add this function after `_with_type_comment` (before `process_list_entry`):

```python
def _collect_prior_versions(session, fetcher, legal_act_id, next_url, timestamp):
    while next_url is not None:
        full_url = urljoin(BASE_URL, next_url)
        external_id = int(dict(parse_qsl(urlsplit(full_url).query))["id"])
        if store.document_version_exists(session, external_id):
            return
        response = fetcher.get(full_url)
        html = response.text
        fields = document_page.parse_document_page(html)
        fields["raw_html_ru"] = html
        version_info = document_page.parse_version_info(html)
        store.upsert_document_version(
            session, legal_act_id, external_id, fields, version_info["version_number"], timestamp,
        )
        next_url = version_info["previous_version_url"]
```

In `process_document_entry`, change the end of the function from:

```python
    timestamp = now()
    legal_act_id = store.upsert_legal_act(session, external_id, section, url, fields, timestamp)
    store.upsert_comments(session, legal_act_id, parsed_comments, DEFAULT_COMMENT_CHANNEL, timestamp)

    if section != "arv":
        for channel in EXPERT_COMMENT_CHANNELS:
            channel_response = fetcher.get(_with_type_comment(url, channel))
            channel_comments = comments_parser.parse_comments(channel_response.text)
            store.upsert_comments(session, legal_act_id, channel_comments, channel, timestamp)
```

to:

```python
    timestamp = now()
    legal_act_id = store.upsert_legal_act(session, external_id, section, url, fields, timestamp)
    store.upsert_comments(session, legal_act_id, parsed_comments, DEFAULT_COMMENT_CHANNEL, timestamp)

    if section != "arv":
        for channel in EXPERT_COMMENT_CHANNELS:
            channel_response = fetcher.get(_with_type_comment(url, channel))
            channel_comments = comments_parser.parse_comments(channel_response.text)
            store.upsert_comments(session, legal_act_id, channel_comments, channel, timestamp)

        version_info = document_page.parse_version_info(ru_html)
        _collect_prior_versions(
            session, fetcher, legal_act_id, version_info["previous_version_url"], timestamp,
        )
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/pytest tests/test_run.py -v`
Expected: all PASS.

- [ ] **Step 4: Run the full backend suite**

Run: `cd backend && .venv/Scripts/pytest -v`
Expected: all PASS (no regressions in the other test files).

- [ ] **Step 5: Commit**

```bash
git add backend/scraper/run.py backend/tests/test_run.py
git commit -m "feat: walk version-history chain when processing a document"
```

---

### Task 5: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:** None — documentation only.

- [ ] **Step 1: Update the storage-layer models bullet**

Find (in the `**Слой хранилища (PostgreSQL via SQLAlchemy):**` bullet list):

```
- `backend/db/models.py` — ORM-модели: `LegalAct` (корневая сущность, замена `Document`), нормализованные справочники `GovernmentBody`/`ActType` (get-or-create по имени; `LegalAct.government_body`/`LegalAct.doc_type` — `association_proxy` на их `.name`, поэтому внешний JSON-контракт API не меняется), `Comment` (поле `comment_channel` — какая из 8 вкладок экспертного участия, `typeComment`; уникальность `(legal_act_id, external_comment_id, comment_channel)`), `LegalActSnapshot` (история изменений + сырой HTML + SHA-256 — единственное место, где сырой HTML вообще хранится, у `LegalAct` таких колонок нет), `CrawlQueueEntry`. Внутренние временные поля (`first_seen_at`, `last_checked_at`, `captured_at`, `discovered_at`, `processed_at`) — `DateTime(timezone=True)` (UTC); поля, пришедшие с источника как текст (`created_date`, `discussion_end_date`, `commented_at_raw`), остаются строками — таймзона источника не подтверждена. Дизайн: `docs/superpowers/specs/2026-09-22-legalacts-data-model-design.md`.
```

Replace with:

```
- `backend/db/models.py` — ORM-модели: `LegalAct` (корневая сущность, замена `Document`), нормализованные справочники `GovernmentBody`/`ActType` (get-or-create по имени; `LegalAct.government_body`/`LegalAct.doc_type` — `association_proxy` на их `.name`, поэтому внешний JSON-контракт API не меняется), `Comment` (поле `comment_channel` — какая из 8 вкладок экспертного участия, `typeComment`; уникальность `(legal_act_id, external_comment_id, comment_channel)`), `LegalActSnapshot` (история изменений + сырой HTML + SHA-256 — единственное место, где сырой HTML текущей версии вообще хранится, у `LegalAct` таких колонок нет), `DocumentVersion` (прошлые версии акта через `/application/viewcardhistory?id=<N>` — отдельное пространство id источника; insert-once, без детекции изменений, потому что версии по построению не меняются; собирается только на ru), `CrawlQueueEntry`. Внутренние временные поля (`first_seen_at`, `last_checked_at`, `captured_at`, `discovered_at`, `processed_at`) — `DateTime(timezone=True)` (UTC); поля, пришедшие с источника как текст (`created_date`, `discussion_end_date`, `commented_at_raw`), остаются строками — таймзона источника не подтверждена. Дизайн: `docs/superpowers/specs/2026-09-22-legalacts-data-model-design.md` (схема `LegalAct`), `docs/superpowers/specs/2026-09-23-document-version-history-design.md` (`DocumentVersion`).
```

- [ ] **Step 2: Update the parsers bullet**

Find:

```
- `backend/scraper/parsers/list_page.py`, `document_page.py`, `comments.py` — разбор HTML через BeautifulSoup+lxml по селекторам, подтверждённым на реальных страницах сайта (фикстуры в `backend/tests/fixtures/`). `document_page.py` понимает два шаблона карточки: `.view-npa` (`/npa/view`, разделы `npa`/`kdrp`) и `.blog-item` (`/npa/viewArvConclusion`, раздел `arv`) — селекторы объединены (`.view-npa h2, .blog-item h2` и т.д.), т.к. на первом шаблоне класс `blog-item` висит на пустом `<br>` и конфликта не возникает.
```

Replace with:

```
- `backend/scraper/parsers/list_page.py`, `document_page.py`, `comments.py` — разбор HTML через BeautifulSoup+lxml по селекторам, подтверждённым на реальных страницах сайта (фикстуры в `backend/tests/fixtures/`). `document_page.py` понимает два шаблона карточки: `.view-npa` (`/npa/view`, разделы `npa`/`kdrp`) и `.blog-item` (`/npa/viewArvConclusion`, раздел `arv`) — селекторы объединены (`.view-npa h2, .blog-item h2` и т.д.), т.к. на первом шаблоне класс `blog-item` висит на пустом `<br>` и конфликта не возникает. `government_body` сначала берётся из `<span class="gov-parent">`, а если его нет (страницы `/application/viewcardhistory` — версии-снапшоты) — из метки `«Государственный орган НПА:»`. `parse_version_info()` вытаскивает номер версии и ссылку на предыдущую версию из метки `«Версия проекта:»`, используется и для текущей карточки, и рекурсивно для каждой найденной версии.
```

- [ ] **Step 3: Update the `run.py` bullet**

Find:

```
- `backend/scraper/run.py` — оркестрация скрейпера: `process_list_entry`, `process_document_entry`, `run(database_url, limit=None)` (главный цикл: list-страницы обрабатываются раньше document-страниц), `main()` (CLI); внутренние переменные переименованы `document_id` → `legal_act_id` вслед за моделью, таймстемпы теперь реальные `datetime` (`scraper.run.now()`), а не ISO-строки. `process_document_entry` для разделов `npa`/`kdrp`/`withdraw` дополнительно обходит все 7 оставшихся вкладок экспертного участия (`EXPERT_COMMENT_CHANNELS = (1, 3, 4, 7, 8, 9, 10)`, по одному GET-запросу `url&typeComment=N` на канал — `_with_type_comment()`), сохраняя каждую под своим `comment_channel`; для `arv` эти запросы пропускаются (у раздела вообще нет вкладок комментариев, см. известные ограничения). Сетевые/разбор-ошибки на уровне одной записи очереди не останавливают весь обход — запись помечается `error`, цикл продолжается. `run()` вызывает `fetcher.set_language("ru")` сразу после создания `Fetcher`, до цикла очереди — без cookie `egovLang` сайт по умолчанию отдаёт казахскую версию, а без этого вызова первый документ каждого цикла `worker/loop.py` парсился бы из казахского HTML под видом русского.
```

Replace with:

```
- `backend/scraper/run.py` — оркестрация скрейпера: `process_list_entry`, `process_document_entry`, `run(database_url, limit=None)` (главный цикл: list-страницы обрабатываются раньше document-страниц), `main()` (CLI); внутренние переменные переименованы `document_id` → `legal_act_id` вслед за моделью, таймстемпы теперь реальные `datetime` (`scraper.run.now()`), а не ISO-строки. `process_document_entry` для разделов `npa`/`kdrp`/`withdraw` дополнительно обходит все 7 оставшихся вкладок экспертного участия (`EXPERT_COMMENT_CHANNELS = (1, 3, 4, 7, 8, 9, 10)`, по одному GET-запросу `url&typeComment=N` на канал — `_with_type_comment()`), сохраняя каждую под своим `comment_channel`; для `arv` эти запросы пропускаются (у раздела вообще нет вкладок комментариев, см. известные ограничения). После этого (тоже кроме `arv`) `process_document_entry` идёт по цепочке предыдущих версий акта через `/application/viewcardhistory?id=<N>` (`_collect_prior_versions`) — останавливается, как только доходит до уже сохранённой версии (`store.document_version_exists`), так что повторный обход не делает лишних запросов. Сетевые/разбор-ошибки на уровне одной записи очереди не останавливают весь обход — запись помечается `error`, цикл продолжается. `run()` вызывает `fetcher.set_language("ru")` сразу после создания `Fetcher`, до цикла очереди — без cookie `egovLang` сайт по умолчанию отдаёт казахскую версию, а без этого вызова первый документ каждого цикла `worker/loop.py` парсился бы из казахского HTML под видом русского.
```

- [ ] **Step 4: Verify no stale references remain**

Run: `grep -n "DocumentVersion\|viewcardhistory" CLAUDE.md`
Expected: at least 2 matches (the two bullets edited above), confirming both edits landed.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document DocumentVersion and version-chain walking in CLAUDE.md"
```

---

### Task 6: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the entire backend test suite**

Run: `cd backend && .venv/Scripts/pytest -v` (PowerShell + `$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"` + `dangerouslyDisableSandbox: true`)
Expected: all tests PASS, output pristine (only the 3 pre-existing third-party deprecation warnings).

- [ ] **Step 2: If any test fails, fix the root cause in the relevant task's files, re-run Step 1, and commit the fix separately** (`git commit -m "fix: <what was wrong>"`) — do not consider this plan done until the full suite is green.
