# Record-Level Quality Checks (Этап 2, группа A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Фиксировать в БД (без блокировки сохранения) четыре вида аномалий,
обнаруженных при `upsert_legal_act`: битый URL, невалидная дата, конец
обсуждения раньше начала, флип счётчика в/из `NULL`.

**Architecture:** Новая таблица `quality_events` (лог, не апсерт — каждое
обнаружение отдельной строкой). Новая функция `store._record_quality_events`,
вызывается изнутри `store.upsert_legal_act` перед финальным `session.commit()`.
Ничего не блокируется: аномалия фиксируется рядом с обычным сохранением акта.

**Tech Stack:** Python, SQLAlchemy 2.x, Alembic, pytest + testcontainers.

**Spec:** `docs/superpowers/specs/2026-09-23-quality-checks-record-level-design.md`

## Global Constraints

- Ни одна из четырёх проверок не блокирует и не изменяет сохранение
  `LegalAct` — акт сохраняется как обычно независимо от найденных
  аномалий.
- `quality_events` — только вставка, без апсерта и без уникального
  констрейнта: каждое обнаружение (в т.ч. повторное на том же акте) —
  отдельная строка.
- Даты источника (`created_date`, `discussion_end_date`) хранятся как
  сырые строки в формате `DD/MM/YYYY` (подтверждено фикстурой
  `document_with_comments.html`: `"Дата создания:</b> 09/09/2026"`).
- Флип счётчика фиксируется в обе стороны (значение → `NULL` и
  `NULL` → значение), но не при первом сохранении акта (`existing is
  None`) — сравнивать не с чем.
- **Критично для реализации Task 2:** старое значение счётчика нужно
  захватить ДО того, как существующий код перезапишет `existing` через
  `setattr` в цикле `for key, value in values.items(): setattr(existing,
  key, value)` — иначе к моменту сравнения старое значение уже будет
  затёрто новым. Смотри точный порядок операций в Task 2.
- Никаких изменений в API v1 (`app/routers/*`, `app/schemas/*`) — эта
  итерация только про сбор данных, как и `DocumentVersion`/`Report`/`Category`.

---

### Task 1: Схема — `QualityEvent`

**Files:**
- Modify: `backend/db/models.py`
- Create: `backend/alembic/versions/0006_quality_events.py`
- Modify: `backend/tests/test_db.py`

**Interfaces:**
- Produces: `QualityEvent(id, legal_act_id, event_type, field_name, detail, detected_at)` — используется в Task 2 через `from db.models import QualityEvent`.

- [ ] **Step 1: Написать падающие тесты схемы**

Добавить в `backend/tests/test_db.py` (после `test_legal_act_categories_table_has_expected_columns`):

```python
def test_migration_creates_quality_events_table(pg_engine):
    tables = set(inspect(pg_engine).get_table_names())
    assert "quality_events" in tables


def test_quality_events_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("quality_events")}
    assert columns == {
        "id", "legal_act_id", "event_type", "field_name", "detail", "detected_at",
    }
```

- [ ] **Step 2: Запустить тесты, убедиться, что падают**

```powershell
$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"
.venv/Scripts/pytest tests/test_db.py -v -k quality_events
```

Ожидается: падают — таблицы ещё нет.

- [ ] **Step 3: Добавить модель в `backend/db/models.py`**

Добавить после класса `LegalActCategory` (перед `CrawlQueueEntry`):

