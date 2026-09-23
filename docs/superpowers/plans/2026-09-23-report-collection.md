# Report Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect the raw HTML of a legal act's discussion-result report (`/report?id=<external_id>`) into a new `Report` table, when the current document page links to one.

**Architecture:** New `Report` model + Alembic migration on top of the existing schema (after `DocumentVersion`). `document_page.py` gets a `parse_report_link()` function. `run.py`'s `process_document_entry` checks for the link after comment channels and the version-history chain, fetching and storing the report's raw HTML once, never re-fetching it on later crawls.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x, Alembic, BeautifulSoup+lxml, pytest + testcontainers (postgres:16-alpine).

**Spec:** `docs/superpowers/specs/2026-09-23-report-collection-design.md`

## Global Constraints

- `Report` rows are insert-once — a report never changes once published, so if a row already exists for a `legal_act_id`, never re-fetch `/report` for it again.
- Only raw HTML is collected (`raw_html_ru`) — no parsing of the report's table rows into structured comment/reply pairs in this plan.
- `section == "arv"` skips the report check entirely — that template never links to a report.
- No `content_sha256`/change-detection columns on `Report` — nothing to detect, it's insert-once.
- A missing report link (discussion not yet concluded) must not cause any request or error — silently skip.
- A 404 on the report fetch must not store anything.

---

### Task 1: `Report` schema + Alembic migration

**Files:**
- Modify: `backend/db/models.py`
- Create: `backend/alembic/versions/0003_reports.py`
- Modify: `backend/tests/test_db.py`
- Test: `backend/tests/test_db.py`

**Interfaces:**
- Produces: ORM class `Report(id, legal_act_id, raw_html_ru, first_seen_at)`, `LegalAct.report` relationship (`uselist=False` — at most one report per act). Consumed by Task 3 (`store.py`).

- [ ] **Step 1: Write the failing test — add to `backend/tests/test_db.py`**

Change the table-set assertion in `test_migration_creates_expected_tables` from:

```python
def test_migration_creates_expected_tables(pg_engine):
    tables = set(inspect(pg_engine).get_table_names())
    assert {
        "legal_acts", "comments", "crawl_queue",
        "government_bodies", "act_types", "legal_act_snapshots", "document_versions",
    }.issubset(tables)
```

to:

```python
def test_migration_creates_expected_tables(pg_engine):
    tables = set(inspect(pg_engine).get_table_names())
    assert {
        "legal_acts", "comments", "crawl_queue",
        "government_bodies", "act_types", "legal_act_snapshots", "document_versions", "reports",
    }.issubset(tables)
```

And add a new test at the end of the file:

```python
def test_reports_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("reports")}
    assert columns == {"id", "legal_act_id", "raw_html_ru", "first_seen_at"}
```

Run: `cd backend && .venv/Scripts/pytest tests/test_db.py -v` (PowerShell + `$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"` + `dangerouslyDisableSandbox: true` — DB-touching tests on this machine only work that way)
Expected: FAIL — table `reports` does not exist yet.

- [ ] **Step 2: Add `Report` to `backend/db/models.py`**

Add this class after `DocumentVersion` (before `CrawlQueueEntry`):

```python
class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True)
    legal_act_id = Column(Integer, ForeignKey("legal_acts.id"), nullable=False, unique=True)
    raw_html_ru = Column(Text)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)

    legal_act = relationship("LegalAct", back_populates="report")
```

Add the reverse relationship to `LegalAct`, right after the existing `document_versions = relationship(...)` block:

```python
    report = relationship("Report", back_populates="legal_act", uselist=False)
```

- [ ] **Step 3: Create `backend/alembic/versions/0003_reports.py`**

```python
"""reports: raw HTML of discussion result reports via /report

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legal_act_id", sa.Integer(), sa.ForeignKey("legal_acts.id"), nullable=False),
        sa.Column("raw_html_ru", sa.Text()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("legal_act_id", name="uq_reports_legal_act_id"),
    )


def downgrade():
    op.drop_table("reports")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd backend && .venv/Scripts/pytest tests/test_db.py -v`
Expected: all `test_db.py` tests PASS, including the new one.

- [ ] **Step 5: Commit**

