# Category Collection (Этап 2, `Category`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Собрать связь актов с категориями/тематиками сайта, обходя 150
списочных URL, отфильтрованных по `categoryId` (6 существующих seed-записей
× 25 категорий), и связывая найденные карточки с уже собранными актами.

**Architecture:** Новая многие-ко-многим связь `LegalAct` ↔ `Category` через
join-таблицу `legal_act_categories`. Новый `page_type="category_list"` в
`crawl_queue` — свой обработчик `process_category_list_entry`, переиспользующий
существующий `list_page.parse_list_page`/`parse_total_pages` и пагинацию
(`_current_page`/`_set_page_param`). `category_list` обрабатывается только
когда очереди `list` и `document` пусты. Если карточка ссылается на акт,
которого ещё нет в `legal_acts` — связь не создаётся, страница просто
пропускается (акт будет найден штатным обходом, связка добьётся повторным
обходом через `requeue_stale_lists`).

**Tech Stack:** Python, SQLAlchemy 2.x, Alembic, BeautifulSoup+lxml, pytest +
testcontainers.

**Spec:** `docs/superpowers/specs/2026-09-23-category-collection-design.md`

## Global Constraints

- Таксономия — 25 категорий (`external_id`, `name`), зафиксированы в спеке
  живой проверкой 2026-09-23 и сверены с `tests/fixtures/list_page.html`.
- Статический список `CATEGORIES` в `run.py` используется **только** для
  построения seed-URL; сохранённое в БД `Category.name` всегда берётся с
  живой страницы через `parse_category_name`, с откатом на `CATEGORIES`,
  только если на странице категория вдруг не нашлась (см. Task 6).
- Если `LegalAct` для найденной карточки ещё не существует — не создавать
  ни акт, ни связь, просто пропустить карточку. Решение владельца продукта
  (2026-09-23), см. спеку.
- `category_list` обрабатывается только после исчерпания очередей `list` и
  `document` (третий, самый низкий приоритет в `run()`).
- `requeue_stale_lists` должен переоткрывать записи обоих типов — `list` и
  `category_list` — по тому же порогу `STALE_AFTER_DAYS`.
- Архивные seed-варианты (`status=IN_ARCHIVE` для `npa`/`arv`) включены в
  затравку категорий — решение владельца продукта (2026-09-23).
- Раздел `arv` не исключается из обхода по категориям.
- Никаких изменений в API v1 (`app/routers/*`, `app/schemas/*`) — эта
  итерация только про сбор данных, как и `DocumentVersion`/`Report`.

---

### Task 1: Схема — `Category` и `LegalActCategory`

**Files:**
- Modify: `backend/db/models.py`
- Create: `backend/alembic/versions/0004_categories.py`
- Modify: `backend/tests/test_db.py`

**Interfaces:**
- Produces: `Category(id, external_id, name)`, `LegalActCategory(id, legal_act_id, category_id, first_seen_at)` — используются во всех последующих задачах через `from db.models import Category, LegalActCategory`.

- [ ] **Step 1: Написать падающие тесты схемы**

Добавить в `backend/tests/test_db.py` (после `test_reports_table_has_expected_columns`):

```python
def test_migration_creates_category_tables(pg_engine):
    tables = set(inspect(pg_engine).get_table_names())
    assert {"categories", "legal_act_categories"}.issubset(tables)


def test_categories_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("categories")}
    assert columns == {"id", "external_id", "name"}


def test_legal_act_categories_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("legal_act_categories")}
    assert columns == {"id", "legal_act_id", "category_id", "first_seen_at"}
```

- [ ] **Step 2: Запустить тесты, убедиться, что падают**

Запуск (PowerShell, из `backend/`, с `$env:DOCKER_HOST = "npipe:////./pipe/dockerDesktopLinuxEngine"`):

```powershell
.venv/Scripts/pytest tests/test_db.py -v
```

Ожидается: `test_migration_creates_category_tables` и обе `_has_expected_columns`
падают — таблиц ещё нет.

- [ ] **Step 3: Добавить модели в `backend/db/models.py`**