```python
class QualityEvent(Base):
    __tablename__ = "quality_events"

    id = Column(Integer, primary_key=True)
    legal_act_id = Column(Integer, ForeignKey("legal_acts.id"), nullable=False)
    event_type = Column(String, nullable=False)
    field_name = Column(String, nullable=False)
    detail = Column(Text)
    detected_at = Column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: Создать Alembic-ревизию `backend/alembic/versions/0006_quality_events.py`**

```python
"""quality_events: record-level data quality anomaly log

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "quality_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legal_act_id", sa.Integer(), sa.ForeignKey("legal_acts.id"), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("field_name", sa.String(), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("quality_events")
```

- [ ] **Step 5: Запустить тесты, убедиться, что проходят**

```powershell
$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"
.venv/Scripts/pytest tests/test_db.py -v
```

- [ ] **Step 6: Коммит**

```bash
git add backend/db/models.py backend/alembic/versions/0006_quality_events.py backend/tests/test_db.py
git commit -m "feat: add QualityEvent schema for record-level quality checks"
```

---

### Task 2: `store.py` — четыре проверки внутри `upsert_legal_act`

**Files:**
- Modify: `backend/scraper/store.py`
- Modify: `backend/tests/test_store.py`

**Interfaces:**
- Consumes: `QualityEvent` из Task 1.
- Produces: события `quality_events` как побочный эффект `upsert_legal_act` — ничего нового не экспортируется наружу, других задач в этом плане нет.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `backend/tests/test_store.py` (в конец файла, после
`test_upsert_report_stores_raw_html_and_first_seen_at` — или после
последнего теста файла, если порядок отличается):

```python
def test_upsert_legal_act_records_invalid_url_event(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://not-legalacts.example/view?id=1", _fields(), T1,
    )

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="invalid_url",
    ).all()
    assert len(events) == 1
    assert events[0].field_name == "url"


def test_upsert_legal_act_does_not_record_invalid_url_event_for_real_url(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1", _fields(), T1,
    )

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="invalid_url",
    ).count() == 0


def test_upsert_legal_act_records_invalid_date_event(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(created_date="not-a-date", discussion_end_date="09/09/2026"), T1,
    )

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="invalid_date",
    ).all()
    assert len(events) == 1
    assert events[0].field_name == "created_date"


def test_upsert_legal_act_does_not_record_invalid_date_event_for_valid_dates(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(created_date="01/01/2026", discussion_end_date="09/09/2026"), T1,
    )

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="invalid_date",
    ).count() == 0


def test_upsert_legal_act_records_end_before_start_event(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(created_date="09/09/2026", discussion_end_date="01/01/2026"), T1,
    )

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="end_before_start",
    ).all()
    assert len(events) == 1
    assert events[0].field_name == "discussion_end_date"


def test_upsert_legal_act_does_not_record_end_before_start_when_dates_ordered_correctly(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(created_date="01/01/2026", discussion_end_date="09/09/2026"), T1,
    )

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="end_before_start",
    ).count() == 0


def test_upsert_legal_act_first_save_does_not_record_counter_null_flip(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=None), T1,
    )

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="counter_null_flip",
    ).count() == 0


def test_upsert_legal_act_records_counter_null_flip_value_to_null(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=42), T1,
    )
    store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=None), T2,
    )

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="counter_null_flip", field_name="comments_total",
    ).all()
    assert len(events) == 1
    assert events[0].detail == "42 -> None"


def test_upsert_legal_act_records_counter_null_flip_null_to_value(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=None), T1,
    )
    store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=42), T2,
    )

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="counter_null_flip", field_name="comments_total",
    ).all()
    assert len(events) == 1


def test_upsert_legal_act_does_not_record_counter_null_flip_when_both_are_numbers(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=42), T1,
    )
    store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=43), T2,
    )

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="counter_null_flip", field_name="comments_total",
    ).count() == 0
```

- [ ] **Step 2: Запустить тесты, убедиться, что падают**

```powershell
$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"
.venv/Scripts/pytest tests/test_store.py -v -k "quality_event or invalid_url or invalid_date or end_before_start or counter_null_flip"
```

Ожидается: падают — `QualityEvent` не пишется, счёт всегда 0 (тесты,
ожидающие events, падают на `assert len(events) == 1`).

- [ ] **Step 3: Реализовать в `backend/scraper/store.py`**

Изменить импорты в начале файла:

```python
import datetime
import hashlib
from urllib.parse import urlsplit

from sqlalchemy import select

from db.models import (
    ActType, Category, Comment, DocumentVersion, GovernmentBody, LegalAct,
    LegalActCategory, LegalActSnapshot, QualityEvent, Report,
)

BASE_URL = "https://legalacts.egov.kz"
SOURCE_DATE_FORMAT = "%d/%m/%Y"
```

Добавить после `_sha256` (перед `_get_or_create`):

```python
def _parse_source_date(raw):
    if not raw:
        return None
    try:
        return datetime.datetime.strptime(raw, SOURCE_DATE_FORMAT).date()
    except ValueError:
        return None
```

Добавить после `_get_or_create` (перед `upsert_legal_act`):

```python
def _record_quality_events(session, legal_act_id, previous_counters, values, now):
    events = []

    url = values["url"]
    parsed_url = urlsplit(url)
    if not parsed_url.scheme or not parsed_url.netloc or not url.startswith(BASE_URL):
        events.append(("invalid_url", "url", f"malformed or unexpected host: {url}"))

    parsed_dates = {}
    for field in ("created_date", "discussion_end_date"):
        raw = values[field]
        if raw:
            parsed_date = _parse_source_date(raw)
            if parsed_date is None:
                events.append(("invalid_date", field, f"unparsable value: {raw!r}"))
            else:
                parsed_dates[field] = parsed_date

    if "created_date" in parsed_dates and "discussion_end_date" in parsed_dates:
        if parsed_dates["discussion_end_date"] < parsed_dates["created_date"]:
            events.append((
                "end_before_start", "discussion_end_date",
                f"{values['discussion_end_date']} is before {values['created_date']}",
            ))

    if previous_counters is not None:
        for field in ("comments_total", "likes_count", "dislikes_count"):
            old_value = previous_counters[field]
            new_value = values[field]
            if (old_value is None) != (new_value is None):
                events.append(("counter_null_flip", field, f"{old_value} -> {new_value}"))

    for event_type, field_name, detail in events:
        session.add(QualityEvent(
            legal_act_id=legal_act_id, event_type=event_type,
            field_name=field_name, detail=detail, detected_at=now,
        ))
```

Изменить `upsert_legal_act` — добавить захват старых значений счётчиков
СРАЗУ после блока `previous_snapshot` (до того, как `existing` будет
изменён через `setattr` ниже по функции), и вызов
`_record_quality_events` перед финальным `session.commit()`:

```python
def upsert_legal_act(session, external_id, section, url, fields, now):
    existing = session.execute(
        select(LegalAct).where(LegalAct.external_id == external_id)
    ).scalar_one_or_none()

    previous_snapshot = None
    previous_counters = None
    if existing is not None:
        previous_snapshot = session.execute(
            select(LegalActSnapshot)
            .where(LegalActSnapshot.legal_act_id == existing.id)
            .order_by(LegalActSnapshot.captured_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        previous_counters = {
            "comments_total": existing.comments_total,
            "likes_count": existing.likes_count,
            "dislikes_count": existing.dislikes_count,
        }

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

    _record_quality_events(session, legal_act.id, previous_counters, values, now)

    session.commit()
    return legal_act.id
```

(Единственные реальные изменения относительно текущего файла: два новых
блока — захват `previous_counters` внутри `if existing is not None:` и
строка `_record_quality_events(...)` перед `session.commit()`. Порядок
критичен: `previous_counters` захватывается ДО цикла `for key, value in
values.items(): setattr(existing, key, value)`, иначе к моменту вызова
`_record_quality_events` старые значения счётчиков будут уже перезаписаны
новыми.)

- [ ] **Step 4: Запустить тесты, убедиться, что проходят**

```powershell
$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"
.venv/Scripts/pytest tests/test_store.py -v
```

Убедиться, что весь файл проходит, включая все существующие тесты
`upsert_legal_act` (они используют `_fields()` с датами в формате
`"2026-01-01"`/`"2026-12-31"` — ISO, не `DD/MM/YYYY` — это ожидаемо
создаёт побочные `invalid_date`-события в этих тестах, но не ломает их
существующие assertions, так как ни один из них не проверяет отсутствие
quality-событий).

- [ ] **Step 5: Прогнать весь backend-набор**

```powershell
$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"
.venv/Scripts/pytest -v
```

Ожидается: все тесты проходят (127 существующих + 10 новых из Task 1–2).

- [ ] **Step 6: Коммит**

```bash
git add backend/scraper/store.py backend/tests/test_store.py
git commit -m "feat: record quality events for invalid URL/dates and counter null-flips"
```

---

### Task 3: Обновить `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md` (корень репо)

**Interfaces:** нет (документация).

- [ ] **Step 1: Обновить `## Architecture` в `CLAUDE.md`**

В разделе «Слой хранилища» добавить предложение о `QualityEvent` после
упоминания `Category`/`LegalActCategory`:

```text
`QualityEvent` (журнал аномалий, обнаруженных при `upsert_legal_act`:
`invalid_url`, `invalid_date`, `end_before_start`, `counter_null_flip`
— ничего не блокирует, только фиксируется рядом с обычным сохранением
акта; без апсерта, каждое обнаружение — отдельная строка).
```

В разделе «Слой скрейпера», в абзаце про `store.py`, добавить
предложение после описания `upsert_legal_act`:

```text
`upsert_legal_act` также пишет `QualityEvent`-записи для четырёх
проверок из раздела 22.3 продуктового ТЗ (группа A — на уровне одной
записи): битый URL (`url` не начинается с `BASE_URL`), невалидная дата
(`created_date`/`discussion_end_date` не парсятся форматом
`DD/MM/YYYY`), конец обсуждения раньше начала, флип счётчика
(`comments_total`/`likes_count`/`dislikes_count`) в/из `NULL` между
последовательными обходами одного акта. Остальные проверки раздела
22.3 (резкое падение числа объектов; новые статусы/типы/категории/
HTML-структуры; сравнение `comments_total` с фактически собранным
числом комментариев) — группа B, агрегатные проверки по всему
датасету, отдельный дизайн, не реализованы.
```

Обновить число тестов в `## Project status` (127/127 → фактическое
число после Task 1–2, посчитать через `pytest --collect-only -q` или
финальную строку `pytest -q`).

В разделе «Известные ограничения» добавить пункт:

```text
- `QualityEvent`: события группы A не экспонируются через API v1 в
  этой итерации (только сбор в БД, как `DocumentVersion`/`Report`/
  `Category`); нет дедупликации — при стабильной проблеме на одном
  акте события накапливаются на каждом обходе.
```

- [ ] **Step 2: Коммит**

```bash
git add CLAUDE.md
git commit -m "docs: document record-level quality checks in CLAUDE.md"
```
