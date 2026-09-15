# Парсер legalacts.egov.kz — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** собрать архив НПА (документы + обсуждения с комментариями) с портала legalacts.egov.kz в локальную SQLite-базу, резюмируемо и с докачкой нового при повторных запусках.

**Architecture:** Python-скрипт без веб-фреймворка. `crawl_queue` в SQLite — единственный источник истины о том, что уже обработано (двигатель резюмируемости). Обход двухуровневый: список → карточки документов; списочные страницы обходятся "лениво" (каждая страница при обработке сама добавляет в очередь только следующую страницу пагинации, а не все сразу). HTML парсится через BeautifulSoup по селекторам, подтверждённым на реальных страницах сайта. Комментарии встроены прямо в HTML карточки документа — отдельного обхода не требуется.

**Tech Stack:** Python 3.8, `requests`, `beautifulsoup4` + `lxml`, стандартный `sqlite3`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-09-15-legalacts-scraper-design.md` (включая раздел "Уточнения по итогам разведки реальной разметки" — план реализует именно уточнённую там модель данных, не исходный раздел 2 спека дословно).

## Global Constraints

- Один запрос за раз, без конкурентности; задержка между запросами ~0.5–1 сек со случайным джиттером (см. спек, раздел 3).
- Постоянный `User-Agent`, указывающий на исследовательский характер обхода.
- `robots.txt` запрещает `/npa/view` и `/application` — этот запрет **сознательно игнорируется** для этих двух путей (см. спек, addendum от 2026-09-15); для всех остальных путей `robots.txt` соблюдается (в v1 остальных путей вне `/list`/`/Arvlist`/`/npa/view`/`/application/withdraw`/`/application/changelang` не используется).
- Комментарии хранятся с единственным полем `body` (не переводятся, см. спек) — язык документа (`title_ru`/`title_kk`, `raw_html_ru`/`raw_html_kk`) хранится отдельно от языка комментариев.
- В v1 нет `category_id`/`government_id`/`region_id` — орган-разработчик хранится как текст в `documents.government_body` (см. спек, решение по объёму MVP).
- Сетевые и разбор-ошибки на уровне одной страницы не должны останавливать весь обход — страница помечается `error` в `crawl_queue`, обход продолжается.

---

### Task 1: Каркас проекта и схема SQLite

**Files:**
- Create: `requirements.txt`
- Create: `scraper/__init__.py`
- Create: `scraper/parsers/__init__.py`
- Create: `scraper/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces: `scraper.db.connect(db_path: str) -> sqlite3.Connection` (с `row_factory = sqlite3.Row`), `scraper.db.init_db(conn: sqlite3.Connection) -> None` (создаёт таблицы `documents`, `comments`, `crawl_queue`, если их ещё нет).

- [ ] **Step 1: Написать `requirements.txt`**

```
requests>=2.31,<3
beautifulsoup4>=4.12,<5
lxml>=4.9,<6
pytest>=7.4,<8
```

- [ ] **Step 2: Создать venv и установить зависимости**

Run:
```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
```
(на Linux/macOS: `.venv/bin/pip install -r requirements.txt`)

- [ ] **Step 3: Создать пустые файлы пакета**

Создать `scraper/__init__.py` и `scraper/parsers/__init__.py` — оба пустые (0 байт). Это делает `scraper` и `scraper.parsers` импортируемыми пакетами.

- [ ] **Step 4: Написать падающий тест схемы**

```python
# tests/test_db.py
import sqlite3

from scraper import db


def _connect():
    conn = sqlite3.connect(":memory:")
    db.init_db(conn)
    return conn


def test_init_db_creates_expected_tables():
    conn = _connect()
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"documents", "comments", "crawl_queue"}.issubset(tables)


def test_documents_table_has_expected_columns():
    conn = _connect()
    columns = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
    assert columns == {
        "id", "external_id", "section", "url", "title_ru", "title_kk",
        "status", "doc_type", "government_body", "created_date",
        "discussion_end_date", "comments_total", "likes_count",
        "dislikes_count", "raw_html_ru", "raw_html_kk", "first_seen_at",
        "last_checked_at",
    }


def test_comments_table_has_expected_columns():
    conn = _connect()
    columns = {row[1] for row in conn.execute("PRAGMA table_info(comments)")}
    assert columns == {
        "id", "document_id", "external_comment_id",
        "parent_external_comment_id", "author_name", "body", "article_ref",
        "status", "commented_at_raw", "first_seen_at",
    }


def test_crawl_queue_table_has_expected_columns():
    conn = _connect()
    columns = {row[1] for row in conn.execute("PRAGMA table_info(crawl_queue)")}
    assert columns == {
        "url", "page_type", "section", "status", "attempts", "last_error",
        "discovered_at", "processed_at",
    }
```

- [ ] **Step 5: Запустить тест и убедиться, что он падает**

Run: `.venv/Scripts/pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.db'`

- [ ] **Step 6: Реализовать `scraper/db.py`**

```python
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id INTEGER NOT NULL UNIQUE,
    section TEXT NOT NULL,
    url TEXT NOT NULL,
    title_ru TEXT,
    title_kk TEXT,
    status TEXT,
    doc_type TEXT,
    government_body TEXT,
    created_date TEXT,
    discussion_end_date TEXT,
    comments_total INTEGER,
    likes_count INTEGER,
    dislikes_count INTEGER,
    raw_html_ru TEXT,
    raw_html_kk TEXT,
    first_seen_at TEXT NOT NULL,
    last_checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    external_comment_id INTEGER NOT NULL,
    parent_external_comment_id INTEGER,
    author_name TEXT,
    body TEXT NOT NULL,
    article_ref TEXT,
    status TEXT,
    commented_at_raw TEXT,
    first_seen_at TEXT NOT NULL,
    UNIQUE(document_id, external_comment_id)
);

CREATE TABLE IF NOT EXISTS crawl_queue (
    url TEXT PRIMARY KEY,
    page_type TEXT NOT NULL,
    section TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    discovered_at TEXT NOT NULL,
    processed_at TEXT
);
"""


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()
```

