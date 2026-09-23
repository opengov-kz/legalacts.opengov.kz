# CLAUDE.md

Всегда общайся с пользователем на русском языке

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Реализована полная архитектура: Python-скрипт резюмируемо обходит портал `legalacts.egov.kz` (документы + обсуждения с комментариями), сохраняет результат в PostgreSQL-базу через SQLAlchemy ORM, и предоставляет асинхронный FastAPI read API с endpoint'ами для документов, аналитики и статуса обхода. Весь стек протестирован (84/84 backend tests passed) и развёртывается через Docker Compose.

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

Docker-образ (`backend/Dockerfile`) использует `python:3.12-slim`; backend теперь рассчитан на запуск внутри контейнера. Основные зависимости: `requests`, `beautifulsoup4` + `lxml`, `fastapi`, `uvicorn`, `sqlalchemy`, `alembic`, `psycopg2-binary`, `pytest`, `testcontainers`.

Схема БД версионируется через Alembic (`backend/alembic/`); `Base.metadata.create_all()` для прод/dev пути больше не используется — актуальную схему создаёт только `alembic upgrade head` (внутри Docker Compose это отдельный one-shot сервис `migrate`, который отрабатывает перед стартом `api`/`worker`; локально из `backend/`: `.venv/Scripts/alembic upgrade head`).

Если раньше уже запускался старый стек (до этой миграции схемы) и в Docker-томе `pgdata` есть таблицы, созданные старым `Base.metadata.create_all()` (без таблицы `alembic_version`) — перед первым `docker compose up --build` на этой ветке нужно один раз выполнить `docker compose down -v`, чтобы снести том. Старая схема заменяется новой целиком, данные до миграции не сохраняются (осознанное решение, см. спеку); без этого шага `alembic upgrade head` упадёт на `CREATE TABLE` с "relation already exists".

Для полного стека с БД и worker'ом (рекомендуется для локального тестирования):

```bash
# Из корня репо:
docker compose up --build
```

Это спинит пять сервисов:
- `db`: PostgreSQL 16 (слушает на `localhost:5432`)
- `migrate`: one-shot сервис, накатывает схему (`alembic upgrade head`) и завершается — `api`/`worker` стартуют только после его успешного завершения
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

Тесты с БД требуют Docker (они спинят временный контейнер `postgres:16-alpine` через testcontainers; фикстуры `tests/conftest.py` перед каждым тестом пересоздают схему `public` и прогоняют `alembic upgrade head`, так что миграции проверяются тем же прогоном, что и остальной код).

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
- `backend/db/models.py` — ORM-модели: `LegalAct` (корневая сущность, замена `Document`), нормализованные справочники `GovernmentBody`/`ActType` (get-or-create по имени; `LegalAct.government_body`/`LegalAct.doc_type` — `association_proxy` на их `.name`, поэтому внешний JSON-контракт API не меняется), `Comment` (поле `comment_channel` — какая из 8 вкладок экспертного участия, `typeComment`; уникальность `(legal_act_id, external_comment_id, comment_channel)`), `LegalActSnapshot` (история изменений + сырой HTML + SHA-256 — единственное место, где сырой HTML текущей версии вообще хранится, у `LegalAct` таких колонок нет), `DocumentVersion` (прошлые версии акта через `/application/viewcardhistory?id=<N>` — отдельное пространство id источника; insert-once, без детекции изменений, потому что версии по построению не меняются; собирается только на ru), `CrawlQueueEntry`. Внутренние временные поля (`first_seen_at`, `last_checked_at`, `captured_at`, `discovered_at`, `processed_at`) — `DateTime(timezone=True)` (UTC); поля, пришедшие с источника как текст (`created_date`, `discussion_end_date`, `commented_at_raw`), остаются строками — таймзона источника не подтверждена. Дизайн: `docs/superpowers/specs/2026-09-22-legalacts-data-model-design.md` (схема `LegalAct`), `docs/superpowers/specs/2026-09-23-document-version-history-design.md` (`DocumentVersion`).
- `backend/db/session.py` — `create_engine_and_session_factory()`: создаёт engine и session factory; схему больше не создаёт — см. Alembic выше.

