# CLAUDE.md

Всегда общайся с пользователем на русском языке

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Реализована полная архитектура: Python-скрипт резюмируемо обходит портал `legalacts.egov.kz` (документы + обсуждения с комментариями), сохраняет результат в PostgreSQL-базу через SQLAlchemy ORM, и предоставляет асинхронный FastAPI read API с endpoint'ами для документов, аналитики и статуса обхода. Весь стек протестирован (58/58 backend tests passed) и развёртывается через Docker Compose.

Исходная спецификация скрейпера: `docs/superpowers/specs/2026-09-15-legalacts-scraper-design.md`.
Спецификация backend-архитектуры (Postgres + SQLAlchemy + FastAPI): `docs/superpowers/specs/2026-09-18-backend-postgres-fastapi-design.md`.
Пошаговый план реализации (выполнен, Task 1–13): `docs/superpowers/plans/2026-09-18-backend-postgres-fastapi.md`.

## Setup

Вся логика (скрейпер, хранилище, API) находится в подпапке `backend/`. Для локальной разработки:

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Linux/macOS: .venv/bin/pip install -r requirements.txt
```

Docker-образ (`backend/Dockerfile`) использует `python:3.12-slim`; backend теперь рассчитан на запуск внутри контейнера. Основные зависимости: `requests`, `beautifulsoup4` + `lxml`, `fastapi`, `uvicorn`, `sqlalchemy`, `psycopg2-binary`, `pytest`, `testcontainers`.

Для полного стека с БД и worker'ом (рекомендуется для локального тестирования):

```bash
# Из корня репо:
docker compose up --build
```

Это спинит четыре сервиса:
- `db`: PostgreSQL 16 (слушает на `localhost:5432`)
- `api`: FastAPI приложение (на `localhost:8000`, требует `X-API-Key` в заголовках)
- `worker`: фоновый worker, запускающий скрейпер по расписанию
- `frontend`: Next.js фронтенд (на `localhost:3000`)

Env-переменные в `.env.example`. Перед `docker compose up` файл `.env` ОБЯЗАТЕЛЕН (скопировать из `.env.example` и заполнить) — у `${VAR}`-подстановок в `docker-compose.yml` нет значений по умолчанию, и без `.env` `POSTGRES_DB`/`POSTGRES_USER`/и т.д. резолвятся в пустые строки, из-за чего `db` не стартует.

Фронтенд (`frontend/`) — Next.js 14 (App Router) + TypeScript. Для локальной разработки:

```bash
cd frontend
npm install
FASTAPI_BASE_URL=http://localhost:8000 API_KEY=<значение из .env> npm run dev
```

Слушает на `http://localhost:3000`; `/` редиректит на `/ru/documents`. Тесты: `cd frontend && npm test`. Типы: `npm run typecheck`.

## Commands

Ниже — backend-команды, запускаются из папки `backend/`. Фронтенд-команды (`npm test`, `npm run typecheck`, `npm run dev`) — см. `## Setup` выше, запускаются из `frontend/`.

**Тесты (все):**

```bash
cd backend
.venv/Scripts/pytest -v
```

**Один тест / один файл:**

```bash
.venv/Scripts/pytest tests/test_run.py -v
.venv/Scripts/pytest tests/test_run.py::test_process_list_entry_enqueues_documents_and_next_page -v
```

Тесты с БД требуют Docker (они спинят временный контейнер `postgres:16-alpine` через testcontainers).

**Запуск скрейпера вручную:**

```bash
.venv/Scripts/python -m scraper.run --database-url "postgresql://user:password@localhost:5432/legalacts" --limit 20
```

Флаг `--limit` ограничивает число обработанных записей очереди за один запуск (list-страница или карточка документа = 1 запись); без флага обход идёт до полного исчерпания очереди. Повторные запуски резюмируемы — очередь не пересоздаётся, если в ней уже есть необработанные записи, а `requeue_stale_documents`/`requeue_stale_lists` переоткрывают записи (`status='done'`) старше 7 дней для докачки.

**Запуск FastAPI (локально):**

```bash
.venv/Scripts/uvicorn app.main:app --reload
```

Приложение слушает на `http://localhost:8000`; документы и аналитика доступны по endpoint'ам с префиксом `/documents`, `/analytics`, `/crawl/status`, `/health`.

**Весь стек через Docker Compose:**

```bash
cd ..
docker compose up --build
```

