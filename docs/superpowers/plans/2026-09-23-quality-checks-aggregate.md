# Aggregate Quality Checks (Этап 2, группа B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Закрыть последние два пункта раздела 22.3 продуктового ТЗ:
падение `totalPages` источника относительно последнего известного
значения (без порога) и обнаружение новых статусов/HTML-структур.

**Architecture:** Три независимых механизма поверх уже существующей
таблицы `quality_events`: (1) `list_page_totals` — baseline последнего
известного `totalPages` на списочный URL, сравнение и событие при
уменьшении, встраивается в `process_list_entry`/`process_category_list_entry`;
(2) `known_status_values` — реестр статусов, пятая проверка внутри уже
существующей `store._record_quality_events`; (3) флаг
`template_recognized` в `document_page.parse_document_page`, проверяется
в `process_document_entry` после `upsert_legal_act`. `QualityEvent.legal_act_id`
становится nullable — падение `totalPages` не привязано к конкретному
акту.

**Tech Stack:** Python, SQLAlchemy 2.x, Alembic, BeautifulSoup+lxml,
pytest + testcontainers.

**Spec:** `docs/superpowers/specs/2026-09-23-quality-checks-aggregate-design.md`

## Global Constraints

- Падение `totalPages` фиксируется без порога — любое уменьшение
  относительно последнего известного значения для того же URL (решение
  владельца продукта 2026-09-23).
- `QualityEvent.legal_act_id` — nullable; событие `list_total_pages_decreased`
  всегда создаётся с `legal_act_id=None`. Все остальные типы событий
  (существующие из группы A и новые `new_status`/`unrecognized_html_structure`)
  по-прежнему всегда заполняют `legal_act_id`.
- Канонический URL для `list_page_totals` строится вызывающим кодом
  (`run.py`) через уже существующий `_set_page_param(url, 1)` — `store.py`
  не строит и не парсит URL сам (не импортирует `urlsplit`/`urlencode` для
  этой задачи), только принимает готовую строку-ключ. Это отличается от
  формулировки в спеке («функция сама приводит URL к page=1») — уточнение
  сделано на этапе планирования, чтобы не дублировать URL-логику `run.py`
  внутри `store.py` и не создавать циклический импорт (`run.py` уже
  импортирует `store`).
- Ничего не блокирует существующий обход — все три проверки только
  добавляют события/обновляют вспомогательные таблицы, не меняют
  сохранение актов/списков/комментариев.
- Никаких изменений в API v1 (`app/routers/*`, `app/schemas/*`).

---

### Task 1: Схема — nullable `QualityEvent.legal_act_id`, `KnownStatusValue`, `ListPageTotal`

**Files:**
- Modify: `backend/db/models.py`
- Create: `backend/alembic/versions/0007_quality_checks_aggregate.py`
- Modify: `backend/tests/test_db.py`

**Interfaces:**
- Produces: `QualityEvent.legal_act_id` nullable; `KnownStatusValue(id, value, first_seen_at)`; `ListPageTotal(id, url, total_pages, updated_at)` — используются в Task 3.

- [ ] **Step 1: Написать падающие тесты схемы**

Добавить в `backend/tests/test_db.py` (в конец файла):

```python
def test_quality_events_legal_act_id_is_nullable(db_session):
    columns = {col["name"]: col for col in inspect(db_session.bind).get_columns("quality_events")}
    assert columns["legal_act_id"]["nullable"] is True


def test_migration_creates_known_status_values_and_list_page_totals_tables(pg_engine):
    tables = set(inspect(pg_engine).get_table_names())
    assert {"known_status_values", "list_page_totals"}.issubset(tables)


def test_known_status_values_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("known_status_values")}
    assert columns == {"id", "value", "first_seen_at"}


def test_list_page_totals_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("list_page_totals")}
    assert columns == {"id", "url", "total_pages", "updated_at"}
```

- [ ] **Step 2: Запустить тесты, убедиться, что падают**

```powershell
$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"
.venv/Scripts/pytest tests/test_db.py -v -k "known_status_values or list_page_totals or quality_events_legal_act_id"
```

Ожидается: `nullable` тест падает (сейчас `NOT NULL`), таблицы не
существуют.

- [ ] **Step 3: Изменить `QualityEvent` и добавить новые модели в `backend/db/models.py`**

Изменить существующую строку в классе `QualityEvent`:

