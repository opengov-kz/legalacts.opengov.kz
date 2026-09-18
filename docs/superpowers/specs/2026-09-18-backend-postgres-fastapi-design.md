# Дизайн: backend на PostgreSQL+SQLAlchemy+FastAPI (этап 1 из 2)

Дата: 2026-09-18
Статус: одобрен, готов к планированию реализации

## 0. Контекст и охват

Приложение разделяется на `backend` и `frontend` (каждый — в своей
директории, свой Docker-образ). Это дизайн **только backend-этапа**.
Frontend (JS-дашборд аналитики и мониторинга сбора) — отдельный
следующий этап со своим дизайном и планом, зависящий от API-контракта,
зафиксированного здесь.

**Цель backend-этапа:**
1. Сохранить весь текущий функционал сборщика (`legalacts-scraper`,
   см. `docs/superpowers/specs/2026-09-15-legalacts-scraper-design.md`)
   — обход портала, парсинг, резюмируемость через очередь.
2. Заменить хранилище SQLite (`sqlite3`, ручной SQL) на PostgreSQL
   через SQLAlchemy.
3. Добавить FastAPI-слой, отдающий собранные данные для будущего
   frontend-дашборда.
4. Контейнеризовать backend (Docker), с раздельными процессами
   API и периодического сбора.

**Явно вне охвата этого этапа:**
- Перенос данных из существующего `legalacts.db` — начинаем с чистой
  БД, архив пересобирается заново.
- Frontend и его Docker-образ.
- Alembic/миграции схемы — при чистом старте схема создаётся через
  `Base.metadata.create_all()`; вернёмся к вопросу миграций, когда
  появится реальная необходимость эволюционировать схему на данных
  в проде.

## 1. Структура каталогов

Корневые `scraper/`, `tests/`, `requirements.txt` переезжают в
`backend/` с адаптацией. `docs/` остаётся в корне репозитория.

```
backend/
├── app/                       # FastAPI-приложение
│   ├── main.py                 # создание приложения, роутеры, startup (create_all)
│   ├── deps.py                 # get_db (Session), require_api_key
│   ├── config.py               # pydantic-settings: DATABASE_URL, API_KEY, ...
│   ├── schemas/                 # Pydantic-модели ответов
│   │   ├── documents.py
│   │   ├── analytics.py
│   │   └── crawl.py
│   └── routers/
│       ├── documents.py        # GET /documents, GET /documents/{id}
│       ├── analytics.py        # GET /analytics/summary, /analytics/timeseries
│       └── crawl.py            # GET /crawl/status
├── scraper/                    # текущая логика обхода
│   ├── fetch.py                 # без изменений
│   ├── parsers/                  # без изменений
│   ├── queue.py                 # переписан на ORM-сессию + Postgres upsert
│   ├── store.py                 # переписан на ORM-сессию + Postgres upsert
│   └── run.py                   # process_list_entry/process_document_entry/run() — логика та же, меняется тип conn на Session
├── worker/
│   └── loop.py                  # цикл: run(db_url, limit=...) → sleep(SCRAPE_INTERVAL_SECONDS) → повтор
├── db/
│   ├── models.py                # SQLAlchemy declarative-модели: Document, Comment, CrawlQueueEntry
│   └── session.py               # engine, SessionLocal, create_all()
├── tests/                       # перенесены из корневого tests/, адаптированы под Postgres
├── Dockerfile
└── requirements.txt
```

## 2. Модель данных (SQLAlchemy ORM)

Единственный источник схемы — declarative-модели в `db/models.py`.
Состав полей полностью переносится из текущего `scraper/db.py`, без
добавления/удаления колонок:

- `Document` (таблица `documents`): те же поля, что сейчас
  (`external_id`, `section`, `url`, `title_ru`, `title_kk`, `status`,
  `doc_type`, `government_body`, `created_date`, `discussion_end_date`,
  `comments_total`, `likes_count`, `dislikes_count`, `raw_html_ru`,
  `raw_html_kk`, `first_seen_at`, `last_checked_at`).