```bash
git add backend/db/models.py backend/alembic/versions/0003_reports.py backend/tests/test_db.py
git commit -m "feat: add Report schema for discussion report collection"
```

---

### Task 2: Parser — `parse_report_link`

**Files:**
- Modify: `backend/scraper/parsers/document_page.py`
- Modify: `backend/tests/test_document_page.py`
- Test: `backend/tests/test_document_page.py` (no DB needed — pure HTML parsing, plain `pytest`)

**Interfaces:**
- Produces: `document_page.parse_report_link(html) -> str | None`. Consumed by Task 4 (`run.py`).

- [ ] **Step 1: Write the failing tests — add to `backend/tests/test_document_page.py`**

```python
def test_parse_report_link_returns_href_when_present():
    html = '<div class="view-npa"><h2>Test</h2><a href="/report?id=15906353">Посмотреть отчет</a></div>'
    assert document_page.parse_report_link(html) == "/report?id=15906353"


def test_parse_report_link_returns_none_when_absent():
    html = '<div class="view-npa"><h2>Test</h2></div>'
    assert document_page.parse_report_link(html) is None
```

Run: `cd backend && .venv/Scripts/pytest tests/test_document_page.py -v`
Expected: FAIL with `AttributeError: module 'document_page' has no attribute 'parse_report_link'`.

- [ ] **Step 2: Add to `backend/scraper/parsers/document_page.py`**

Append this function at the end of the file:

```python
def parse_report_link(html):
    soup = BeautifulSoup(html, "lxml")
    link = soup.select_one('a[href^="/report?id="]')
    return link["href"] if link else None
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/pytest tests/test_document_page.py -v`
Expected: all PASS, including all pre-existing tests.

- [ ] **Step 4: Commit**

```bash
git add backend/scraper/parsers/document_page.py backend/tests/test_document_page.py
git commit -m "feat: parse_report_link for discussion report pages"
```

---

### Task 3: Storage layer — `report_exists`, `upsert_report`

**Files:**
- Modify: `backend/scraper/store.py`
- Modify: `backend/tests/test_store.py`
- Test: `backend/tests/test_store.py`

**Interfaces:**
- Consumes: `db.models.Report` from Task 1.
- Produces: `store.report_exists(session, legal_act_id) -> bool`, `store.upsert_report(session, legal_act_id, raw_html_ru, now)`. Consumed by Task 4 (`run.py`).

- [ ] **Step 1: Write the failing tests — add to `backend/tests/test_store.py`**

```python
def test_report_exists_returns_false_before_insert_and_true_after(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    assert store.report_exists(db_session, legal_act_id) is False

    store.upsert_report(db_session, legal_act_id, "<html>report</html>", T1)
    assert store.report_exists(db_session, legal_act_id) is True


def test_upsert_report_stores_raw_html_and_first_seen_at(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)

    store.upsert_report(db_session, legal_act_id, "<html>report</html>", T1)

    from db.models import Report
    row = db_session.query(Report).filter_by(legal_act_id=legal_act_id).one()
    assert row.raw_html_ru == "<html>report</html>"
    assert row.first_seen_at == T1
```

Run: `cd backend && .venv/Scripts/pytest tests/test_store.py -v` (PowerShell + `DOCKER_HOST`)
Expected: FAIL — `store.report_exists`/`store.upsert_report` don't exist yet.

- [ ] **Step 2: Add to `backend/scraper/store.py`**

Change the import line at the top from:

```python
from db.models import ActType, Comment, DocumentVersion, GovernmentBody, LegalAct, LegalActSnapshot
```

to:

```python
from db.models import ActType, Comment, DocumentVersion, GovernmentBody, LegalAct, LegalActSnapshot, Report
```

Append these two functions at the end of the file:

```python
def report_exists(session, legal_act_id):
    return session.execute(
        select(Report.id).where(Report.legal_act_id == legal_act_id)
    ).scalar_one_or_none() is not None


def upsert_report(session, legal_act_id, raw_html_ru, now):
    session.add(Report(legal_act_id=legal_act_id, raw_html_ru=raw_html_ru, first_seen_at=now))
    session.commit()
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/pytest tests/test_store.py -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/scraper/store.py backend/tests/test_store.py
git commit -m "feat: report_exists / upsert_report storage functions"
```

---

### Task 4: Scraper orchestration — collect the report in `run.py`