- [ ] **Step 7: Запустить тест и убедиться, что он проходит**

Run: `.venv/Scripts/pytest tests/test_db.py -v`
Expected: PASS (3 passed)

- [ ] **Step 8: Закоммитить**

```bash
git add requirements.txt scraper/__init__.py scraper/parsers/__init__.py scraper/db.py tests/test_db.py
git commit -m "feat: добавить схему SQLite и каркас проекта"
```

---

### Task 2: Очередь обхода (`crawl_queue`)

**Files:**
- Create: `scraper/queue.py`
- Test: `tests/test_queue.py`

**Interfaces:**
- Consumes: `scraper.db.connect`, `scraper.db.init_db` (Task 1).
- Produces: `enqueue(conn, url: str, page_type: str, discovered_at: str, section: str | None = None) -> None`, `next_pending(conn, page_type: str) -> str | None`, `section_for(conn, url: str) -> str | None`, `mark_done(conn, url: str, processed_at: str) -> None`, `mark_error(conn, url: str, error_message: str, processed_at: str) -> None`, `requeue_stale_documents(conn, older_than_iso: str) -> None`.

`section` существует в очереди отдельно от `documents.section`, потому что карточки документов доступны по общему маршруту `/npa/view?id=...` одинаково для всех разделов сайта — по самому URL документа невозможно понять, из какого раздела (`/list`, `/Arvlist`, `/application/withdraw`, `/list?types[]=...` для КДРП) он был обнаружен. Раздел известен только в момент обработки списочной страницы, поэтому сохраняется в очереди при постановке документа в неё и читается обратно при обработке (см. Task 8).

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_queue.py
import sqlite3

from scraper import db, queue


def _connect():
    conn = sqlite3.connect(":memory:")
    db.init_db(conn)
    return conn


def test_enqueue_then_next_pending_returns_url():
    conn = _connect()
    queue.enqueue(conn, "https://example.test/list", "list", "2026-09-15T00:00:00")
    assert queue.next_pending(conn, "list") == "https://example.test/list"
    assert queue.next_pending(conn, "document") is None


def test_enqueue_is_idempotent_for_same_url():
    conn = _connect()
    queue.enqueue(conn, "https://example.test/list", "list", "t1")
    queue.enqueue(conn, "https://example.test/list", "list", "t2")
    count = conn.execute("SELECT COUNT(*) AS n FROM crawl_queue").fetchone()["n"]
    assert count == 1


def test_mark_done_removes_url_from_pending():
    conn = _connect()
    queue.enqueue(conn, "https://example.test/list", "list", "t1")
    queue.mark_done(conn, "https://example.test/list", "t2")
    assert queue.next_pending(conn, "list") is None
    row = conn.execute(
        "SELECT status, processed_at, attempts FROM crawl_queue WHERE url = ?",
        ("https://example.test/list",),
    ).fetchone()
    assert row["status"] == "done"
    assert row["processed_at"] == "t2"
    assert row["attempts"] == 1


def test_mark_error_records_message_and_keeps_out_of_pending():
    conn = _connect()
    queue.enqueue(conn, "https://example.test/list", "list", "t1")
    queue.mark_error(conn, "https://example.test/list", "timeout", "t2")
    assert queue.next_pending(conn, "list") is None
    row = conn.execute(
        "SELECT status, last_error FROM crawl_queue WHERE url = ?",
        ("https://example.test/list",),
    ).fetchone()
    assert row["status"] == "error"
    assert row["last_error"] == "timeout"


def test_enqueue_stores_section_and_section_for_reads_it_back():
    conn = _connect()
    queue.enqueue(conn, "https://example.test/npa/view?id=1", "document", "t1", section="arv")
    assert queue.section_for(conn, "https://example.test/npa/view?id=1") == "arv"


def test_section_for_returns_none_for_unknown_url():
    conn = _connect()
    assert queue.section_for(conn, "https://example.test/missing") is None


def test_requeue_stale_documents_resets_old_done_documents_only():
    conn = _connect()
    queue.enqueue(conn, "https://example.test/doc-old", "document", "t0")
    queue.enqueue(conn, "https://example.test/doc-new", "document", "t0")
    queue.enqueue(conn, "https://example.test/list", "list", "t0")
    queue.mark_done(conn, "https://example.test/doc-old", "2026-09-01T00:00:00")
    queue.mark_done(conn, "https://example.test/doc-new", "2026-09-14T00:00:00")
    queue.mark_done(conn, "https://example.test/list", "2026-09-01T00:00:00")

    queue.requeue_stale_documents(conn, "2026-09-10T00:00:00")

    assert queue.next_pending(conn, "document") == "https://example.test/doc-old"
    row_new = conn.execute(
        "SELECT status FROM crawl_queue WHERE url = ?",
        ("https://example.test/doc-new",),
    ).fetchone()
    assert row_new["status"] == "done"
    row_list = conn.execute(
        "SELECT status FROM crawl_queue WHERE url = ?",
        ("https://example.test/list",),
    ).fetchone()
    assert row_list["status"] == "done"
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `.venv/Scripts/pytest tests/test_queue.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.queue'`

- [ ] **Step 3: Реализовать `scraper/queue.py`**