Теперь также запускает `frontend` (порт 3000) — см. `## Setup` выше.

Линтера в проекте нет.

## Architecture

Код находится в `backend/` и разделён по слоям:

**Слой хранилища (PostgreSQL via SQLAlchemy):**
- `backend/db/models.py` — ORM-модели (`Document`, `Comment`, `CrawlQueueEntry`) для таблиц в Postgres.
- `backend/db/session.py` — `create_engine_and_session_factory()`: создаёт engine и session factory, вызывает `Base.metadata.create_all()`.

**Слой скрейпера (парсеры и очередь):**
- `backend/scraper/queue.py` — управление очередью обхода (`CrawlQueue`): `enqueue`, `next_pending`, `section_for`, `mark_done`, `mark_error`, `requeue_stale_documents`, `requeue_stale_lists`. Единственный источник истины о том, что уже обработано (двигатель резюмируемости).
- `backend/scraper/store.py` — сохранение документов и комментариев в БД (upsert): `upsert_document`, `upsert_comments`. Сохраняет `first_seen_at`, обновляет `last_checked_at`; kk-поля не затираются, если при очередном обходе не пришли.
- `backend/scraper/fetch.py` — `Fetcher`: вежливый HTTP-клиент с задержкой между запросами, джиттером и ретраями на сетевых/5xx-ошибках; `set_language()` для переключения ru/kk через `/application/changelang`.
- `backend/scraper/parsers/list_page.py`, `document_page.py`, `comments.py` — разбор HTML через BeautifulSoup+lxml по селекторам, подтверждённым на реальных страницах сайта (фикстуры в `backend/tests/fixtures/`).
- `backend/scraper/run.py` — оркестрация скрейпера: `process_list_entry`, `process_document_entry`, `run(database_url, limit=None)` (главный цикл: list-страницы обрабатываются раньше document-страниц), `main()` (CLI). Сетевые/разбор-ошибки на уровне одной записи очереди не останавливают весь обход — запись помечается `error`, цикл продолжается.

**Worker (фоновый процесс):**
- `backend/worker/loop.py` — запускает скрейпер на расписание (`SCRAPE_INTERVAL_SECONDS`) в infinite loop'е.

**FastAPI приложение (read API):**
- `backend/app/main.py` — `create_app()`: инициализация приложения, регистрация роутов, `GET /health`.
- `backend/app/config.py` — `Settings` (pydantic-settings) из env-переменных: только `database_url`, `api_key`. `SCRAPE_INTERVAL_SECONDS`/`WORKER_LIMIT` в `Settings` не входят — их читает напрямую через `os.environ` `backend/worker/loop.py`.
- `backend/app/deps.py` — зависимости (dependency injection): `get_db()`, `require_api_key()`.
- API-key авторизация реализована не как middleware, а как FastAPI dependency на уровне роутера (`dependencies=[Depends(require_api_key)]` в каждом `APIRouter`).
- `backend/app/routers/documents.py` — endpoint'ы `GET /documents` (фильтры `section`, `status`, пагинация `page`; без полнотекстового поиска), `GET /documents/{id}`.
- `backend/app/routers/analytics.py` — endpoint'ы `GET /analytics/summary`, `GET /analytics/timeseries?interval=day|week` (без `{section}` в пути) с агрегацией по датам.
- `backend/app/routers/crawl.py` — endpoint `GET /crawl/status` для статуса текущего обхода.
- `backend/app/schemas/` — Pydantic-схемы для валидации request/response.

**Docker-композиция:**
- `docker-compose.yml` в корне репо определяет три сервиса:
  - `db`: PostgreSQL 16, инициализация schema через `backend/db/models.py` (SQLAlchemy создаёт таблицы на старт).
  - `api`: FastAPI приложение, слушает на порту 8000, требует `X-API-Key` в заголовках.
  - `worker`: фоновый процесс, запускает `backend/worker/loop.py`.
- `backend/Dockerfile` — однослойный (single-stage) build на `python:3.12-slim`: устанавливает зависимости, копирует код, запускает приложение.
- `.env.example` — шаблон переменных окружения.