- `Comment` (таблица `comments`): те же поля (`document_id`,
  `external_comment_id`, `parent_external_comment_id`, `author_name`,
  `body`, `article_ref`, `status`, `commented_at_raw`, `first_seen_at`),
  `UNIQUE(document_id, external_comment_id)`.
- `CrawlQueueEntry` (таблица `crawl_queue`): те же поля (`url` PK,
  `page_type`, `section`, `status`, `attempts`, `last_error`,
  `discovered_at`, `processed_at`).

Изменения типов при переходе на Postgres:
- `id` → `Integer, primary_key=True` (SERIAL/IDENTITY вместо
  `AUTOINCREMENT`).
- `first_seen_at`, `last_checked_at`, `discovered_at`, `processed_at`
  → `TIMESTAMPTZ` вместо `TEXT` (сейчас туда пишется
  `now_iso()` — строка ISO-8601; естественно ложится на нативный тип
  времени).
- Остальные поля — `String`/`Integer`/`Text` без изменения семантики.

Схема создаётся вызовом `Base.metadata.create_all(engine)` при старте
API и воркера (идемпотентно). Alembic не подключаем — см. раздел 0.

## 3. Слой хранения и оркестрации обхода

**`queue.py` / `store.py`** переписываются на приём SQLAlchemy
`Session` вместо `sqlite3.Connection`, с той же публичной сигнатурой
функций (`enqueue`, `next_pending`, `section_for`, `mark_done`,
`mark_error`, `requeue_stale_documents`, `requeue_stale_lists`,
`upsert_document`, `upsert_comments`) и тем же поведением:

- `enqueue()` → `session.execute(insert(CrawlQueueEntry).values(...).on_conflict_do_nothing(index_elements=["url"]))`
  — замена `INSERT OR IGNORE` на Postgres-диалект.
- `upsert_document()` / `upsert_comments()` → `insert(...).on_conflict_do_update(index_elements=[...], set_=...)`.
  Сохраняется текущая семантика: `first_seen_at` не переписывается при
  обновлении; kk-поля (`title_kk`, `raw_html_kk`) не затираются пустым
  значением, если при очередном обходе kk-версия не пришла.
- `next_pending()`, `section_for()` и т.д. → `session.execute(select(...))`,
  доступ к полям через атрибуты ORM-объектов вместо `row["field"]`.

**`fetch.py` и `scraper/parsers/*`** — переносятся без изменений: это
чистая логика (HTTP-клиент, разбор HTML) без зависимости от способа
хранения.

**`run.py`** — структура та же (`process_list_entry`,
`process_document_entry`, `run()`, `main()`), меняется только тип
`conn` (теперь `Session`) и источник соединения
(`db.connect()/init_db()` → `SessionLocal()` + `create_all()`).
`main()` с флагами `--db`/`--limit` сохраняется для ручного запуска
внутри контейнера (флаг `--db` в новой версии — это, по сути, разовый
override `DATABASE_URL`, а не путь к файлу).

Обработка ошибок на уровне записи очереди (одна сломанная
list/document-страница не останавливает весь обход) сохраняется без
изменений.

## 4. FastAPI

Аутентификация: заголовок `X-API-Key`, проверяется зависимостью
`app.deps.require_api_key` (значение — из `API_KEY` в конфиге).
Применяется ко всем роутерам, кроме `/health`.

Эндпоинты:

| Метод и путь | Назначение |
|---|---|
| `GET /documents?section=&status=&page=` | список карточек с фильтрами и пагинацией |
| `GET /documents/{id}` | карточка документа + связанные комментарии |
| `GET /analytics/summary` | количество документов/комментариев в разрезе `section`/`status` |
| `GET /analytics/timeseries?field=created_date\|first_seen_at&interval=day\|week` | динамика по датам |
| `GET /crawl/status` | количество записей `crawl_queue` по `status`/`page_type`, время последнего `processed_at`, последние N записей со `status='error'` (текст `last_error`) |
| `GET /health` | без авторизации, для Docker healthcheck |