**Слой скрейпера (парсеры и очередь):**
- `backend/scraper/queue.py` — управление очередью обхода (`CrawlQueue`): `enqueue`, `next_pending`, `section_for`, `mark_done`, `mark_error`, `requeue_stale_documents`, `requeue_stale_lists`. Единственный источник истины о том, что уже обработано (двигатель резюмируемости).
- `backend/scraper/store.py` — сохранение актов и комментариев в БД (upsert): `upsert_legal_act` (get-or-create для `GovernmentBody`/`ActType`; вставляет новую строку `LegalActSnapshot`, только если изменились статус/сроки/счётчики/хэш содержимого — идемпотентно для неизменного повторного обхода), `upsert_comments` (принимает `comment_channel`). Сохраняет `first_seen_at`, обновляет `last_checked_at`; kk-поля не затираются, если при очередном обходе не пришли — включая `raw_html_kk`, который в этом случае переносится из последнего снапшота.
- `backend/scraper/fetch.py` — `Fetcher`: вежливый HTTP-клиент с задержкой между запросами, джиттером и ретраями на сетевых/5xx-ошибках; `set_language()` для переключения ru/kk через `/application/changelang`.
- `backend/scraper/parsers/list_page.py`, `document_page.py`, `comments.py` — разбор HTML через BeautifulSoup+lxml по селекторам, подтверждённым на реальных страницах сайта (фикстуры в `backend/tests/fixtures/`). `document_page.py` понимает два шаблона карточки: `.view-npa` (`/npa/view`, разделы `npa`/`kdrp`) и `.blog-item` (`/npa/viewArvConclusion`, раздел `arv`) — селекторы объединены (`.view-npa h2, .blog-item h2` и т.д.), т.к. на первом шаблоне класс `blog-item` висит на пустом `<br>` и конфликта не возникает. `government_body` сначала берётся из `<span class="gov-parent">`, а если его нет (страницы `/application/viewcardhistory` — версии-снапшоты) — из метки `«Государственный орган НПА:»`. `parse_version_info()` вытаскивает номер версии и ссылку на предыдущую версию из метки `«Версия проекта:»`, используется и для текущей карточки, и рекурсивно для каждой найденной версии.
- `backend/scraper/run.py` — оркестрация скрейпера: `process_list_entry`, `process_document_entry`, `run(database_url, limit=None)` (главный цикл: list-страницы обрабатываются раньше document-страниц), `main()` (CLI); внутренние переменные переименованы `document_id` → `legal_act_id` вслед за моделью, таймстемпы теперь реальные `datetime` (`scraper.run.now()`), а не ISO-строки. `process_document_entry` для разделов `npa`/`kdrp`/`withdraw` дополнительно обходит все 7 оставшихся вкладок экспертного участия (`EXPERT_COMMENT_CHANNELS = (1, 3, 4, 7, 8, 9, 10)`, по одному GET-запросу `url&typeComment=N` на канал — `_with_type_comment()`), сохраняя каждую под своим `comment_channel`; для `arv` эти запросы пропускаются (у раздела вообще нет вкладок комментариев, см. известные ограничения). После этого (тоже кроме `arv`) `process_document_entry` идёт по цепочке предыдущих версий акта через `/application/viewcardhistory?id=<N>` (`_collect_prior_versions`) — останавливается, как только доходит до уже сохранённой версии (`store.document_version_exists`), так что повторный обход не делает лишних запросов. Сетевые/разбор-ошибки на уровне одной записи очереди не останавливают весь обход — запись помечается `error`, цикл продолжается. `run()` вызывает `fetcher.set_language("ru")` сразу после создания `Fetcher`, до цикла очереди — без cookie `egovLang` сайт по умолчанию отдаёт казахскую версию, а без этого вызова первый документ каждого цикла `worker/loop.py` парсился бы из казахского HTML под видом русского.

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
- `docker-compose.yml` в корне репо определяет пять сервисов:
  - `db`: PostgreSQL 16.
  - `migrate`: one-shot сервис, накатывает схему через `alembic upgrade head` и завершается (exit 0); ждёт `db: service_healthy`.
  - `api`: FastAPI приложение, слушает на порту 8000, требует `X-API-Key` в заголовках; стартует только после успешного завершения `migrate` (`depends_on: migrate: condition: service_completed_successfully`).
  - `worker`: фоновый процесс, запускает `backend/worker/loop.py`; та же зависимость от `migrate`.
  - `frontend`: Next.js фронтенд, слушает на порту 3000, зависит от `api`.