```python
def enqueue(conn, url, page_type, discovered_at, section=None):
    conn.execute(
        "INSERT OR IGNORE INTO crawl_queue (url, page_type, section, status, attempts, discovered_at) "
        "VALUES (?, ?, ?, 'pending', 0, ?)",
        (url, page_type, section, discovered_at),
    )
    conn.commit()


def next_pending(conn, page_type):
    row = conn.execute(
        "SELECT url FROM crawl_queue WHERE page_type = ? AND status = 'pending' "
        "ORDER BY discovered_at LIMIT 1",
        (page_type,),
    ).fetchone()
    return row["url"] if row else None


def section_for(conn, url):
    row = conn.execute(
        "SELECT section FROM crawl_queue WHERE url = ?", (url,)
    ).fetchone()
    return row["section"] if row else None


def mark_done(conn, url, processed_at):
    conn.execute(
        "UPDATE crawl_queue SET status = 'done', processed_at = ?, attempts = attempts + 1 "
        "WHERE url = ?",
        (processed_at, url),
    )
    conn.commit()


def mark_error(conn, url, error_message, processed_at):
    conn.execute(
        "UPDATE crawl_queue SET status = 'error', last_error = ?, processed_at = ?, "
        "attempts = attempts + 1 WHERE url = ?",
        (error_message, processed_at, url),
    )
    conn.commit()


def requeue_stale_documents(conn, older_than_iso):
    conn.execute(
        "UPDATE crawl_queue SET status = 'pending' WHERE page_type = 'document' "
        "AND status = 'done' AND processed_at < ?",
        (older_than_iso,),
    )
    conn.commit()
```

- [ ] **Step 4: Запустить тест и убедиться, что он проходит**

Run: `.venv/Scripts/pytest tests/test_queue.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Закоммитить**

```bash
git add scraper/queue.py tests/test_queue.py
git commit -m "feat: реализовать очередь обхода crawl_queue"
```

---

### Task 3: Вежливый HTTP-клиент (`Fetcher`)

**Files:**
- Create: `scraper/fetch.py`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Produces: `class Fetcher(user_agent: str, delay: float = 0.6, jitter: float = 0.4, max_retries: int = 3, backoff: float = 2.0, session=None, sleep_func=time.sleep, random_func=random.random)` с методами `get(url: str) -> requests.Response`-совместимый объект (атрибуты `.status_code`, `.text`) и `set_language(lang: str, location: str = "/") -> None`.

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_fetch.py
import requests
import pytest

from scraper.fetch import Fetcher


class FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_get_returns_response_on_first_success():
    session = FakeSession([FakeResponse(200, "ok")])
    fetcher = Fetcher(
        "test-agent", session=session, sleep_func=lambda s: None, random_func=lambda: 0
    )
    response = fetcher.get("https://example.test/page")
    assert response.status_code == 200
    assert session.calls == ["https://example.test/page"]


def test_get_retries_on_server_error_then_succeeds():
    session = FakeSession([FakeResponse(500), FakeResponse(200, "ok")])
    fetcher = Fetcher(
        "test-agent", max_retries=3, session=session,
        sleep_func=lambda s: None, random_func=lambda: 0,
    )
    response = fetcher.get("https://example.test/page")
    assert response.status_code == 200
    assert len(session.calls) == 2


def test_get_raises_after_exhausting_retries_on_network_error():
    session = FakeSession([requests.ConnectionError("boom"), requests.ConnectionError("boom")])
    fetcher = Fetcher(
        "test-agent", max_retries=1, session=session,
        sleep_func=lambda s: None, random_func=lambda: 0,
    )
    with pytest.raises(requests.ConnectionError):
        fetcher.get("https://example.test/page")


def test_get_returns_404_response_without_retrying():
    session = FakeSession([FakeResponse(404)])
    fetcher = Fetcher(
        "test-agent", session=session, sleep_func=lambda s: None, random_func=lambda: 0
    )
    response = fetcher.get("https://example.test/missing")
    assert response.status_code == 404
    assert len(session.calls) == 1


def test_get_waits_between_requests():
    session = FakeSession([FakeResponse(200, "ok")])
    sleeps = []
    fetcher = Fetcher(
        "test-agent", delay=0.6, jitter=0.4, session=session,
        sleep_func=sleeps.append, random_func=lambda: 0.5,
    )
    fetcher.get("https://example.test/page")
    assert sleeps == [0.6 + 0.5 * 0.4]


def test_set_language_requests_changelang_endpoint():
    session = FakeSession([FakeResponse(302, "")])
    fetcher = Fetcher(
        "test-agent", session=session, sleep_func=lambda s: None, random_func=lambda: 0
    )
    fetcher.set_language("kk", location="/npa/view?id=1")
    assert session.calls == [
        "https://legalacts.egov.kz/application/changelang?lang=kk&location=/npa/view?id=1"
    ]
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `.venv/Scripts/pytest tests/test_fetch.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.fetch'`

- [ ] **Step 3: Реализовать `scraper/fetch.py`**

```python
import random
import time

import requests

BASE_URL = "https://legalacts.egov.kz"


class Fetcher:
    def __init__(
        self, user_agent, delay=0.6, jitter=0.4, max_retries=3, backoff=2.0,
        session=None, sleep_func=time.sleep, random_func=random.random,
    ):
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.delay = delay
        self.jitter = jitter
        self.max_retries = max_retries
        self.backoff = backoff
        self._sleep = sleep_func
        self._random = random_func

    def set_language(self, lang, location="/"):
        url = f"{BASE_URL}/application/changelang?lang={lang}&location={location}"
        self.get(url)

    def get(self, url):
        attempt = 0
        while True:
            self._sleep(self.delay + self._random() * self.jitter)
            try:
                response = self.session.get(url, timeout=15)
            except requests.RequestException:
                attempt += 1
                if attempt > self.max_retries:
                    raise
                self._sleep(self.backoff**attempt)
                continue
            if response.status_code >= 500 and attempt < self.max_retries:
                attempt += 1
                self._sleep(self.backoff**attempt)
                continue
            return response
```

- [ ] **Step 4: Запустить тест и убедиться, что он проходит**