**Files:**
- Modify: `backend/scraper/run.py`
- Modify: `backend/tests/test_run.py`
- Test: `backend/tests/test_run.py`

**Interfaces:**
- Consumes: `document_page.parse_report_link` (Task 2), `store.report_exists` / `store.upsert_report` (Task 3).

- [ ] **Step 1: Write the failing tests — add to `backend/tests/test_run.py`**

Add after `test_process_document_entry_skips_version_chain_for_arv_section` (before `test_process_document_entry_404_stores_nothing`):

```python
def test_process_document_entry_collects_report_when_link_present(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    report_url = "https://legalacts.egov.kz/report?id=15906353"

    main_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<div class="blog-info"><span class="gov-parent">Main Body</span></div>'
        '<small><b>Статус:</b> Архив</small>'
        '<a href="/report?id=15906353">Посмотреть отчет</a>'
        '</div>'
    )
    report_html = "<html>report content</html>"

    fetcher = StubFetcher({url: main_html, report_url: report_html})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    from db.models import LegalAct, Report
    act = db_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 15906353)
    ).fetchone()
    report = db_session.execute(
        Report.__table__.select().where(Report.legal_act_id == act.id)
    ).fetchone()
    assert report is not None
    assert report.raw_html_ru == report_html


def test_process_document_entry_does_not_refetch_existing_report(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    report_url = "https://legalacts.egov.kz/report?id=15906353"

    main_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<div class="blog-info"><span class="gov-parent">Main Body</span></div>'
        '<a href="/report?id=15906353">Посмотреть отчет</a>'
        '</div>'
    )
    fetcher = StubFetcher({url: main_html, report_url: "<html>report</html>"})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")
    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    assert fetcher.calls.count(report_url) == 1


def test_process_document_entry_skips_report_when_no_link(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=15906353"

    main_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<div class="blog-info"><span class="gov-parent">Main Body</span></div>'
        '</div>'
    )
    fetcher = StubFetcher({url: main_html})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    from db.models import Report
    assert db_session.execute(Report.__table__.select()).fetchall() == []
    assert not any("/report?id=" in call_url for call_url in fetcher.calls)


def test_process_document_entry_skips_report_for_arv_section(db_session):
    ru_html = (FIXTURES / "document_arv_conclusion.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/npa/viewArvConclusion?id=99999"
    fetcher = StubFetcher({url: [ru_html, ru_html]})

    run_module.process_document_entry(db_session, fetcher, url, section="arv")

    assert not any("/report?id=" in call_url for call_url in fetcher.calls)


def test_report_fetch_404_does_not_store_anything(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    report_url = "https://legalacts.egov.kz/report?id=15906353"

    main_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<div class="blog-info"><span class="gov-parent">Main Body</span></div>'
        '<a href="/report?id=15906353">Посмотреть отчет</a>'
        '</div>'
    )
    fetcher = StubFetcher({url: main_html}, status_codes={report_url: 404})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    from db.models import Report
    assert db_session.execute(Report.__table__.select()).fetchall() == []
```

Run: `cd backend && .venv/Scripts/pytest tests/test_run.py -v` (PowerShell + `DOCKER_HOST`)
Expected: the five new tests FAIL — `process_document_entry` doesn't check for a report link yet, so no `Report` rows are ever created and `fetcher.calls` never contains a `/report?id=` URL (the two "skip"/"404" tests trivially pass already, same pattern as the arv-skip tests for earlier features — the three "collect"/"no-refetch"/"404-empty" tests genuinely fail).

- [ ] **Step 2: Rewrite the relevant part of `backend/scraper/run.py`**

Change the end of `process_document_entry` from:

```python
        version_info = document_page.parse_version_info(ru_html)
        _collect_prior_versions(
            session, fetcher, legal_act_id, version_info["previous_version_url"], timestamp,
        )
```

to:

```python
        version_info = document_page.parse_version_info(ru_html)
        _collect_prior_versions(
            session, fetcher, legal_act_id, version_info["previous_version_url"], timestamp,
        )

        report_url = document_page.parse_report_link(ru_html)
        if report_url is not None and not store.report_exists(session, legal_act_id):
            report_response = fetcher.get(urljoin(BASE_URL, report_url))
            if report_response.status_code != 404:
                store.upsert_report(session, legal_act_id, report_response.text, timestamp)
```