- `backend/Dockerfile` — однослойный (single-stage) build на `python:3.12-slim`: устанавливает зависимости, копирует код, запускает приложение.
- `.env.example` — шаблон переменных окружения.

**Фронтенд (`frontend/`):**
- `frontend/app/page.tsx` — редиректит `/` на `/ru/documents`; помечен `export const dynamic = "force-dynamic"`, иначе Next.js кеширует эту полностью статическую страницу и отдаёт `307` без заголовка `Location` (редирект срабатывает только через клиентский JS, curl/поисковики/health-чеки видят пустой редирект).
- `frontend/app/layout.tsx` — единственный файл, где разрешено рендерить `<html>`/`<body>` (ограничение Next.js App Router: ровно один layout в дереве может это делать, и это должен быть настоящий корень, не видящий параметр `[locale]`). `<html lang>` там статичный (`"ru"`); для `kk`-страниц реальный атрибут `lang` синхронизирует `useEffect` в `SiteHeader.tsx` (`document.documentElement.lang = locale`) — стандартный обходной путь для App Router, где у корневого layout нет доступа к динамическим сегментам. `frontend/app/global-error.tsx` — отдельный файл с собственным `<html>`/`<body>`, ловит необработанные ошибки в самом `app/layout.tsx`.
- `frontend/app/[locale]/layout.tsx` — обёртка с шапкой сайта (`SiteHeader`) под корневым layout; здесь же валидация локали (`isLocale`/`notFound()`).
- `frontend/app/[locale]/not-found.tsx` — определяет локаль из `usePathname()` (не из `params` — Next.js не передаёт их в `not-found.tsx`), поэтому 404 показывается на языке текущего URL, а не всегда по-русски.
- `frontend/app/[locale]/error.tsx` — error boundary для дерева `[locale]` (ошибки внутри публичных страниц, в отличие от `app/global-error.tsx`, который ловит ошибки самого корневого layout'а); локаль берёт из `useParams()`, показывает сообщение словаря и кнопку повтора (`reset`).
- `frontend/app/[locale]/*` — публичные страницы: `documents` (каталог с фильтром по разделу и пагинацией), `documents/[id]` (детальная страница документа + комментарии), `analytics` (графики по разделам/статусам + динамика во времени), `crawl-status` (статус очереди обхода и последние ошибки). Локаль (`ru`/`kk`) всегда в пути.
- `frontend/lib/env.ts` — единственный модуль, которому разрешено читать `FASTAPI_BASE_URL`/`API_KEY` из `process.env` (`getServerEnv()`, помечен `server-only`); бросает исключение, если переменная не задана.
- `frontend/lib/api-client.ts` — единственный модуль, которому разрешено обращаться к FastAPI напрямую (`getDocuments`, `getDocument`, `getAnalyticsSummary`, `getAnalyticsTimeseries`, `getCrawlStatus`), учётные данные берёт из `lib/env.ts`; Server Component-страницы вызывают эти функции напрямую (in-process), без self-HTTP. BFF-роуты (`app/api/*`) логируют реальную ошибку через `console.error` на сервере и отдают наружу общее сообщение — не пробрасывают внутренний текст ошибки неавторизованным клиентам.
- `frontend/app/api/*` — BFF route handlers, обёртки над теми же функциями `lib/api-client.ts`; в v1 самими страницами не используются (задел на будущий client-side fetching).
- `frontend/lib/i18n/*` — `locales.ts` (список локалей, `isLocale`, `DEFAULT_LOCALE`), `dictionaries.ts` (статические ru/kk словари UI-строк, без i18n-фреймворка).
- `frontend/components/ui/*` — базовые примитивы в духе shadcn/ui (Button, Table, Badge) поверх Tailwind + Radix.
- `frontend/components/{documents,analytics,crawl,nav}/*` — презентационные компоненты страниц (таблицы документов, фильтры, пагинация, графики Recharts с обязательной HTML-таблицей рядом, шапка сайта с переключателем языка).
- `frontend/Dockerfile` — двухстадийная (multi-stage) сборка на `node:20-slim` с `output: "standalone"` (`next.config.js`) — рантайм-стадия не ставит `node_modules` заново, копирует только `.next/standalone` + `.next/static` + `public`; запускается от непривилегированного пользователя `node`.

**Обход двухуровневый и ленивый:** список → карточки документов; каждая обработанная list-страница сама добавляет в очередь только следующую страницу своей пагинации, а не все сразу. Раздел сайта (`section`: `npa`/`kdrp`/`arv`/`withdraw`) хранится в `crawl_queue` в момент постановки в очередь, а не выводится из URL документа — раздел виден только на списочной странице, откуда документ был обнаружен. Карточки разделов `npa`/`kdrp` живут на `/npa/view?id=...` (шаблон `.view-npa`), карточки `arv` — на `/npa/viewArvConclusion?id=...` (другой шаблон, `.blog-item`, без вкладок комментариев); оба шаблона разбирает один и тот же `document_page.py`.

**Известные ограничения (см. спек):**

- `comments_total` документа считает комментарии по всем вкладкам экспертизы портала. Живой проверкой (2026-09-21) подтверждено до 8 таких вкладок (Комментарий/`typeComment=6`, «Атамекен» ҰҚП/`3`, Қоғамдық және сараптамалық кеңестер/`1`, антикоррупционная/научно-правовая/научно-экономическая экспертиза/`8`,`9`,`10`, ЗҚАИ и члены ВАК/`7`, аккредитованные НКО/`4`) — переключаются обычной навигацией `/npa/view?id=<id>&typeComment=<N>`, без отдельного AJAX-эндпоинта; все 8 теперь собираются (`run.py`, см. выше), каждая вкладка — свой `comment_channel`. Тем не менее `comments_total` может не совпадать с суммой сохранённых комментариев по всем каналам — это агрегат источника, который считается независимо (см. раздел 22.3 продуктового ТЗ про контроль качества), а не производная величина.
- `robots.txt` запрещает `/npa/view`, `/application` и `/report` — это сознательно игнорируется для этих путей (см. addendum в спеке от 2026-09-21 и решение от 2026-09-23); для остальных используемых путей (`/list`, `/Arvlist`) `robots.txt` соблюдается. Полный список `Disallow` на самом деле шире (`/legalact/`, `/filtercomments/`, `/public`, `/subscriptioncontroller/` и служебные пути) — текущий код их не касается, но расширение на эти пути в будущем потребует того же осознанного решения.
- `USER_AGENT` в `backend/scraper/run.py` должен оставаться ASCII-совместимым (ISO-8859-1) — HTTP-заголовки не допускают произвольной кириллицы (RFC 7230 §3.2); это уже проверяется тестом `test_user_agent_is_latin1_encodable`.
- У документов `arv` (`/npa/viewArvConclusion`) нет вкладок комментариев/лейбла статуса — `status`, `discussion_end_date` и список комментариев для них всегда `NULL`/пустые, это не баг парсера, а особенность шаблона (см. фикстуру `document_arv_conclusion.html` и тесты `test_parse_document_page_reads_arv_conclusion_template`/`test_parse_comments_returns_empty_list_for_arv_conclusion_template`).
- `DocumentVersion` (версии-снапшоты через `/application/viewcardhistory`) собираются только на ru, без вложенных приложенных файлов и без экспонирования через API v1 (пока только для сбора/архива). Запись — insert-once: если сбор цепочки версий прервётся сетевой ошибкой посередине (вся запись очереди documents уйдёт в `error`), уже собранные версии останутся в БД, но `error`-записи очереди сейчас не переоткрываются автоматически (`requeue_stale_documents`/`requeue_stale_lists` смотрят только на `status == "done"`) — это существовавшее до `DocumentVersion` ограничение очереди, не специфичное для версий, но версии-цепочки увеличивают число сетевых запросов на документ и потому чуть повышают вероятность с ним столкнуться.

Два бага, найденных живой проверкой источника 2026-09-21 (были описаны здесь и в addendum `docs/superpowers/specs/2026-09-15-legalacts-scraper-design.md`) — **исправлены**: несовпадение шаблона `arv` с `.view-npa`-селекторами (см. выше про `document_page.py`) и гонка языка на первом документе каждого цикла (см. выше про `run()`). Регрессионные тесты: `test_parse_document_page_reads_arv_conclusion_template`, `test_run_switches_to_russian_before_first_document_fetch`.