Run: `.venv/Scripts/pytest tests/test_fetch.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Закоммитить**

```bash
git add scraper/fetch.py tests/test_fetch.py
git commit -m "feat: добавить вежливый HTTP-клиент с ретраями"
```

---

### Task 4: Парсер списочных страниц

**Files:**
- Create: `scraper/parsers/list_page.py`
- Test: `tests/test_list_page.py`
- Use fixture: `tests/fixtures/list_page.html` (уже сохранена — реальная страница `/list?status=IN_ARCHIVE`)

**Interfaces:**
- Produces: `parse_list_page(html: str) -> list[dict]` (каждый элемент: `{"url": str, "title": str}`), `parse_total_pages(html: str) -> int`.

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_list_page.py
from pathlib import Path

from scraper.parsers import list_page

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_list_page_extracts_document_cards():
    html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    cards = list_page.parse_list_page(html)
    assert len(cards) == 5
    assert cards[0]["url"] == "https://legalacts.egov.kz/npa/view?id=15908401"
    assert "внесении изменений" in cards[0]["title"].lower()


def test_parse_total_pages_reads_script_value():
    html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    assert list_page.parse_total_pages(html) == 29852


def test_parse_total_pages_defaults_to_one_when_absent():
    assert list_page.parse_total_pages("<html><body>Нет данных</body></html>") == 1
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `.venv/Scripts/pytest tests/test_list_page.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.parsers.list_page'`

- [ ] **Step 3: Реализовать `scraper/parsers/list_page.py`**

```python
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BASE_URL = "https://legalacts.egov.kz"
TOTAL_PAGES_RE = re.compile(r"totalPages:\s*(\d+)")


def parse_list_page(html):
    soup = BeautifulSoup(html, "lxml")
    cards = []
    for block in soup.select("div.contentlist"):
        link = block.select_one("h3 a[href]")
        if link is None:
            continue
        cards.append({
            "url": urljoin(BASE_URL, link["href"]),
            "title": link.get_text(strip=True),
        })
    return cards


def parse_total_pages(html):
    match = TOTAL_PAGES_RE.search(html)
    return int(match.group(1)) if match else 1
```

- [ ] **Step 4: Запустить тест и убедиться, что он проходит**

Run: `.venv/Scripts/pytest tests/test_list_page.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Закоммитить**

```bash
git add scraper/parsers/list_page.py tests/test_list_page.py
git commit -m "feat: реализовать парсер списочных страниц"
```

---

### Task 5: Парсер карточки документа

**Files:**
- Create: `scraper/parsers/document_page.py`
- Test: `tests/test_document_page.py`
- Use fixtures: `tests/fixtures/document_no_comments.html`, `tests/fixtures/document_with_comments.html`, `tests/fixtures/document_with_comments_kk.html` (все — реальные страницы `/npa/view?id=...`)

**Interfaces:**
- Produces: `parse_document_page(html: str) -> dict` с ключами `title, status, doc_type, created_date, discussion_end_date, government_body, comments_total, likes_count, dislikes_count`.

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_document_page.py
from pathlib import Path

from scraper.parsers import document_page

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_document_page_extracts_core_fields_without_comments():
    data = document_page.parse_document_page(_read("document_no_comments.html"))
    assert data["title"] == (
        "О понижении размера ставки налогов при применении специального "
        "налогового режима на основе упрощенной декларации в городе Каражал"
    )
    assert data["status"] == "На публичном обсуждении"
    assert data["doc_type"] == "Решение"
    assert data["created_date"] == "15/09/2026"
    assert data["discussion_end_date"] == "30/09/2026"
    assert data["government_body"] == "Аппарат акима города Каражал"
    assert data["comments_total"] == 0
    assert data["likes_count"] == 0
    assert data["dislikes_count"] == 0


def test_parse_document_page_reads_counts_with_comments():
    data = document_page.parse_document_page(_read("document_with_comments.html"))
    assert data["status"] == "Архив"
    assert data["doc_type"] == "Приказ"
    assert data["government_body"] == "Министерство труда и социальной защиты населения РК"
    assert data["comments_total"] == 24
    assert data["likes_count"] == 0
    assert data["dislikes_count"] == 1


def test_parse_document_page_reads_kk_title():
    data = document_page.parse_document_page(_read("document_with_comments_kk.html"))
    assert data["title"].startswith("Қазақстан Республикасы")
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `.venv/Scripts/pytest tests/test_document_page.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.parsers.document_page'`

- [ ] **Step 3: Реализовать `scraper/parsers/document_page.py`**

```python
import re

from bs4 import BeautifulSoup

LABEL_MAP = {
    "status": "Статус:",
    "doc_type": "Тип НПА:",
    "created_date": "Дата создания:",
    "discussion_end_date": "Публичное обсуждение до:",
}


def _label_text(soup, label):
    for small in soup.select(".view-npa small"):
        b = small.find("b")
        if b is not None and b.get_text(strip=True) == label:
            b.extract()
            return small.get_text(strip=True)
    return None


def _count_by_class_prefix(soup, prefix):
    span = soup.find("span", class_=re.compile("^" + re.escape(prefix)))
    if span is None:
        return 0
    text = span.get_text(strip=True)
    return int(text) if text.isdigit() else 0


def parse_document_page(html):
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one(".view-npa h2")
    title = title_el.get_text(strip=True) if title_el else None

    fields = {key: _label_text(soup, label) for key, label in LABEL_MAP.items()}

    government_body_el = soup.select_one(".blog-info .gov-parent")
    government_body = (
        government_body_el.get_text(strip=True) if government_body_el else None
    )

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
```

- [ ] **Step 4: Запустить тест и убедиться, что он проходит**