Ответы сериализуются из тех же ORM-моделей через Pydantic-схемы
(`model_config = ConfigDict(from_attributes=True)`), без промежуточного
слоя ручного маппинга.

## 5. Воркер и расписание сбора

`worker/loop.py` — процесс, отдельный от API:

```python
while True:
    run(database_url, limit=WORKER_LIMIT)
    sleep(SCRAPE_INTERVAL_SECONDS)
```

Без cron/APScheduler/Celery: это избыточно для периодического вызова
уже готовой функции `run()`, которая сама резюмируема и сама
останавливается, когда очередь пуста (или после `WORKER_LIMIT`
записей за проход). Интервал и лимит — переменные окружения с
дефолтами, разумными для вежливого обхода (см. раздел 3 исходного
скрапер-спека).

## 6. Docker / docker-compose

`backend/Dockerfile` — один образ на оба процесса, команда
переопределяется в compose:
- база — `python:3.12-slim` (текущий проект зафиксирован на Python 3.8,
  это EOL-версия; для новых контейнеров поднимаем до актуального 3.12
  — нет причины тащить legacy-ограничение в свежий образ).
- `api`: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- `worker`: `python -m worker.loop`.

`docker-compose.yml` в корне репозитория:

```yaml
services:
  db:
    image: postgres:16-alpine
    volumes: [pgdata:/var/lib/postgresql/data]
    environment: [POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD]
    healthcheck: pg_isready

  api:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    environment: [DATABASE_URL, API_KEY]
    ports: ["8000:8000"]
    depends_on: db (healthy)

  worker:
    build: ./backend
    command: python -m worker.loop
    environment: [DATABASE_URL, SCRAPE_INTERVAL_SECONDS, WORKER_LIMIT]
    depends_on: db (healthy)

volumes:
  pgdata:
```

Сервис `frontend` добавится в этот же файл на втором этапе.

## 7. Тестирование

- Тесты парсеров (`test_list_page.py`, `test_document_page.py`,
  `test_comments.py`, `test_fetch.py`) переносятся без изменений —
  это чистые функции на HTML-фикстурах, не зависящие от способа
  хранения.
- Тесты `db`/`queue`/`store`/`run` гоняются на настоящем PostgreSQL
  через `testcontainers-python` (`testcontainers[postgres]`):
  pytest-фикстура на сессию поднимает эфемерный Postgres-контейнер,
  накатывает `Base.metadata.create_all()`, тесты работают с реальным
  диалектом. Это убирает риск расхождения поведения SQLite/Postgres
  (важно для `ON CONFLICT`-upsert логики) и оставляет команду запуска
  тестов такой же простой (`pytest -v`), без ручного поднятия
  compose перед прогоном.
- Предпосылка: локально должен быть доступен Docker — уже выполняется,
  так как всё приложение контейнеризуется.

## 8. Технические решения, зафиксированные в ходе брейнсторминга

- **Декомпозиция на два этапа** (backend, затем frontend) — frontend
  зависит от API-контракта, зафиксированного здесь, поэтому не может
  проектироваться параллельно без риска рассинхронизации.
- **Модель запуска сбора** — отдельный воркер-контейнер по
  расписанию, не через API-эндпоинты управления (`/crawl/start` и
  т.п. не нужны для MVP-дашборда, который только показывает прогресс).
- **Данные не переносятся** — чистый старт, полный пересбор архива.
- **Подход к ORM** — единые SQLAlchemy-модели как источник схемы для
  scraper и API (вариант с параллельным SQLAlchemy Core +
  ручными Pydantic-схемами для чтения — отклонён как дублирующий
  схему в двух местах).
- **Авторизация API** — простой статический API-ключ в заголовке,
  этого достаточно для внутреннего инструмента с внешним доступом
  через опубликованный порт.
