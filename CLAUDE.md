# CLAUDE.md

Всегда общайся с пользователем на русском языке

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Рабочий MVP реализован и покрыт тестами (43/43 passed). Это Python-скрипт без веб-фреймворка, который резюмируемо обходит портал `legalacts.egov.kz` (документы + обсуждения с комментариями) и сохраняет результат в локальную SQLite-базу.

Полная спецификация и мотивация решений: `docs/superpowers/specs/2026-09-15-legalacts-scraper-design.md`.
Пошаговый план реализации (уже выполнен, Task 1–8): `docs/superpowers/plans/2026-09-15-legalacts-scraper.md`.

## Setup

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Linux/macOS: .venv/bin/pip install -r requirements.txt
```

Python 3.8, зависимости: `requests`, `beautifulsoup4` + `lxml`, `pytest`.

## Commands

Тесты (все):

```bash
.venv/Scripts/pytest -v
```

Один тест / один файл:

```bash
.venv/Scripts/pytest tests/test_run.py -v
.venv/Scripts/pytest tests/test_run.py::test_process_list_entry_enqueues_documents_and_next_page -v
```

Запуск обхода:

```bash
.venv/Scripts/python -m scraper.run --db legalacts.db --limit 20
```

`--limit` ограничивает число обработанных записей очереди за один запуск (list-страница или карточка документа = 1 запись); без флага обход идёт до полного исчерпания очереди. Повторные запуски резюмируемы — очередь не пересоздаётся, если в ней уже есть необработанные записи, а `requeue_stale_documents` переоткрывает документы старше 7 дней для докачки.

Линтера в проекте нет.

## Architecture

- `scraper/db.py` — схема SQLite (`documents`, `comments`, `crawl_queue`) и `connect()`/`init_db()`.
- `scraper/queue.py` — `crawl_queue`, единственный источник истины о том, что уже обработано (двигатель резюмируемости): `enqueue`, `next_pending`, `section_for`, `mark_done`, `mark_error`, `requeue_stale_documents`.
- `scraper/fetch.py` — `Fetcher`: вежливый HTTP-клиент с задержкой между запросами, джиттером и ретраями на сетевых/5xx-ошибках; `set_language()` для переключения ru/kk через `/application/changelang`.
- `scraper/parsers/list_page.py`, `document_page.py`, `comments.py` — разбор HTML через BeautifulSoup+lxml по селекторам, подтверждённым на реальных страницах сайта (фикстуры в `tests/fixtures/`).
- `scraper/store.py` — upsert документов и комментариев (сохраняет `first_seen_at`, обновляет `last_checked_at`; kk-поля не затираются, если при очередном обходе не пришли).
- `scraper/run.py` — оркестрация: `process_list_entry`, `process_document_entry`, `run()` (главный цикл: list-страницы обрабатываются раньше document-страниц), `main()` (CLI, флаги `--db`/`--limit`). Сетевые/разбор-ошибки на уровне одной записи очереди не останавливают весь обход — запись помечается `error`, цикл продолжается.

**Обход двухуровневый и ленивый:** список → карточки документов; каждая обработанная list-страница сама добавляет в очередь только следующую страницу своей пагинации, а не все сразу. Раздел сайта (`section`: `npa`/`kdrp`/`arv`/`withdraw`) хранится в `crawl_queue` в момент постановки в очередь, а не выводится из URL документа — карточки всех разделов доступны по одному и тому же маршруту `/npa/view?id=...`, и раздел виден только на списочной странице, откуда документ был обнаружен.

**Известные ограничения (см. спек):**

- `comments_total` документа считает комментарии по всем вкладкам экспертизы портала; `parse_comments` разбирает только вкладку "Комментарий" — сохранённых комментариев может быть меньше `comments_total`.
- `robots.txt` запрещает `/npa/view` и `/application` — это сознательно игнорируется для этих путей (см. addendum в спеке); для остальных используемых путей (`/list`, `/Arvlist`) `robots.txt` соблюдается.
- `USER_AGENT` в `scraper/run.py` должен оставаться ASCII-совместимым (ISO-8859-1) — HTTP-заголовки не допускают произвольной кириллицы (RFC 7230 §3.2); это уже проверяется тестом `test_user_agent_is_latin1_encodable`.