Run: `.venv/Scripts/pytest tests/test_document_page.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Закоммитить**

```bash
git add scraper/parsers/document_page.py tests/test_document_page.py
git commit -m "feat: реализовать парсер карточки документа"
```

---

### Task 6: Парсер комментариев

**Files:**
- Create: `scraper/parsers/comments.py`
- Test: `tests/test_comments.py`
- Use fixtures: `tests/fixtures/document_with_comments.html`, `tests/fixtures/document_no_comments.html`

**Interfaces:**
- Produces: `parse_comments(html: str) -> list[dict]`, каждый элемент — `{"external_id": int | None, "parent_external_id": int | None, "author_name": str | None, "body": str, "article_ref": str | None, "status": "accepted" | "rejected" | None, "commented_at_raw": str | None}`. Порядок: для каждого комментария верхнего уровня сразу следом идёт его вложенный ответ (если есть) — родитель перед ответом.

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_comments.py
from pathlib import Path

from scraper.parsers import comments as comments_parser

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_comments_flattens_top_level_and_replies():
    result = comments_parser.parse_comments(_read("document_with_comments.html"))
    assert len(result) == 20

    first = result[0]
    assert first["external_id"] == 15907499
    assert first["parent_external_id"] is None
    assert first["author_name"] == "СУХАНОВ АНДРЕЙ"
    assert first["status"] == "rejected"
    assert "Полная версия" in first["body"]
    assert first["commented_at_raw"] == "10/09 - 11:05"

    reply = result[1]
    assert reply["external_id"] == 15907783
    assert reply["parent_external_id"] == 15907499
    assert reply["author_name"] == "Министерство труда и социальной защиты населения РК"
    assert reply["status"] is None
    assert reply["commented_at_raw"] == "10/09 - 12:24"


def test_parse_comments_returns_empty_list_when_no_comments():
    assert comments_parser.parse_comments(_read("document_no_comments.html")) == []
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `.venv/Scripts/pytest tests/test_comments.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.parsers.comments'`

- [ ] **Step 3: Реализовать `scraper/parsers/comments.py`**

```python
import re

from bs4 import BeautifulSoup

STATUS_BY_TITLE = {
    "Принято": "accepted",
    "Не принято": "rejected",
}

TIMESTAMP_RE = re.compile(r"\d{2}/\d{2} - \d{2}:\d{2}")


def parse_comments(html):
    soup = BeautifulSoup(html, "lxml")
    container = soup.select_one(".main-comments")
    if container is None:
        return []
    result = []
    for media in container.find_all("div", class_="media", recursive=False):
        result.extend(_parse_comment_node(media, parent_external_id=None))
    return result


def _parse_comment_node(media, parent_external_id):
    body = media.find("div", class_="media-body", recursive=False)
    if body is None:
        return []

    headings = body.find_all("h4", class_="media-heading", recursive=False)
    author_name = headings[0].get_text(strip=True) if headings else None

    heading_text = " ".join(h.get_text(" ", strip=True) for h in headings)
    timestamp_match = TIMESTAMP_RE.search(heading_text)
    commented_at_raw = timestamp_match.group() if timestamp_match else None

    article_ref = None
    status = None
    if len(headings) > 1:
        second = headings[1]
        ref_link = second.select_one("a.view-comment-part[npa-id]")
        if ref_link is not None:
            article_ref = ref_link.get_text(strip=True)
        status_icon = second.select_one("i.liker")
        if status_icon is not None:
            status = STATUS_BY_TITLE.get(status_icon.get("title", ""))

    text_el = body.find("p", recursive=False)
    external_id = None
    text = ""
    if text_el is not None:
        text = text_el.get_text(strip=True)
        if text_el.has_attr("id"):
            external_id = int(text_el["id"])

    comment = {
        "external_id": external_id,
        "parent_external_id": parent_external_id,
        "author_name": author_name,
        "body": text,
        "article_ref": article_ref,
        "status": status,
        "commented_at_raw": commented_at_raw,
    }

    result = [comment]
    nested = body.find("div", class_="media", recursive=False)
    if nested is not None:
        result.extend(_parse_comment_node(nested, parent_external_id=external_id))
    return result
```

- [ ] **Step 4: Запустить тест и убедиться, что он проходит**

Run: `.venv/Scripts/pytest tests/test_comments.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Закоммитить**

```bash
git add scraper/parsers/comments.py tests/test_comments.py
git commit -m "feat: реализовать парсер комментариев с вложенными ответами"
```

**Известное ограничение (не блокирует MVP, задокументировать в коде не нужно — это уже описано в спеке):** `comments_total` документа считает комментарии по всем вкладкам экспертизы портала ("Комментарий", "НПП Атамекен", "Антикоррупционная экспертиза" и т.д.), а `parse_comments` разбирает только вкладку, отрисованную по умолчанию ("Комментарий" — общий блок публичных комментариев). Поэтому число сохранённых комментариев может быть меньше `comments_total`.

---

### Task 7: Сохранение в SQLite

**Files:**
- Create: `scraper/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `scraper.db.connect`, `scraper.db.init_db` (Task 1); формат `fields`-словаря из `document_page.parse_document_page` (Task 5) плюс ключи `title_ru`, `raw_html_ru`, опционально `title_kk`, `raw_html_kk`; формат элементов списка из `comments.parse_comments` (Task 6).
- Produces: `upsert_document(conn, external_id: int, section: str, url: str, fields: dict, now: str) -> int` (возвращает `documents.id`), `upsert_comments(conn, document_id: int, comments: list[dict], now: str) -> None`.

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_store.py
import sqlite3

from scraper import db, store


def _connect():
    conn = sqlite3.connect(":memory:")
    db.init_db(conn)
    return conn