(No import changes needed — `urljoin` is already imported for the version-chain feature.)

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/pytest tests/test_run.py -v`
Expected: all PASS.

- [ ] **Step 4: Run the full backend suite**

Run: `cd backend && .venv/Scripts/pytest -v`
Expected: all PASS (no regressions in other test files).

- [ ] **Step 5: Commit**

```bash
git add backend/scraper/run.py backend/tests/test_run.py
git commit -m "feat: collect discussion report when linked from a document page"
```

---

### Task 5: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:** None — documentation only.

- [ ] **Step 1: Update the storage-layer models bullet**

Find:

```
- `backend/db/models.py` — ORM-модели: `LegalAct` (корневая сущность, замена `Document`), нормализованные справочники `GovernmentBody`/`ActType` (get-or-create по имени; `LegalAct.government_body`/`LegalAct.doc_type` — `association_proxy` на их `.name`, поэтому внешний JSON-контракт API не меняется), `Comment` (поле `comment_channel` — какая из 8 вкладок экспертного участия, `typeComment`; уникальность `(legal_act_id, external_comment_id, comment_channel)`), `LegalActSnapshot` (история изменений + сырой HTML + SHA-256 — единственное место, где сырой HTML текущей версии вообще хранится, у `LegalAct` таких колонок нет), `DocumentVersion` (прошлые версии акта через `/application/viewcardhistory?id=<N>` — отдельное пространство id источника; insert-once, без детекции изменений, потому что версии по построению не меняются; собирается только на ru), `CrawlQueueEntry`. Внутренние временные поля (`first_seen_at`, `last_checked_at`, `captured_at`, `discovered_at`, `processed_at`) — `DateTime(timezone=True)` (UTC); поля, пришедшие с источника как текст (`created_date`, `discussion_end_date`, `commented_at_raw`), остаются строками — таймзона источника не подтверждена. Дизайн: `docs/superpowers/specs/2026-09-22-legalacts-data-model-design.md` (схема `LegalAct`), `docs/superpowers/specs/2026-09-23-document-version-history-design.md` (`DocumentVersion`).
```

Replace with:

```
- `backend/db/models.py` — ORM-модели: `LegalAct` (корневая сущность, замена `Document`), нормализованные справочники `GovernmentBody`/`ActType` (get-or-create по имени; `LegalAct.government_body`/`LegalAct.doc_type` — `association_proxy` на их `.name`, поэтому внешний JSON-контракт API не меняется), `Comment` (поле `comment_channel` — какая из 8 вкладок экспертного участия, `typeComment`; уникальность `(legal_act_id, external_comment_id, comment_channel)`), `LegalActSnapshot` (история изменений + сырой HTML + SHA-256 — единственное место, где сырой HTML текущей версии вообще хранится, у `LegalAct` таких колонок нет), `DocumentVersion` (прошлые версии акта через `/application/viewcardhistory?id=<N>` — отдельное пространство id источника; insert-once, без детекции изменений, потому что версии по построению не меняются; собирается только на ru), `Report` (сырой HTML отчёта об итогах обсуждения через `/report?id=<external_id акта>` — то же id, что у карточки, не отдельное пространство; insert-once, максимум одна запись на акт), `CrawlQueueEntry`. Внутренние временные поля (`first_seen_at`, `last_checked_at`, `captured_at`, `discovered_at`, `processed_at`) — `DateTime(timezone=True)` (UTC); поля, пришедшие с источника как текст (`created_date`, `discussion_end_date`, `commented_at_raw`), остаются строками — таймзона источника не подтверждена. Дизайн: `docs/superpowers/specs/2026-09-22-legalacts-data-model-design.md` (схема `LegalAct`), `docs/superpowers/specs/2026-09-23-document-version-history-design.md` (`DocumentVersion`), `docs/superpowers/specs/2026-09-23-report-collection-design.md` (`Report`).
```

- [ ] **Step 2: Update the `run.py` bullet**

Find:

```
- `backend/scraper/run.py` — оркестрация скрейпера: `process_list_entry`, `process_document_entry`, `run(database_url, limit=None)` (главный цикл: list-страницы обрабатываются раньше document-страниц), `main()` (CLI); внутренние переменные переименованы `document_id` → `legal_act_id` вслед за моделью, таймстемпы теперь реальные `datetime` (`scraper.run.now()`), а не ISO-строки. `process_document_entry` для разделов `npa`/`kdrp`/`withdraw` дополнительно обходит все 7 оставшихся вкладок экспертного участия (`EXPERT_COMMENT_CHANNELS = (1, 3, 4, 7, 8, 9, 10)`, по одному GET-запросу `url&typeComment=N` на канал — `_with_type_comment()`), сохраняя каждую под своим `comment_channel`; для `arv` эти запросы пропускаются (у раздела вообще нет вкладок комментариев, см. известные ограничения). После этого (тоже кроме `arv`) `process_document_entry` идёт по цепочке предыдущих версий акта через `/application/viewcardhistory?id=<N>` (`_collect_prior_versions`) — останавливается, как только доходит до уже сохранённой версии (`store.document_version_exists`), так что повторный обход не делает лишних запросов. Сетевые/разбор-ошибки на уровне одной записи очереди не останавливают весь обход — запись помечается `error`, цикл продолжается. `run()` вызывает `fetcher.set_language("ru")` сразу после создания `Fetcher`, до цикла очереди — без cookie `egovLang` сайт по умолчанию отдаёт казахскую версию, а без этого вызова первый документ каждого цикла `worker/loop.py` парсился бы из казахского HTML под видом русского.
```

Replace with:

```
- `backend/scraper/run.py` — оркестрация скрейпера: `process_list_entry`, `process_document_entry`, `run(database_url, limit=None)` (главный цикл: list-страницы обрабатываются раньше document-страниц), `main()` (CLI); внутренние переменные переименованы `document_id` → `legal_act_id` вслед за моделью, таймстемпы теперь реальные `datetime` (`scraper.run.now()`), а не ISO-строки. `process_document_entry` для разделов `npa`/`kdrp`/`withdraw` дополнительно обходит все 7 оставшихся вкладок экспертного участия (`EXPERT_COMMENT_CHANNELS = (1, 3, 4, 7, 8, 9, 10)`, по одному GET-запросу `url&typeComment=N` на канал — `_with_type_comment()`), сохраняя каждую под своим `comment_channel`; для `arv` эти запросы пропускаются (у раздела вообще нет вкладок комментариев, см. известные ограничения). После этого (тоже кроме `arv`) `process_document_entry` идёт по цепочке предыдущих версий акта через `/application/viewcardhistory?id=<N>` (`_collect_prior_versions`) — останавливается, как только доходит до уже сохранённой версии (`store.document_version_exists`), так что повторный обход не делает лишних запросов. Тем же принципом (кроме `arv`) — если на карточке есть ссылка на `/report?id=...` (появляется только после завершения обсуждения) и отчёт для акта ещё не сохранён, `process_document_entry` забирает и сохраняет его сырой HTML (`store.report_exists`/`store.upsert_report`); уже сохранённый отчёт повторно не запрашивается. Сетевые/разбор-ошибки на уровне одной записи очереди не останавливают весь обход — запись помечается `error`, цикл продолжается. `run()` вызывает `fetcher.set_language("ru")` сразу после создания `Fetcher`, до цикла очереди — без cookie `egovLang` сайт по умолчанию отдаёт казахскую версию, а без этого вызова первый документ каждого цикла `worker/loop.py` парсился бы из казахского HTML под видом русского.
```

- [ ] **Step 3: Verify no stale references remain**

Run: `grep -n "class Report\|upsert_report\|report_exists\|parse_report_link" CLAUDE.md`
Expected: at least 3 matches, confirming the edits landed.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document Report collection in CLAUDE.md"
```

---

### Task 6: Full-suite verification

**Files:** none (verification only).

- [ ] **Step 1: Run the entire backend test suite**

Run: `cd backend && .venv/Scripts/pytest -v` (PowerShell + `$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"` + `dangerouslyDisableSandbox: true`)
Expected: all tests PASS, output pristine (only pre-existing third-party deprecation warnings).

- [ ] **Step 2: If any test fails, fix the root cause in the relevant task's files, re-run Step 1, and commit the fix separately** (`git commit -m "fix: <what was wrong>"`) — do not consider this plan done until the full suite is green.