Добавить после класса `Report` (перед `CrawlQueueEntry`):

```python
class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    external_id = Column(Integer, nullable=False, unique=True)
    name = Column(String, nullable=False)


class LegalActCategory(Base):
    __tablename__ = "legal_act_categories"
    __table_args__ = (
        UniqueConstraint(
            "legal_act_id", "category_id",
            name="uq_legal_act_categories_legal_act_id_category_id",
        ),
    )

    id = Column(Integer, primary_key=True)
    legal_act_id = Column(Integer, ForeignKey("legal_acts.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: Создать Alembic-ревизию `backend/alembic/versions/0004_categories.py`**

```python
"""categories: category/topic taxonomy and legal_act <-> category membership

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.UniqueConstraint("external_id", name="uq_categories_external_id"),
    )
    op.create_table(
        "legal_act_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legal_act_id", sa.Integer(), sa.ForeignKey("legal_acts.id"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "legal_act_id", "category_id",
            name="uq_legal_act_categories_legal_act_id_category_id",
        ),
    )


def downgrade():
    op.drop_table("legal_act_categories")
    op.drop_table("categories")
```

- [ ] **Step 5: Запустить тесты, убедиться, что проходят**

```powershell
.venv/Scripts/pytest tests/test_db.py -v
```

Ожидается: все тесты `test_db.py`, включая три новых, проходят (фикстуры
`conftest.py` сами прогоняют `alembic upgrade head` перед каждым тестом).

- [ ] **Step 6: Коммит**

```bash
git add backend/db/models.py backend/alembic/versions/0004_categories.py backend/tests/test_db.py
git commit -m "feat: add Category and LegalActCategory schema"
```

---

### Task 2: `store.py` — функции для категорий

**Files:**
- Modify: `backend/scraper/store.py`
- Modify: `backend/tests/test_store.py`

**Interfaces:**
- Consumes: `Category`, `LegalActCategory` из Task 1; существующий `LegalAct` (уже импортирован в `store.py`).
- Produces: `legal_act_id_for_external_id(session, external_id) -> int | None`, `get_or_create_category(session, external_id, name) -> Category`, `link_legal_act_category(session, legal_act_id, category_id, now) -> None` — используются в Task 6.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `backend/tests/test_store.py` (после `test_upsert_report_stores_raw_html_and_first_seen_at`):

```python
def test_legal_act_id_for_external_id_returns_none_before_insert_and_id_after(db_session):
    assert store.legal_act_id_for_external_id(db_session, 15906353) is None

    legal_act_id = store.upsert_legal_act(db_session, 15906353, "npa", "url1", _fields(), T1)
    assert store.legal_act_id_for_external_id(db_session, 15906353) == legal_act_id


def test_get_or_create_category_inserts_new_row(db_session):
    category = store.get_or_create_category(db_session, 346, "Информационные технологии")

    from db.models import Category
    row = db_session.get(Category, category.id)
    assert row.external_id == 346
    assert row.name == "Информационные технологии"


def test_get_or_create_category_reuses_existing_row_by_external_id(db_session):
    first = store.get_or_create_category(db_session, 346, "Информационные технологии")
    second = store.get_or_create_category(db_session, 346, "Информационные технологии")

    assert first.id == second.id
    from db.models import Category
    assert db_session.query(Category).filter_by(external_id=346).count() == 1


def test_get_or_create_category_updates_name_when_site_renamed_it(db_session):
    first = store.get_or_create_category(db_session, 346, "Старое имя")
    second = store.get_or_create_category(db_session, 346, "Новое имя")

    assert first.id == second.id
    from db.models import Category
    row = db_session.get(Category, first.id)
    assert row.name == "Новое имя"


def test_link_legal_act_category_creates_row(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    category = store.get_or_create_category(db_session, 346, "Информационные технологии")

    store.link_legal_act_category(db_session, legal_act_id, category.id, T1)

    from db.models import LegalActCategory
    row = db_session.query(LegalActCategory).filter_by(
        legal_act_id=legal_act_id, category_id=category.id,
    ).one()
    assert row.first_seen_at == T1


def test_link_legal_act_category_is_idempotent(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    category = store.get_or_create_category(db_session, 346, "Информационные технологии")

    store.link_legal_act_category(db_session, legal_act_id, category.id, T1)
    store.link_legal_act_category(db_session, legal_act_id, category.id, T2)

    from db.models import LegalActCategory
    rows = db_session.query(LegalActCategory).filter_by(
        legal_act_id=legal_act_id, category_id=category.id,
    ).all()
    assert len(rows) == 1
    assert rows[0].first_seen_at == T1
```

- [ ] **Step 2: Запустить тесты, убедиться, что падают**

```powershell
.venv/Scripts/pytest tests/test_store.py -v -k "category or legal_act_id_for_external_id"
```

Ожидается: падают с `AttributeError: module 'scraper.store' has no attribute ...`.

- [ ] **Step 3: Реализовать функции в `backend/scraper/store.py`**

Изменить импорт в начале файла:

```python
from db.models import (
    ActType, Category, Comment, DocumentVersion, GovernmentBody, LegalAct,
    LegalActCategory, LegalActSnapshot, Report,
)
```

Добавить в конец файла (после `upsert_report`):

```python
def legal_act_id_for_external_id(session, external_id):
    return session.execute(
        select(LegalAct.id).where(LegalAct.external_id == external_id)
    ).scalar_one_or_none()


def get_or_create_category(session, external_id, name):
    existing = session.execute(
        select(Category).where(Category.external_id == external_id)
    ).scalar_one_or_none()
    if existing is not None:
        if name and existing.name != name:
            existing.name = name
            session.commit()
        return existing

    category = Category(external_id=external_id, name=name)
    session.add(category)
    session.commit()
    return category


def link_legal_act_category(session, legal_act_id, category_id, now):
    existing = session.execute(
        select(LegalActCategory.id).where(
            LegalActCategory.legal_act_id == legal_act_id,
            LegalActCategory.category_id == category_id,
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(LegalActCategory(
            legal_act_id=legal_act_id, category_id=category_id, first_seen_at=now,
        ))
        session.commit()
```

- [ ] **Step 4: Запустить тесты, убедиться, что проходят**

```powershell
.venv/Scripts/pytest tests/test_store.py -v
```

Ожидается: весь файл проходит (проверить, что старые тесты `store.py` тоже
не сломались изменением импорта).

- [ ] **Step 5: Коммит**

```bash
git add backend/scraper/store.py backend/tests/test_store.py
git commit -m "feat: add store functions for category lookup and linking"
```

---

### Task 3: Парсер — `parse_category_name`

**Files:**
- Modify: `backend/scraper/parsers/list_page.py`
- Modify: `backend/tests/test_list_page.py`

**Interfaces:**
- Produces: `parse_category_name(html, category_id) -> str | None` — используется в Task 6.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `backend/tests/test_list_page.py`:

```python
def test_parse_category_name_finds_matching_option():
    html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    assert list_page.parse_category_name(html, 8232) == "Экономика/экономическая деятельность"


def test_parse_category_name_strips_whitespace():
    html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    assert list_page.parse_category_name(html, 779) == "Лицензирование и аккредитация"


def test_parse_category_name_returns_none_when_id_not_found():
    html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    assert list_page.parse_category_name(html, 999999) is None
```

- [ ] **Step 2: Запустить тесты, убедиться, что падают**

```powershell
.venv/Scripts/pytest tests/test_list_page.py -v -k category
```

Ожидается: падают с `AttributeError: module 'scraper.parsers.list_page' has no attribute 'parse_category_name'`.

- [ ] **Step 3: Реализовать в `backend/scraper/parsers/list_page.py`**

Добавить в конец файла:

```python
def parse_category_name(html, category_id):
    soup = BeautifulSoup(html, "lxml")
    option = soup.select_one(f'option[value="{category_id}"]')
    return option.get_text(strip=True) if option else None
```

- [ ] **Step 4: Запустить тесты, убедиться, что проходят**

```powershell
.venv/Scripts/pytest tests/test_list_page.py -v
```

- [ ] **Step 5: Коммит**

```bash
git add backend/scraper/parsers/list_page.py backend/tests/test_list_page.py
git commit -m "feat: parse category name from the categoryId filter dropdown"
```

---

### Task 4: `queue.py` — `requeue_stale_lists` для `category_list`

**Files:**
- Modify: `backend/scraper/queue.py`
- Modify: `backend/tests/test_queue.py`

**Interfaces:**
- Consumes: ничего нового (сигнатура `requeue_stale_lists(session, older_than_iso)` не меняется).

- [ ] **Step 1: Написать падающий тест**

Добавить в `backend/tests/test_queue.py` (после `test_requeue_stale_lists_resets_old_done_lists_only`):

```python
def test_requeue_stale_lists_also_resets_old_done_category_lists(db_session):
    queue.enqueue(db_session, "https://example.test/cat-old", "category_list", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.enqueue(db_session, "https://example.test/cat-new", "category_list", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.mark_done(db_session, "https://example.test/cat-old", datetime.datetime(2026, 9, 1, tzinfo=UTC))
    queue.mark_done(db_session, "https://example.test/cat-new", datetime.datetime(2026, 9, 14, tzinfo=UTC))

    queue.requeue_stale_lists(db_session, datetime.datetime(2026, 9, 10, tzinfo=UTC))

    assert queue.next_pending(db_session, "category_list") == "https://example.test/cat-old"

    from db.models import CrawlQueueEntry
    assert db_session.get(CrawlQueueEntry, "https://example.test/cat-new").status == "done"
```

- [ ] **Step 2: Запустить тест, убедиться, что падает**

```powershell
.venv/Scripts/pytest tests/test_queue.py -v -k category_lists
```

Ожидается: падает — `next_pending` возвращает `None`, `category_list` записи
не переоткрываются.

- [ ] **Step 3: Изменить `requeue_stale_lists` в `backend/scraper/queue.py`**

```python
def requeue_stale_lists(session, older_than_iso):
    session.execute(
        update(CrawlQueueEntry)
        .where(
            CrawlQueueEntry.page_type.in_(["list", "category_list"]),
            CrawlQueueEntry.status == "done",
            CrawlQueueEntry.processed_at < older_than_iso,
        )
        .values(status="pending")
    )
    session.commit()
```

- [ ] **Step 4: Запустить тесты, убедиться, что проходят**

```powershell
.venv/Scripts/pytest tests/test_queue.py -v
```

- [ ] **Step 5: Коммит**

```bash
git add backend/scraper/queue.py backend/tests/test_queue.py
git commit -m "feat: requeue stale category_list entries alongside list entries"
```

---

### Task 5: `run.py` — таксономия и затравка

**Files:**
- Modify: `backend/scraper/run.py`
- Modify: `backend/tests/test_run.py`

**Interfaces:**
- Produces: `CATEGORIES` (список из 25 `(external_id, name)`), `CATEGORY_NAMES` (тот же список как `dict`), `_with_category(url, category_id) -> str` — используются в Task 6/7.
- Consumes: существующий `queue.enqueue`.

- [ ] **Step 1: Написать падающий тест**

Добавить в `backend/tests/test_run.py` (после `test_process_list_entry_stops_pagination_at_last_page`, до `test_process_document_entry_stores_document_and_comments`):

```python
def test_seed_queue_enqueues_category_list_for_every_seed_and_category(db_session):
    run_module.seed_queue(db_session)

    from db.models import CrawlQueueEntry
    category_rows = db_session.execute(
        CrawlQueueEntry.__table__.select().where(CrawlQueueEntry.page_type == "category_list")
    ).fetchall()
    assert len(category_rows) == len(run_module.SEED_LIST_URLS) * len(run_module.CATEGORIES)

    npa_urls = {row.url for row in category_rows if row.section == "npa"}
    assert "https://legalacts.egov.kz/list?categoryId=346" in npa_urls

    kdrp_urls = {row.url for row in category_rows if row.section == "kdrp"}
    assert any(
        "types%5B0%5D=7001" in url and "categoryId=346" in url for url in kdrp_urls
    )


def test_with_category_preserves_existing_query_params():
    url = run_module._with_category(
        "https://legalacts.egov.kz/list?types[0]=7001&types[1]=7002", 346,
    )
    assert "categoryId=346" in url
    assert "types" in url
```

- [ ] **Step 2: Запустить тесты, убедиться, что падают**

```powershell
.venv/Scripts/pytest tests/test_run.py -v -k "seed_queue_enqueues_category or with_category"
```

Ожидается: `AttributeError` — `CATEGORIES`/`_with_category` ещё не существуют.

- [ ] **Step 3: Добавить константы и функцию в `backend/scraper/run.py`**

Добавить после `SEED_LIST_URLS` (перед `def now():`):

```python
CATEGORIES = [
    (346, "Информационные технологии"),
    (359, "Иммиграция, миграция, гражданство"),
    (367, "Семья"),
    (368, "Образование"),
    (369, "Трудоустройство и занятость"),
    (370, "Социальное обеспечение"),
    (372, "Недвижимость"),
    (373, "Налоги и финансы"),
    (374, "Правовая помощь"),
    (375, "Туризм и спорт"),
    (376, "Воинский учет и безопасность"),
    (633, "Сельское хозяйство"),
    (779, "Лицензирование и аккредитация"),
    (806, "Транспорт и коммуникации"),
    (844, "Здравоохранение"),
    (1301, "Природные ресурсы и экология"),
    (1385, "Интеллектуальная собственность"),
    (1442, "Регистрация и развитие бизнеса"),
    (1551, "Промышленность"),
    (1874, "Культура, Религия, СМИ"),
    (8232, "Экономика/экономическая деятельность"),
    (15888758, "Другие"),
    (15888765, "Иные вопросы"),
    (15888767, "Государственное управление"),
    (15888768, "Организационные вопросы"),
]
CATEGORY_NAMES = dict(CATEGORIES)
```

Изменить `seed_queue`:

```python
def seed_queue(session):
    discovered = now()
    for section, url in SEED_LIST_URLS:
        queue.enqueue(session, url, "list", discovered, section=section)
    for section, url in SEED_LIST_URLS:
        for category_id, _category_name in CATEGORIES:
            queue.enqueue(
                session, _with_category(url, category_id), "category_list", discovered, section=section,
            )
```

Добавить рядом с `_with_type_comment` (после неё):

```python
def _with_category(url, category_id):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["categoryId"] = str(category_id)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
```

- [ ] **Step 4: Запустить тесты, убедиться, что проходят**

```powershell
.venv/Scripts/pytest tests/test_run.py -v -k "seed_queue or with_category"
```

Также перепроверить `test_run_seeds_queue_and_respects_limit` (существующий
тест, использует `monkeypatch.setattr(run_module, "SEED_LIST_URLS", ...)` —
после патча `seed_queue` всё равно создаст `len(CATEGORIES)` записей
`category_list` в дополнение к затронутой `list`; тест не проверяет их
количество, только `document`-записи, так что он не сломается):

```powershell
.venv/Scripts/pytest tests/test_run.py -v -k test_run_seeds_queue_and_respects_limit
```

- [ ] **Step 5: Коммит**

```bash
git add backend/scraper/run.py backend/tests/test_run.py
git commit -m "feat: seed category-filtered list queue entries"
```

---

### Task 6: `run.py` — `process_category_list_entry`

**Files:**
- Modify: `backend/scraper/run.py`
- Modify: `backend/tests/test_run.py`

**Interfaces:**
- Consumes: `store.legal_act_id_for_external_id`, `store.get_or_create_category`, `store.link_legal_act_category` (Task 2); `list_page.parse_category_name`, `list_page.parse_list_page`, `list_page.parse_total_pages` (Task 3, существующее); `CATEGORY_NAMES`, `_with_category`, `_current_page`, `_set_page_param` (Task 5, существующее).
- Produces: `process_category_list_entry(session, fetcher, url, section="npa")` — используется в Task 7.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `backend/tests/test_run.py` (после `test_process_list_entry_404_enqueues_nothing`, до `test_run_seeds_queue_and_respects_limit`):

```python
def test_process_category_list_entry_links_known_act(db_session):
    store.upsert_legal_act(db_session, 15908401, "npa", "url1", _fields(), T1)

    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/list?categoryId=346"
    fetcher = StubFetcher({url: list_html})

    run_module.process_category_list_entry(db_session, fetcher, url, section="npa")

    from db.models import Category, LegalAct, LegalActCategory
    act = db_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 15908401)
    ).fetchone()
    category = db_session.query(Category).filter_by(external_id=346).one()
    link = db_session.query(LegalActCategory).filter_by(
        legal_act_id=act.id, category_id=category.id,
    ).one_or_none()
    assert link is not None
    assert category.name == "Информационные технологии"


def test_process_category_list_entry_skips_unknown_act(db_session):
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/list?categoryId=346"
    fetcher = StubFetcher({url: list_html})

    run_module.process_category_list_entry(db_session, fetcher, url, section="npa")

    from db.models import LegalAct, LegalActCategory
    assert db_session.execute(LegalAct.__table__.select()).fetchall() == []
    assert db_session.execute(LegalActCategory.__table__.select()).fetchall() == []


def test_process_category_list_entry_falls_back_to_static_name_when_dropdown_missing(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 100, "npa", "url1", _fields(), T1)
    url = "https://legalacts.egov.kz/list?categoryId=346"
    html = '<div class="contentlist"><h3><a href="/npa/view?id=100">Title</a></h3></div>'
    fetcher = StubFetcher({url: html})

    run_module.process_category_list_entry(db_session, fetcher, url, section="npa")

    from db.models import Category
    category = db_session.query(Category).filter_by(external_id=346).one()
    assert category.name == run_module.CATEGORY_NAMES[346]


def test_process_category_list_entry_enqueues_next_page(db_session):
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/list?categoryId=346"
    fetcher = StubFetcher({url: list_html})

    run_module.process_category_list_entry(db_session, fetcher, url, section="npa")

    from db.models import CrawlQueueEntry
    next_page = db_session.execute(
        CrawlQueueEntry.__table__.select().where(CrawlQueueEntry.page_type == "category_list")
    ).fetchall()
    assert len(next_page) == 1
    assert "page=2" in next_page[0].url
    assert "categoryId=346" in next_page[0].url


def test_process_category_list_entry_404_enqueues_nothing(db_session):
    url = "https://legalacts.egov.kz/list?categoryId=346"
    fetcher = StubFetcher({}, status_codes={url: 404})

    run_module.process_category_list_entry(db_session, fetcher, url, section="npa")

    from db.models import Category, CrawlQueueEntry
    assert db_session.execute(Category.__table__.select()).fetchall() == []
    assert db_session.execute(CrawlQueueEntry.__table__.select()).fetchall() == []
```

Добавить импорт `store` в начало `backend/tests/test_run.py` (после
`from scraper import run as run_module`):

```python
from scraper import store
```

И константу `T1` (тесты выше используют `_fields()`/`T1` из `test_store.py`
только по образцу — в `test_run.py` их нет, добавить рядом с `UTC`):

```python
T1 = datetime.datetime(2026, 9, 1, tzinfo=UTC)


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
```

- [ ] **Step 2: Запустить тесты, убедиться, что падают**

```powershell
.venv/Scripts/pytest tests/test_run.py -v -k process_category_list_entry
```

Ожидается: `AttributeError: module 'scraper.run' has no attribute 'process_category_list_entry'`.

- [ ] **Step 3: Реализовать в `backend/scraper/run.py`**

Добавить после `process_list_entry` (перед `def process_document_entry`):

```python
def process_category_list_entry(session, fetcher, url, section="npa"):
    response = fetcher.get(url)
    if response.status_code == 404:
        return
    html = response.text

    category_id = int(dict(parse_qsl(urlsplit(url).query))["categoryId"])
    category_name = list_page.parse_category_name(html, category_id) or CATEGORY_NAMES.get(category_id)
    category = store.get_or_create_category(session, category_id, category_name)

    discovered = now()
    for card in list_page.parse_list_page(html):
        external_id = int(dict(parse_qsl(urlsplit(card["url"]).query))["id"])
        legal_act_id = store.legal_act_id_for_external_id(session, external_id)
        if legal_act_id is not None:
            store.link_legal_act_category(session, legal_act_id, category.id, discovered)

    total_pages = list_page.parse_total_pages(html)
    current_page = _current_page(url)
    if current_page < total_pages:
        queue.enqueue(
            session, _set_page_param(url, current_page + 1), "category_list", discovered, section=section,
        )
```

- [ ] **Step 4: Запустить тесты, убедиться, что проходят**

```powershell
.venv/Scripts/pytest tests/test_run.py -v
```

Убедиться, что весь файл проходит, не только новые тесты (добавленный
импорт `store`/`T1`/`_fields` не должен конфликтовать с существующими
именами в файле).

- [ ] **Step 5: Коммит**

```bash
git add backend/scraper/run.py backend/tests/test_run.py
git commit -m "feat: process category-filtered list pages and link known acts"
```

---

### Task 7: `run.py` — приоритет очереди в главном цикле

**Files:**
- Modify: `backend/scraper/run.py`
- Modify: `backend/tests/test_run.py`

**Interfaces:**
- Consumes: `process_category_list_entry` (Task 6), существующие `queue.next_pending`/`queue.section_for`/`queue.mark_done`/`queue.mark_error`.

- [ ] **Step 1: Написать падающий тест**

Добавить в `backend/tests/test_run.py` (после
`test_second_run_rediscovers_stale_list_page`, в конец файла):

```python
def test_run_processes_category_list_only_after_list_and_document_queues_empty(database_url, monkeypatch):
    ru_html = (FIXTURES / "document_with_comments.html").read_text(encoding="utf-8")
    kk_html = (FIXTURES / "document_with_comments_kk.html").read_text(encoding="utf-8")
    doc_url = "https://legalacts.egov.kz/npa/view?id=15906353"
    category_url = "https://legalacts.egov.kz/list?categoryId=346"
    category_html = (
        '<select id="categoryId"><option value="346">Информационные технологии</option></select>'
    )

    _, SessionLocal = create_engine_and_session_factory(database_url)
    seed_session = SessionLocal()
    queue.enqueue(seed_session, doc_url, "document", datetime.datetime(2020, 1, 1, tzinfo=UTC), section="npa")
    queue.enqueue(seed_session, category_url, "category_list", datetime.datetime(2020, 1, 1, tzinfo=UTC), section="npa")
    seed_session.close()

    fetcher = StubFetcher({doc_url: [ru_html, kk_html], category_url: category_html})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(database_url, limit=1)

    check_session = SessionLocal()
    from db.models import CrawlQueueEntry
    assert check_session.get(CrawlQueueEntry, doc_url).status == "done"
    assert check_session.get(CrawlQueueEntry, category_url).status == "pending"
    check_session.close()

    run_module.run(database_url, limit=1)

    check_session2 = SessionLocal()
    assert check_session2.get(CrawlQueueEntry, category_url).status == "done"
    check_session2.close()
```

- [ ] **Step 2: Запустить тест, убедиться, что падает**

```powershell
.venv/Scripts/pytest tests/test_run.py -v -k processes_category_list_only_after
```

Ожидается: первая часть (`doc_row.status == "done"`, `category_row.status
== "pending"`) пройдёт уже сейчас — `category_list` просто не существует
для текущего цикла `run()`, поэтому `document`-запись обрабатывается как
обычно, а `category_list`-запись никто не трогает. Тест упадёт на второй
части (`category_row2.status == "done"` после второго вызова `run()`) —
без ветки `category_list` в цикле `has_pending` после первого запуска
станет `False` (обе `list`/`document`-очереди пусты, `category_list`
не проверяется вообще), `run()` сразу завершится, ничего не обработав.

- [ ] **Step 3: Изменить `run()` в `backend/scraper/run.py`**

Изменить `has_pending`:

```python
    has_pending = (
        queue.next_pending(session, "list") is not None
        or queue.next_pending(session, "document") is not None
        or queue.next_pending(session, "category_list") is not None
    )
```

Добавить третью ветку в цикл `while`, после блока `document_url` и перед
`break`:

```python
        category_list_url = queue.next_pending(session, "category_list")
        if category_list_url is not None:
            section = queue.section_for(session, category_list_url) or "npa"
            try:
                process_category_list_entry(session, fetcher, category_list_url, section=section)
                queue.mark_done(session, category_list_url, now())
            except Exception as exc:
                session.rollback()
                queue.mark_error(session, category_list_url, str(exc), now())
            processed += 1
            continue

        break
```

(Удалить старый одиночный `break`, оставить только новый, идущий после
этой ветки.)

- [ ] **Step 4: Запустить тесты, убедиться, что проходят**

```powershell
.venv/Scripts/pytest tests/test_run.py -v
```

- [ ] **Step 5: Прогнать весь backend-набор**

```powershell
.venv/Scripts/pytest -v
```

Ожидается: все тесты проходят (порядок величины — 94 существующих + новые
из Task 1–7).

- [ ] **Step 6: Коммит**

```bash
git add backend/scraper/run.py backend/tests/test_run.py
git commit -m "feat: give category_list queue entries lowest processing priority"
```

---

### Task 8: Обновить `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md` (корень репо)

**Interfaces:** нет (документация).

- [ ] **Step 1: Обновить `## Architecture` в `CLAUDE.md`**

В разделе «Слой хранилища» добавить предложение о `Category`/`LegalActCategory`
после упоминания `Report`, по образцу существующих формулировок:

```text
`Category`/`LegalActCategory` (категории/тематики — таксономия из 25
значений; `Category.external_id` — categoryId сайта, `Category.name`
перезаписывается живым значением с отфильтрованной страницы при каждом
обходе; `LegalActCategory` — связь многие-ко-многим, создаётся только для
уже собранных актов).
```

В разделе «Слой скрейпера» после абзаца про `run.py`/`process_document_entry`
добавить абзац:

```text
Начиная с Этапа 2, `run.py` также обходит категории/тематики: `CATEGORIES`
(статический список из 25 `(id, name)`, используется только для построения
150 стартовых URL — 6 существующих seed-записей × 25 категорий) и
`process_category_list_entry` (новый `page_type="category_list"`,
переиспользует `list_page.parse_list_page`/`parse_total_pages` и пагинацию
`_set_page_param`; парсит имя категории живьём через
`list_page.parse_category_name`, с откатом на `CATEGORY_NAMES`, если на
странице категория не нашлась). Если карточка ссылается на акт, которого
ещё нет в `legal_acts` — связь не создаётся, карточка пропускается (акт
будет найден штатным обходом `list`/`Arvlist`, связка добьётся повторным
обходом). `category_list` обрабатывается в `run()` только когда очереди
`list` и `document` пусты — третий, самый низкий приоритет.
`requeue_stale_lists` переоткрывает устаревшие записи обоих типов
(`list` и `category_list`).
```

Обновить число тестов в `## Project status` (94/94 → фактическое число
после Task 1–7, посчитать через `pytest --collect-only -q | tail -1` или
аналог).

В разделе «Известные ограничения» добавить пункт:

```text
- `Category`: связь с актом создаётся, только если акт уже был обойдён
  штатным `list`/`Arvlist`-обходом на момент обработки категорийной
  страницы; для актов, обнаруженных позже, связка появится только на
  следующем полном обходе категории (`requeue_stale_lists`, порог
  `STALE_AFTER_DAYS` = 7 дней) — до этого момента акт существует в базе
  без связей с категориями, в которых он на самом деле состоит.
```

- [ ] **Step 2: Коммит**

```bash
git add CLAUDE.md
git commit -m "docs: document Category collection in CLAUDE.md"
```