def test_upsert_document_inserts_new_row():
    conn = _connect()
    fields = {
        "title_ru": "Заголовок", "status": "Архив", "doc_type": "Приказ",
        "government_body": "Минтруда", "created_date": "09/09/2026",
        "discussion_end_date": "14/09/2026", "comments_total": 24,
        "likes_count": 0, "dislikes_count": 1, "raw_html_ru": "<html>ru</html>",
    }
    doc_id = store.upsert_document(
        conn, 15906353, "npa", "https://legalacts.egov.kz/npa/view?id=15906353",
        fields, "2026-09-15T00:00:00",
    )
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    assert row["external_id"] == 15906353
    assert row["title_ru"] == "Заголовок"
    assert row["comments_total"] == 24
    assert row["first_seen_at"] == "2026-09-15T00:00:00"
    assert row["last_checked_at"] == "2026-09-15T00:00:00"


def test_upsert_document_updates_existing_and_preserves_first_seen_at():
    conn = _connect()
    store.upsert_document(conn, 1, "npa", "url1", {"title_ru": "V1"}, "2026-09-01T00:00:00")
    store.upsert_document(conn, 1, "npa", "url1", {"title_ru": "V2"}, "2026-09-15T00:00:00")
    row = conn.execute("SELECT * FROM documents WHERE external_id = 1").fetchone()
    assert row["title_ru"] == "V2"
    assert row["first_seen_at"] == "2026-09-01T00:00:00"
    assert row["last_checked_at"] == "2026-09-15T00:00:00"


def test_upsert_document_keeps_kk_fields_when_not_provided():
    conn = _connect()
    store.upsert_document(
        conn, 1, "npa", "url1", {"title_ru": "V1", "title_kk": "KK1"}, "t1"
    )
    store.upsert_document(conn, 1, "npa", "url1", {"title_ru": "V2"}, "t2")
    row = conn.execute("SELECT * FROM documents WHERE external_id = 1").fetchone()
    assert row["title_kk"] == "KK1"


def test_upsert_comments_inserts_and_preserves_first_seen_at_on_update():
    conn = _connect()
    doc_id = store.upsert_document(conn, 1, "npa", "url1", {"title_ru": "V"}, "t0")
    comment = {
        "external_id": 100, "parent_external_id": None, "author_name": "A",
        "body": "text", "article_ref": None, "status": "rejected",
        "commented_at_raw": "10/09 - 11:05",
    }
    store.upsert_comments(conn, doc_id, [comment], "2026-09-01T00:00:00")

    updated_comment = dict(comment, status="accepted")
    store.upsert_comments(conn, doc_id, [updated_comment], "2026-09-15T00:00:00")

    row = conn.execute(
        "SELECT * FROM comments WHERE document_id = ? AND external_comment_id = 100",
        (doc_id,),
    ).fetchone()
    assert row["status"] == "accepted"
    assert row["first_seen_at"] == "2026-09-01T00:00:00"
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `.venv/Scripts/pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.store'`

- [ ] **Step 3: Реализовать `scraper/store.py`**

```python
DOCUMENT_FIELD_ORDER = [
    "section", "url", "title_ru", "title_kk", "status", "doc_type",
    "government_body", "created_date", "discussion_end_date",
    "comments_total", "likes_count", "dislikes_count", "raw_html_ru",
    "raw_html_kk",
]


def upsert_document(conn, external_id, section, url, fields, now):
    existing = conn.execute(
        "SELECT id, title_kk, raw_html_kk FROM documents WHERE external_id = ?",
        (external_id,),
    ).fetchone()

    title_kk = fields.get("title_kk") or (existing["title_kk"] if existing else None)
    raw_html_kk = fields.get("raw_html_kk") or (
        existing["raw_html_kk"] if existing else None
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
        conn.execute(
            "INSERT INTO documents (external_id, " + ", ".join(DOCUMENT_FIELD_ORDER) +
            ", first_seen_at, last_checked_at) VALUES (?, "
            + ", ".join("?" for _ in DOCUMENT_FIELD_ORDER) + ", ?, ?)",
            (external_id, *(values[key] for key in DOCUMENT_FIELD_ORDER), now, now),
        )
        conn.commit()
        return conn.execute(
            "SELECT id FROM documents WHERE external_id = ?", (external_id,)
        ).fetchone()["id"]

    conn.execute(
        "UPDATE documents SET "
        + ", ".join(f"{key} = ?" for key in DOCUMENT_FIELD_ORDER)
        + ", last_checked_at = ? WHERE id = ?",
        (*(values[key] for key in DOCUMENT_FIELD_ORDER), now, existing["id"]),
    )
    conn.commit()
    return existing["id"]


def upsert_comments(conn, document_id, comments, now):
    for comment in comments:
        conn.execute(
            """
            INSERT INTO comments (
                document_id, external_comment_id, parent_external_comment_id,
                author_name, body, article_ref, status, commented_at_raw,
                first_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id, external_comment_id) DO UPDATE SET
                parent_external_comment_id = excluded.parent_external_comment_id,
                author_name = excluded.author_name,
                body = excluded.body,
                article_ref = excluded.article_ref,
                status = excluded.status,
                commented_at_raw = excluded.commented_at_raw
            """,
            (
                document_id, comment["external_id"], comment["parent_external_id"],
                comment["author_name"], comment["body"], comment["article_ref"],
                comment["status"], comment["commented_at_raw"], now,
            ),
        )
    conn.commit()
```

- [ ] **Step 4: Запустить тест и убедиться, что он проходит**