```python
    legal_act_id = Column(Integer, ForeignKey("legal_acts.id"), nullable=False)
```

на:

```python
    legal_act_id = Column(Integer, ForeignKey("legal_acts.id"))
```

Добавить после класса `QualityEvent` (перед `CrawlQueueEntry`):

```python
class KnownStatusValue(Base):
    __tablename__ = "known_status_values"

    id = Column(Integer, primary_key=True)
    value = Column(String, nullable=False, unique=True)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)


class ListPageTotal(Base):
    __tablename__ = "list_page_totals"

    id = Column(Integer, primary_key=True)
    url = Column(String, nullable=False, unique=True)
    total_pages = Column(Integer, nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: Создать Alembic-ревизию `backend/alembic/versions/0007_quality_checks_aggregate.py`**

```python
"""quality checks aggregate: nullable QualityEvent.legal_act_id, known_status_values, list_page_totals

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("quality_events", "legal_act_id", nullable=True)
    op.create_table(
        "known_status_values",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("value", name="uq_known_status_values_value"),
    )
    op.create_table(
        "list_page_totals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("total_pages", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("url", name="uq_list_page_totals_url"),
    )


def downgrade():
    op.drop_table("list_page_totals")
    op.drop_table("known_status_values")
    op.alter_column("quality_events", "legal_act_id", nullable=False)
```

- [ ] **Step 5: Запустить тесты, убедиться, что проходят**

```powershell
$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"
.venv/Scripts/pytest tests/test_db.py -v
```

- [ ] **Step 6: Коммит**

```bash
git add backend/db/models.py backend/alembic/versions/0007_quality_checks_aggregate.py backend/tests/test_db.py
git commit -m "feat: add KnownStatusValue/ListPageTotal schema, make QualityEvent.legal_act_id nullable"
```

---

### Task 2: `document_page.py` — флаг `template_recognized`

**Files:**
- Modify: `backend/scraper/parsers/document_page.py`
- Modify: `backend/tests/test_document_page.py`

**Interfaces:**
- Produces: `parse_document_page(html)` теперь включает ключ
  `template_recognized: bool` в возвращаемый словарь — используется в
  Task 4.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `backend/tests/test_document_page.py` (после
`test_parse_document_page_falls_back_to_government_body_label_when_gov_parent_absent`):

```python
def test_parse_document_page_reports_template_recognized_for_known_templates():
    data = document_page.parse_document_page(_read("document_no_comments.html"))
    assert data["template_recognized"] is True

    data_arv = document_page.parse_document_page(_read("document_arv_conclusion.html"))
    assert data_arv["template_recognized"] is True


def test_parse_document_page_reports_template_not_recognized_for_unknown_html():
    html = (
        '<html><body><div class="some-other-template">'
        '<h1>Not a known template</h1></div></body></html>'
    )
    data = document_page.parse_document_page(html)
    assert data["template_recognized"] is False
    assert data["title"] is None
```

- [ ] **Step 2: Запустить тесты, убедиться, что падают**

```powershell
.venv/Scripts/pytest tests/test_document_page.py -v -k template_recognized
```

Ожидается: `KeyError: 'template_recognized'`.

- [ ] **Step 3: Изменить `parse_document_page` в `backend/scraper/parsers/document_page.py`**

Изменить:

```python
def parse_document_page(html):
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one(".view-npa h2, .blog-item h2")
    title = title_el.get_text(strip=True) if title_el else None

    fields = {key: _label_text(soup, label) for key, label in LABEL_MAP.items()}
```

на:

```python
def parse_document_page(html):
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one(".view-npa h2, .blog-item h2")
    title = title_el.get_text(strip=True) if title_el else None
    template_recognized = title_el is not None

    fields = {key: _label_text(soup, label) for key, label in LABEL_MAP.items()}
```

И добавить ключ в возвращаемый словарь:

```python
    return {
        "title": title,
        "template_recognized": template_recognized,
        "status": fields["status"],
        "doc_type": fields["doc_type"],
        "created_date": fields["created_date"],
        "discussion_end_date": fields["discussion_end_date"],
        "government_body": government_body,
        "comments_total": comments_total,
        "likes_count": _count_by_class_prefix(soup, "likeCount-"),
        "dislikes_count": _count_by_class_prefix(soup, "dislikeCount-"),
    }
```

- [ ] **Step 4: Запустить тесты, убедиться, что проходят**

```powershell
.venv/Scripts/pytest tests/test_document_page.py -v
```

Убедиться, что все существующие тесты файла тоже проходят (новый ключ в
словаре не должен ничего сломать — ни один существующий тест не
проверяет словарь на равенство целиком, только отдельные ключи).

- [ ] **Step 5: Коммит**

```bash
git add backend/scraper/parsers/document_page.py backend/tests/test_document_page.py
git commit -m "feat: report whether document_page.parse_document_page recognized a known template"
```

---

### Task 3: `store.py` — три новые функции

**Files:**
- Modify: `backend/scraper/store.py`
- Modify: `backend/tests/test_store.py`

**Interfaces:**
- Consumes: `KnownStatusValue`, `ListPageTotal` из Task 1.
- Produces: `record_list_total_pages_change(session, url, total_pages, now)`,
  `record_unrecognized_html_structure(session, legal_act_id, template_recognized, now)`
  — используются в Task 4. Расширение существующей `_record_quality_events`
  (новая проверка `new_status`) — вызывается автоматически изнутри уже
  существующего `upsert_legal_act`, отдельного публичного интерфейса не
  создаёт.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `backend/tests/test_store.py` (в конец файла):

```python
def test_upsert_legal_act_records_new_status_event(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(status="Совершенно новый статус XYZ"), T1,
    )

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="new_status",
    ).all()
    assert len(events) == 1
    assert events[0].detail == "Совершенно новый статус XYZ"


def test_upsert_legal_act_does_not_record_new_status_event_for_known_status(db_session):
    store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(status="Status_Value_001"), T1,
    )
    legal_act_id_2 = store.upsert_legal_act(
        db_session, 2, "npa", "https://legalacts.egov.kz/npa/view?id=2",
        _fields(status="Status_Value_001"), T1,
    )

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id_2, event_type="new_status",
    ).count() == 0


def test_record_list_total_pages_change_first_call_creates_baseline_no_event(db_session):
    store.record_list_total_pages_change(db_session, "https://legalacts.egov.kz/list", 100, T1)

    from db.models import ListPageTotal, QualityEvent
    row = db_session.query(ListPageTotal).filter_by(url="https://legalacts.egov.kz/list").one()
    assert row.total_pages == 100
    assert db_session.query(QualityEvent).filter_by(event_type="list_total_pages_decreased").count() == 0


def test_record_list_total_pages_change_decrease_creates_event(db_session):
    store.record_list_total_pages_change(db_session, "https://legalacts.egov.kz/list", 100, T1)
    store.record_list_total_pages_change(db_session, "https://legalacts.egov.kz/list", 80, T2)

    from db.models import ListPageTotal, QualityEvent
    events = db_session.query(QualityEvent).filter_by(event_type="list_total_pages_decreased").all()
    assert len(events) == 1
    assert events[0].legal_act_id is None
    assert events[0].detail == "100 -> 80"

    row = db_session.query(ListPageTotal).filter_by(url="https://legalacts.egov.kz/list").one()
    assert row.total_pages == 80


def test_record_list_total_pages_change_increase_no_event(db_session):
    store.record_list_total_pages_change(db_session, "https://legalacts.egov.kz/list", 100, T1)
    store.record_list_total_pages_change(db_session, "https://legalacts.egov.kz/list", 150, T2)

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(event_type="list_total_pages_decreased").count() == 0


def test_record_list_total_pages_change_equal_no_event(db_session):
    store.record_list_total_pages_change(db_session, "https://legalacts.egov.kz/list", 100, T1)
    store.record_list_total_pages_change(db_session, "https://legalacts.egov.kz/list", 100, T2)

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(event_type="list_total_pages_decreased").count() == 0


def test_record_unrecognized_html_structure_creates_event_when_not_recognized(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1", _fields(), T1,
    )

    store.record_unrecognized_html_structure(db_session, legal_act_id, False, T1)

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="unrecognized_html_structure",
    ).all()
    assert len(events) == 1


def test_record_unrecognized_html_structure_no_event_when_recognized(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1", _fields(), T1,
    )

    store.record_unrecognized_html_structure(db_session, legal_act_id, True, T1)

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="unrecognized_html_structure",
    ).count() == 0
```

- [ ] **Step 2: Запустить тесты, убедиться, что падают**

```powershell
$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"
.venv/Scripts/pytest tests/test_store.py -v -k "new_status or list_total_pages or unrecognized_html_structure"
```

Ожидается: `AttributeError` на `record_list_total_pages_change`/
`record_unrecognized_html_structure`; `new_status`-тесты падают на
`assert len(events) == 1` (проверка ещё не добавлена в
`_record_quality_events`).

- [ ] **Step 3: Реализовать в `backend/scraper/store.py`**

Изменить импорт в начале файла:

```python
from db.models import (
    ActType, Category, Comment, DocumentVersion, GovernmentBody, KnownStatusValue,
    LegalAct, LegalActCategory, LegalActSnapshot, ListPageTotal, QualityEvent, Report,
)
```

Добавить пятую проверку в `_record_quality_events` (после блока
`counter_null_flip`, перед циклом `for event_type, field_name, detail in events:`):

```python
    status = values["status"]
    if status:
        known_status = session.execute(
            select(KnownStatusValue).where(KnownStatusValue.value == status)
        ).scalar_one_or_none()
        if known_status is None:
            session.add(KnownStatusValue(value=status, first_seen_at=now))
            events.append(("new_status", "status", status))
```

Добавить в конец файла:

```python
def record_list_total_pages_change(session, url, total_pages, now):
    existing = session.execute(
        select(ListPageTotal).where(ListPageTotal.url == url)
    ).scalar_one_or_none()

    if existing is not None and total_pages < existing.total_pages:
        session.add(QualityEvent(
            legal_act_id=None, event_type="list_total_pages_decreased",
            field_name="total_pages",
            detail=f"{existing.total_pages} -> {total_pages}",
            detected_at=now,
        ))

    if existing is not None:
        existing.total_pages = total_pages
        existing.updated_at = now
    else:
        session.add(ListPageTotal(url=url, total_pages=total_pages, updated_at=now))

    session.commit()


def record_unrecognized_html_structure(session, legal_act_id, template_recognized, now):
    if template_recognized:
        return
    session.add(QualityEvent(
        legal_act_id=legal_act_id, event_type="unrecognized_html_structure",
        field_name="title", detail="neither .view-npa nor .blog-item template matched",
        detected_at=now,
    ))
    session.commit()
```

- [ ] **Step 4: Запустить тесты, убедиться, что проходят**

```powershell
$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"
.venv/Scripts/pytest tests/test_store.py -v
```

Убедиться, что весь файл проходит, включая все существующие тесты
`upsert_legal_act` — они теперь дополнительно создают `new_status`
события при первом использовании каждого уникального значения `status`
в рамках теста (harmless побочный эффект, ни один существующий тест не
проверяет отсутствие `new_status`-событий).

- [ ] **Step 5: Коммит**

```bash
git add backend/scraper/store.py backend/tests/test_store.py
git commit -m "feat: add new_status check and list-totals/html-structure quality functions"
```

---

### Task 4: `run.py` — подключение трёх проверок

**Files:**
- Modify: `backend/scraper/run.py`
- Modify: `backend/tests/test_run.py`

**Interfaces:**
- Consumes: `store.record_list_total_pages_change` и
  `store.record_unrecognized_html_structure` из Task 3;
  `fields["template_recognized"]` из Task 2.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `backend/tests/test_run.py`:

Тест на падение `totalPages` — после `test_process_list_entry_stops_pagination_at_last_page`:

```python
def test_process_list_entry_records_total_pages_decrease(db_session):
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE"
    fetcher = StubFetcher({url: list_html})

    canonical_url = run_module._set_page_param(url, 1)
    store.record_list_total_pages_change(db_session, canonical_url, 99999, T1)

    run_module.process_list_entry(db_session, fetcher, url, section="npa")

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(event_type="list_total_pages_decreased").all()
    assert len(events) == 1
    assert events[0].detail == "99999 -> 29852"
```

Тест на `unrecognized_html_structure` — после
`test_process_document_entry_stores_document_and_comments`:

```python
def test_process_document_entry_records_unrecognized_html_structure(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    unknown_html = '<html><body><div class="totally-unknown-template"><h1>Nope</h1></div></body></html>'
    fetcher = StubFetcher({url: [unknown_html, unknown_html]})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    from db.models import LegalAct, QualityEvent
    act = db_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 15906353)
    ).fetchone()

    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=act.id, event_type="unrecognized_html_structure",
    ).all()
    assert len(events) == 1


def test_process_document_entry_does_not_record_unrecognized_html_structure_for_known_template(db_session):
    ru_html = (FIXTURES / "document_with_comments.html").read_text(encoding="utf-8")
    kk_html = (FIXTURES / "document_with_comments_kk.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    fetcher = StubFetcher({url: [ru_html, kk_html]})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    from db.models import LegalAct, QualityEvent
    act = db_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 15906353)
    ).fetchone()

    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=act.id, event_type="unrecognized_html_structure",
    ).count() == 0
```

- [ ] **Step 2: Запустить тесты, убедиться, что падают**

```powershell
$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"
.venv/Scripts/pytest tests/test_run.py -v -k "total_pages_decrease or unrecognized_html_structure"
```

Ожидается: `list_total_pages_decreased`-тест падает на `assert len(events)
== 1` (функция ещё не вызывается из `process_list_entry`);
`unrecognized_html_structure`-тесты падают аналогично (не вызывается из
`process_document_entry`); тест на "не создаёт событие" должен уже
проходить тривиально (событий и так нет, пока функция не вызывается) —
это ожидаемо и не блокирует переход к реализации, финальная проверка на
Step 4 подтвердит, что он продолжает проходить корректно (а не просто
случайно, потому что проверка ещё не подключена).

- [ ] **Step 3: Реализовать в `backend/scraper/run.py`**

В `process_list_entry`, после строки `total_pages =
list_page.parse_total_pages(html)`:

```python
    total_pages = list_page.parse_total_pages(html)
    store.record_list_total_pages_change(session, _set_page_param(url, 1), total_pages, discovered)
    current_page = _current_page(url)
```

В `process_category_list_entry`, после строки `total_pages =
list_page.parse_total_pages(html)`:

```python
    total_pages = list_page.parse_total_pages(html)
    store.record_list_total_pages_change(session, _set_page_param(url, 1), total_pages, discovered)
    current_page = _current_page(url)
```

В `process_document_entry`, сразу после строки `legal_act_id =
store.upsert_legal_act(session, external_id, section, url, fields,
timestamp)`:

```python
    legal_act_id = store.upsert_legal_act(session, external_id, section, url, fields, timestamp)
    store.record_unrecognized_html_structure(session, legal_act_id, fields.get("template_recognized"), timestamp)
    store.upsert_comments(session, legal_act_id, parsed_comments, DEFAULT_COMMENT_CHANNEL, timestamp)
```

- [ ] **Step 4: Запустить тесты, убедиться, что проходят**

```powershell
$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"
.venv/Scripts/pytest tests/test_run.py -v
```

Убедиться, что весь файл проходит — особое внимание существующим
тестам `process_list_entry`/`process_category_list_entry`/
`process_document_entry`, ни один из них не должен сломаться от двух
новых вызовов (они не меняют существующее поведение пагинации/upsert'а,
только добавляют независимые side-эффекты в новые таблицы).

- [ ] **Step 5: Прогнать весь backend-набор**

```powershell
$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"
.venv/Scripts/pytest -v
```

Ожидается: все тесты проходят (146 существующих + новые из Task 1–4).

- [ ] **Step 6: Коммит**

```bash
git add backend/scraper/run.py backend/tests/test_run.py
git commit -m "feat: wire aggregate quality checks into list/category/document processing"
```

---

### Task 5: Обновить `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md` (корень репо)

**Interfaces:** нет (документация).

- [ ] **Step 1: Обновить `## Architecture` в `CLAUDE.md`**

В разделе «Слой хранилища», в предложении про `QualityEvent`, заменить
формулировку «четырёх проверок» на «семи проверок» и дописать три новых
типа. Найти текущий текст (внутри абзаца про `backend/db/models.py`):

```text
`QualityEvent` (журнал аномалий, обнаруженных при `upsert_legal_act`: `invalid_url`, `invalid_date`, `end_before_start`, `counter_null_flip` — ничего не блокирует, только фиксируется рядом с обычным сохранением акта; без апсерта, каждое обнаружение — отдельная строка)
```

заменить на:

```text
`QualityEvent` (журнал аномалий: `invalid_url`, `invalid_date`, `end_before_start`, `counter_null_flip`, `new_status` — все пять при `upsert_legal_act`; `comments_total_mismatch` — при завершении сбора комментариев в `process_document_entry`; `unrecognized_html_structure` — там же, сразу после `upsert_legal_act`; `list_total_pages_decreased` — в `process_list_entry`/`process_category_list_entry`, не привязано к акту, `legal_act_id=NULL` — единственный тип события, где это так. Ничего не блокирует, только фиксируется рядом с обычным сохранением; без апсерта, каждое обнаружение — отдельная строка), `KnownStatusValue` (реестр всех когда-либо встреченных значений `status` — аналог get-or-create таблиц `GovernmentBody`/`ActType`/`Category`, но без FK-связи с `LegalAct`, `status` остаётся обычной строкой), `ListPageTotal` (последнее известное `totalPages` на списочный URL, канонизированный к `page=1`; используется только для сравнения при следующем обходе)
```

В разделе «Слой скрейпера», в абзаце про `store.py`, найти текст:

```text
`upsert_legal_act` также пишет `QualityEvent`-записи для четырёх проверок из раздела 22.3 продуктового ТЗ (группа A — на уровне одной записи): битый URL (`url` не начинается с `BASE_URL`), невалидная дата (`created_date`/`discussion_end_date` не парсятся форматом `DD/MM/YYYY`), конец обсуждения раньше начала, флип счётчика (`comments_total`/`likes_count`/`dislikes_count`) в/из `NULL` между последовательными обходами одного акта.
```

дописать в конец этого предложения (не заменяя остальное):

```text
, новое значение `status` (глобально впервые для всего датасета, сверяется с `known_status_values`).
```

И заменить следующее предложение (про `record_comments_total_mismatch`):

```text
Сравнение `comments_total` с фактически собранным числом комментариев реализовано отдельно — `store.record_comments_total_mismatch(session, legal_act_id, comments_total, now)`, вызывается из `run.py`'s `process_document_entry` после сбора всех каналов комментариев (не из `upsert_legal_act`, т.к. на момент upsert'а комментарии ещё не собраны); считает `Comment` по всем каналам для акта, пишет `QualityEvent(event_type="comments_total_mismatch")` при любом расхождении (без порога — решение о значимости за будущей группой B). Остальные проверки раздела 22.3 (резкое падение числа объектов; новые статусы/типы/категории/HTML-структуры) — группа B, агрегатные проверки по всему датасету, отдельный дизайн, не реализованы.
```

на:

```text
Сравнение `comments_total` с фактически собранным числом комментариев реализовано отдельно — `store.record_comments_total_mismatch(session, legal_act_id, comments_total, now)`, вызывается из `run.py`'s `process_document_entry` после сбора всех каналов комментариев (не из `upsert_legal_act`, т.к. на момент upsert'а комментарии ещё не собраны); считает `Comment` по всем каналам для акта, пишет `QualityEvent(event_type="comments_total_mismatch")` при любом расхождении (без порога). `store.record_unrecognized_html_structure(session, legal_act_id, template_recognized, now)` — там же, сразу после `upsert_legal_act`; `template_recognized` приходит от `document_page.parse_document_page` (`True`, если совпал `.view-npa` или `.blog-item`). `store.record_list_total_pages_change(session, url, total_pages, now)` — в `process_list_entry`/`process_category_list_entry`, сравнивает `total_pages` с последним известным для того же (канонизированного к `page=1`) URL в `list_page_totals`; при уменьшении пишет `QualityEvent` с `legal_act_id=None`, при любом исходе обновляет baseline на новое значение. Все три проверки — без порога и без исключений по разделу (`arv` не требует особой обработки: у него уже узнаваемый шаблон `.blog-item`). Раздел 22.3 продуктового ТЗ закрыт полностью, кроме `response time` (вне v1).
```

Обновить число тестов в `## Project status` (посчитать через `pytest -q`
после Task 1–4).

В разделе «Известные ограничения» добавить пункт:

```text
- `QualityEvent`: `list_total_pages_decreased` не различает «временную»
  просадку (например, сайт отдал неполную выдачу из-за собственной
  ошибки на один запрос) от устойчивого изменения — фиксируется каждое
  отдельное уменьшение независимо, включая одиночные флуктуации;
  `known_status_values`/`list_page_totals` не экспонируются через API v1
  в этой итерации.
```

- [ ] **Step 2: Коммит**

```bash
git add CLAUDE.md
git commit -m "docs: document aggregate quality checks in CLAUDE.md"
```