**Фронтенд (`frontend/`):**
- `frontend/app/page.tsx` — редиректит `/` на `/ru/documents`; помечен `export const dynamic = "force-dynamic"`, иначе Next.js кеширует эту полностью статическую страницу и отдаёт `307` без заголовка `Location` (редирект срабатывает только через клиентский JS, curl/поисковики/health-чеки видят пустой редирект).
- `frontend/app/layout.tsx` — единственный файл, где разрешено рендерить `<html>`/`<body>` (ограничение Next.js App Router: ровно один layout в дереве может это делать, и это должен быть настоящий корень, не видящий параметр `[locale]`). `<html lang>` там статичный (`"ru"`); для `kk`-страниц реальный атрибут `lang` синхронизирует `useEffect` в `SiteHeader.tsx` (`document.documentElement.lang = locale`) — стандартный обходной путь для App Router, где у корневого layout нет доступа к динамическим сегментам. `frontend/app/global-error.tsx` — отдельный файл с собственным `<html>`/`<body>`, ловит необработанные ошибки в самом `app/layout.tsx`.
- `frontend/app/[locale]/layout.tsx` — обёртка с шапкой сайта (`SiteHeader`) под корневым layout; здесь же валидация локали (`isLocale`/`notFound()`).
- `frontend/app/[locale]/not-found.tsx` — определяет локаль из `usePathname()` (не из `params` — Next.js не передаёт их в `not-found.tsx`), поэтому 404 показывается на языке текущего URL, а не всегда по-русски.
- `frontend/app/[locale]/*` — публичные страницы: `documents` (каталог с фильтром по разделу и пагинацией), `documents/[id]` (детальная страница документа + комментарии), `analytics` (графики по разделам/статусам + динамика во времени), `crawl-status` (статус очереди обхода и последние ошибки). Локаль (`ru`/`kk`) всегда в пути.
- `frontend/lib/api-client.ts` — единственный модуль, которому разрешено читать `FASTAPI_BASE_URL`/`API_KEY` и обращаться к FastAPI напрямую (`getDocuments`, `getDocument`, `getAnalyticsSummary`, `getAnalyticsTimeseries`, `getCrawlStatus`); Server Component-страницы вызывают эти функции напрямую (in-process), без self-HTTP. BFF-роуты (`app/api/*`) логируют реальную ошибку через `console.error` на сервере и отдают наружу общее сообщение — не пробрасывают внутренний текст ошибки неавторизованным клиентам.
- `frontend/app/api/*` — BFF route handlers, обёртки над теми же функциями `lib/api-client.ts`; в v1 самими страницами не используются (задел на будущий client-side fetching).
- `frontend/lib/i18n/*` — `locales.ts` (список локалей, `isLocale`, `DEFAULT_LOCALE`), `dictionaries.ts` (статические ru/kk словари UI-строк, без i18n-фреймворка).
- `frontend/components/ui/*` — базовые примитивы в духе shadcn/ui (Button, Table, Badge) поверх Tailwind + Radix.
- `frontend/components/{documents,analytics,crawl,nav}/*` — презентационные компоненты страниц (таблицы документов, фильтры, пагинация, графики Recharts с обязательной HTML-таблицей рядом, шапка сайта с переключателем языка).
- `frontend/Dockerfile` — двухстадийная (multi-stage) сборка на `node:20-slim` с `output: "standalone"` (`next.config.js`) — рантайм-стадия не ставит `node_modules` заново, копирует только `.next/standalone` + `.next/static` + `public`; запускается от непривилегированного пользователя `node`.

**Обход двухуровневый и ленивый:** список → карточки документов; каждая обработанная list-страница сама добавляет в очередь только следующую страницу своей пагинации, а не все сразу. Раздел сайта (`section`: `npa`/`kdrp`/`arv`/`withdraw`) хранится в `crawl_queue` в момент постановки в очередь, а не выводится из URL документа — карточки всех разделов доступны по одному и тому же маршруту `/npa/view?id=...`, и раздел виден только на списочной странице, откуда документ был обнаружен.

**Известные ограничения (см. спек):**

- `comments_total` документа считает комментарии по всем вкладкам экспертизы портала; `parse_comments` разбирает только вкладку "Комментарий" — сохранённых комментариев может быть меньше `comments_total`.
- `robots.txt` запрещает `/npa/view` и `/application` — это сознательно игнорируется для этих путей (см. addendum в спеке); для остальных используемых путей (`/list`, `/Arvlist`) `robots.txt` соблюдается.
- `USER_AGENT` в `backend/scraper/run.py` должен оставаться ASCII-совместимым (ISO-8859-1) — HTTP-заголовки не допускают произвольной кириллицы (RFC 7230 §3.2); это уже проверяется тестом `test_user_agent_is_latin1_encodable`.