Run: `.venv/Scripts/pytest tests/test_store.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Закоммитить**

```bash
git add scraper/store.py tests/test_store.py
git commit -m "feat: реализовать сохранение документов и комментариев в SQLite"
```

---

### Task 8: Оркестрация обхода и CLI

**Files:**
- Create: `scraper/run.py`
- Test: `tests/test_run.py`

**Interfaces:**
- Consumes: всё из Task 1–7 — `db.connect`, `db.init_db`, `queue.enqueue/next_pending/section_for/mark_done/mark_error/requeue_stale_documents`, `fetch.Fetcher`, `parsers.list_page.parse_list_page/parse_total_pages`, `parsers.document_page.parse_document_page`, `parsers.comments.parse_comments`, `store.upsert_document/upsert_comments`.
- Produces: `process_list_entry(conn, fetcher, url: str, section: str = "npa") -> None`, `process_document_entry(conn, fetcher, url: str, section: str = "npa") -> None`, `run(db_path: str, limit: int | None = None) -> None`, `main() -> None` (CLI entry point с флагами `--db` и `--limit`).

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_run.py
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from scraper import db, queue
from scraper import run as run_module

FIXTURES = Path(__file__).parent / "fixtures"


def _connect():
    conn = sqlite3.connect(":memory:")
    db.init_db(conn)
    return conn


class StubFetcher:
    def __init__(self, pages):
        self._pages = {url: list(v) if isinstance(v, list) else [v] for url, v in pages.items()}
        self.calls = []
        self.lang_calls = []

    def get(self, url):
        self.calls.append(url)
        remaining = self._pages[url]
        html = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        return SimpleNamespace(text=html, status_code=200)

    def set_language(self, lang, location="/"):
        self.lang_calls.append(lang)


def test_process_list_entry_enqueues_documents_and_next_page():
    conn = _connect()
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE"
    fetcher = StubFetcher({url: list_html})

    run_module.process_list_entry(conn, fetcher, url, section="npa")

    doc_rows = conn.execute(
        "SELECT url FROM crawl_queue WHERE page_type = 'document'"
    ).fetchall()
    assert len(doc_rows) == 5
    assert queue.section_for(conn, doc_rows[0]["url"]) == "npa"

    page_rows = [
        row["url"]
        for row in conn.execute(
            "SELECT url FROM crawl_queue WHERE page_type = 'list'"
        ).fetchall()
    ]
    assert len(page_rows) == 1
    assert "page=2" in page_rows[0]
    assert "status=IN_ARCHIVE" in page_rows[0]
    assert queue.section_for(conn, page_rows[0]) == "npa"


def test_process_list_entry_stops_pagination_at_last_page():
    conn = _connect()
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE&page=29852"
    fetcher = StubFetcher({url: list_html})

    run_module.process_list_entry(conn, fetcher, url)

    page_rows = conn.execute(
        "SELECT url FROM crawl_queue WHERE page_type = 'list'"
    ).fetchall()
    assert len(page_rows) == 0


def test_process_document_entry_stores_document_and_comments():
    conn = _connect()
    ru_html = (FIXTURES / "document_with_comments.html").read_text(encoding="utf-8")
    kk_html = (FIXTURES / "document_with_comments_kk.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    fetcher = StubFetcher({url: [ru_html, kk_html]})

    run_module.process_document_entry(conn, fetcher, url, section="withdraw")

    doc = conn.execute(
        "SELECT * FROM documents WHERE external_id = 15906353"
    ).fetchone()
    assert doc["section"] == "withdraw"
    assert doc["status"] == "Архив"
    assert doc["title_kk"].startswith("Қазақстан Республикасы")
    assert doc["raw_html_ru"] == ru_html
    assert doc["raw_html_kk"] == kk_html

    comment_count = conn.execute(
        "SELECT COUNT(*) AS n FROM comments WHERE document_id = ?", (doc["id"],)
    ).fetchone()["n"]
    assert comment_count == 20
    assert fetcher.lang_calls == ["kk", "ru"]


def test_run_seeds_queue_and_respects_limit(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    seed_url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE"

    monkeypatch.setattr(run_module, "SEED_LIST_URLS", [("npa", seed_url)])
    fake_fetcher = StubFetcher({seed_url: list_html})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fake_fetcher)

    run_module.run(db_path, limit=1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    doc_rows = conn.execute(
        "SELECT url FROM crawl_queue WHERE page_type = 'document'"
    ).fetchall()
    assert len(doc_rows) == 5
    assert queue.section_for(conn, doc_rows[0]["url"]) == "npa"
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `.venv/Scripts/pytest tests/test_run.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scraper.run'`

- [ ] **Step 3: Реализовать `scraper/run.py`**

```python
import argparse
import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import db, queue, store
from .fetch import Fetcher
from .parsers import comments as comments_parser
from .parsers import document_page, list_page

BASE_URL = "https://legalacts.egov.kz"
USER_AGENT = (
    "legalacts-research-bot/0.1 (личный исследовательский проект; "
    "контакт: k.nefyodov@qbs.kz)"
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


def seed_queue(conn):
    discovered = now_iso()
    for section, url in SEED_LIST_URLS:
        queue.enqueue(conn, url, "list", discovered, section=section)


def _current_page(url):
    query = dict(parse_qsl(urlsplit(url).query))
    return int(query.get("page", 1))


def _set_page_param(url, page):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["page"] = str(page)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def process_list_entry(conn, fetcher, url, section="npa"):
    response = fetcher.get(url)
    html = response.text

    discovered = now_iso()
    for card in list_page.parse_list_page(html):
        queue.enqueue(conn, card["url"], "document", discovered, section=section)

    total_pages = list_page.parse_total_pages(html)
    current_page = _current_page(url)
    if current_page < total_pages:
        queue.enqueue(
            conn, _set_page_param(url, current_page + 1), "list", discovered, section=section
        )


def process_document_entry(conn, fetcher, url, section="npa"):
    ru_response = fetcher.get(url)
    ru_html = ru_response.text
    fields = document_page.parse_document_page(ru_html)
    fields["title_ru"] = fields.pop("title")
    fields["raw_html_ru"] = ru_html

    fetcher.set_language("kk", location=url)
    kk_response = fetcher.get(url)
    kk_html = kk_response.text
    kk_fields = document_page.parse_document_page(kk_html)
    fields["title_kk"] = kk_fields["title"]
    fields["raw_html_kk"] = kk_html
    fetcher.set_language("ru", location=url)

    external_id = int(dict(parse_qsl(urlsplit(url).query))["id"])
    parsed_comments = comments_parser.parse_comments(ru_html)

    timestamp = now_iso()
    document_id = store.upsert_document(conn, external_id, section, url, fields, timestamp)
    store.upsert_comments(conn, document_id, parsed_comments, timestamp)


def run(db_path, limit=None):
    conn = db.connect(db_path)
    db.init_db(conn)

    has_pending = (
        queue.next_pending(conn, "list") is not None
        or queue.next_pending(conn, "document") is not None
    )
    if not has_pending:
        seed_queue(conn)

    queue.requeue_stale_documents(
        conn,
        (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=STALE_AFTER_DAYS)
        ).isoformat(),
    )

    fetcher = Fetcher(USER_AGENT)
    processed = 0

    while limit is None or processed < limit:
        list_url = queue.next_pending(conn, "list")
        if list_url is not None:
            # Раздел записан в очередь при постановке этой строки (см. Task 2) —
            # по самому URL списочной страницы его тоже можно было бы вычислить
            # (/Arvlist, /application/withdraw, /list?types[]=... различимы),
            # но чтение из очереди даёт один источник истины и для списков, и для
            # документов, у которых URL раздел не выдаёт (Task 8).
            section = queue.section_for(conn, list_url) or "npa"
            try:
                process_list_entry(conn, fetcher, list_url, section=section)
                queue.mark_done(conn, list_url, now_iso())
            except Exception as exc:
                # Одна сломанная страница не должна останавливать весь обход (спек, раздел 3).
                queue.mark_error(conn, list_url, str(exc), now_iso())
            processed += 1
            continue

        document_url = queue.next_pending(conn, "document")
        if document_url is not None:
            section = queue.section_for(conn, document_url) or "npa"
            try:
                process_document_entry(conn, fetcher, document_url, section=section)
                queue.mark_done(conn, document_url, now_iso())
            except Exception as exc:
                queue.mark_error(conn, document_url, str(exc), now_iso())
            processed += 1
            continue

        break

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Обход портала legalacts.egov.kz")
    parser.add_argument("--db", default="legalacts.db")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(args.db, limit=args.limit)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Запустить тест и убедиться, что он проходит**

Run: `.venv/Scripts/pytest tests/test_run.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Запустить весь набор тестов проекта**

Run: `.venv/Scripts/pytest -v`
Expected: все тесты из Task 1–8 проходят (32 passed).

- [ ] **Step 6: Закоммитить**

```bash
git add scraper/run.py tests/test_run.py
git commit -m "feat: реализовать оркестрацию обхода и CLI-точку входа"
```

- [ ] **Step 7: Ручной sanity-check на живом сайте (см. спек, раздел 4)**

Run: `.venv/Scripts/python -m scraper.run --limit 5`
Expected: команда отрабатывает без необработанных исключений; файл `legalacts.db` появляется в корне проекта; `sqlite3 legalacts.db "SELECT COUNT(*) FROM documents;"` возвращает число ≥ 0 без ошибок. Затем повторный запуск `--limit 5` не должен падать и должен продолжать обход с того места, где остановился предыдущий (не пересоздавать очередь с нуля) — можно проверить через `sqlite3 legalacts.db "SELECT status, COUNT(*) FROM crawl_queue GROUP BY status;"` до и после.

---

## Самопроверка плана

- **Покрытие спека:** назначение/охват (спек §1) → seed-URL в Task 8; модель данных (спек §2, с уточнениями addendum) → Task 1 (схема) + Task 7 (upsert); обход/вежливость/ошибки (спек §3) → Task 3 (Fetcher) + Task 8 (try/except вокруг каждой записи очереди, задержки в Fetcher); резюмируемость/докачка (спек §1, §2) → Task 2 (`crawl_queue`) + Task 8 (`seed_queue` только при пустой очереди, `requeue_stale_documents`); технологии/структура/тесты (спек §4) → вся структура файлов плана, фикстуры уже в `tests/fixtures/`; robots.txt-решение (addendum) → `USER_AGENT` в Task 8 явно указывает контакт и назначение, запрет для `/npa/view`/`/application` сознательно не проверяется в коде (комментарий Global Constraints).
- **Плейсхолдеров нет:** каждый шаг либо содержит готовый код, либо точную bash/pytest-команду с ожидаемым результатом.
- **Согласованность типов:** `upsert_document` принимает `fields` в точности с теми ключами, которые возвращает `document_page.parse_document_page` (плюс `title_ru`/`raw_html_ru`/опционально `title_kk`/`raw_html_kk`, добавляемые в `run.process_document_entry`); `upsert_comments` принимает элементы в точности с ключами, которые возвращает `comments.parse_comments`; `queue.next_pending`/`mark_done`/`mark_error` используются в `run.py` с той же сигнатурой, что определена и протестирована в Task 2.
- **Исправлена реальная ошибка, найденная при первом черновике плана:** карточка документа всегда доступна по одному и тому же маршруту `/npa/view?id=...` независимо от раздела сайта (НПА/АРВ/КДРП/отозванные) — определить раздел по URL самого документа невозможно. Черновик пытался это сделать (`_section_for_url` по префиксу пути документа) и всегда возвращал `"npa"`. Исправлено: `crawl_queue` хранит `section`, вычисленный в момент обработки *списочной* страницы (где раздел действительно виден по URL), и прокидывается и в дочерние документы, и в следующую страницу пагинации; `run()` читает его через `queue.section_for` перед вызовом `process_list_entry`/`process_document_entry`.
