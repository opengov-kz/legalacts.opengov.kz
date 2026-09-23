# Архитектурный дизайн: расширенная модель данных (Этап 1, архитектурная часть)

Дата: 2026-09-22

## Контекст

Продуктовое ТЗ (`docs/superpowers/specs/2026-09-20-analytics-product-requirements.md`,
раздел 21) описывает целевую модель данных для legalacts.opengov.kz:
`LegalAct` как корневая сущность с `GovernmentBody`, `ActType`,
`Category[]`, `Discussion[]`, `Document[]`, `Report[]`, `Comment[]`
(с `CommentVoteSnapshot[]`, `Reply[]`), `ExpertParticipation[]` и
`LegalActSnapshot[]`. Раздел 27 относит реализацию этой модели к
Этапу 1 («расширенная проверка источника и модель данных»).

Расследовательская часть Этапа 1 уже выполнена и зафиксирована в
`docs/superpowers/specs/2026-09-15-legalacts-scraper-design.md`
(раздел «Уточнения по итогам живой проверки источника (2026-09-21)»):
подтверждены 8 вкладок экспертного участия (`typeComment=1/3/4/6/7/8/9/10`,
общий контейнер `.main-comments`), исправлены два бага (шаблон `arv`,
гонка языка), подтверждены, но не собираются в v1, поля «версия
проекта» и время начала/окончания обсуждения.

Этот документ — архитектурная часть Этапа 1: дизайн модели данных,
которая заменит текущую плоскую схему (`Document`, `Comment`,
`CrawlQueueEntry` в `backend/db/models.py`).

Карта полей и покрытие по годам, а также точная механика связи версий
документа были вынесены за рамки этого документа как отдельная
исследовательская задача (по решению в ходе брейнсторминга) и
выполнены отдельно 2026-09-23 — см. «Дальнейшие шаги» в конце
документа и addendum в `docs/superpowers/specs/2026-09-15-legalacts-scraper-design.md`.

## Область действия и решения по объёму

Модель данных **полностью заменяет** текущие `Document`/`Comment`
(ломающая миграция). Продакшен ещё не запущен (критерии приёмки v1 —
раздел 26 продуктового ТЗ — ещё не подтверждены как выполненные),
поэтому уже собранные данные не считаются ценными: после миграции
предполагается полный переисполненный обход с нуля, а не перенос
старых строк.

Из целевой ER-диаграммы раздела 21 в эту версию модели **сознательно
не включены** (нет живого подтверждения источника или явно отложено
до момента, когда будет ясно, что именно собирать):

- `Document[]` (версии/файлы акта) — связь версий не исследована;
- `Report[]` — сбор отчётов требует отдельного решения по `robots.txt`
  (`/report` в `Disallow`), не принятого владельцем продукта;
- `Category` — не подтверждена живой проверкой как существующее поле
  на карточках `/npa/view` (в отличие от `government_body`);
- `CommentVoteSnapshot[]` — живая проверка не показала лайков/дизлайков
  на уровне отдельного комментария (только на уровне акта);
- `Discussion` как отдельная сущность — на источнике каждая карточка
  имеет ровно одно обсуждение; выносить его в отдельную таблицу без
  подтверждённых повторных обсуждений преждевременно. Поля обсуждения
  остаются на `LegalAct`.
- `ExpertParticipation` как отдельная от `Comment` сущность — все 8
  вкладок структурно идентичны обычным комментариям и отличаются
  только параметром `typeComment`; моделируются как один канал
  (`comment_channel`) в таблице `comments`, а не отдельная таблица.

Эти решения — не отказ от концепций, а перенос на следующий шаг
(Этап 2 продуктового ТЗ), когда для каждой станет ясно, что именно
собирать и в каком виде. Добавление таких таблиц позже — отдельная
Alembic-ревизия, не блокирующая эту работу.

## Обзор сущностей

```text
government_bodies (справочник)
act_types (справочник)

legal_acts                              (замена documents)
  ├── government_body_id  -> government_bodies
  ├── act_type_id         -> act_types
  ├── discussion_end_date              (поле, не отдельная сущность)
  ├── comments[]
  │     comment_channel (typeComment: 1/3/4/6/7/8/9/10, default=6 «Комментарий»)
  │     parent_external_comment_id (self-ссылка по внешнему id, как сейчас)
  └── legal_act_snapshots[]    (история изменений + сырой HTML, provenance)

crawl_queue   — без структурных изменений, кроме типа полей дат
```

## Схема таблиц

### `government_bodies`, `act_types`

Простые справочники, get-or-create по имени; строки никогда не
переименовываются задним числом (только вставка новых при появлении
нового значения на источнике).

```text
id    PK
name  String, unique, not null
```

`act_type_id` заменяет текущее строковое поле `Document.doc_type`;
`government_body_id` заменяет `Document.government_body`.

### `legal_acts` (замена `documents`)

```text
id                    PK (внутренний)
external_id           Integer, unique, not null   -- id источника
section               String, not null
url                   String, not null
title_ru, title_kk    String, nullable
status                String, nullable
act_type_id           FK -> act_types, nullable
government_body_id    FK -> government_bodies, nullable
created_date          String, nullable   -- сырой текст источника, timezone не подтверждён
discussion_end_date   String, nullable   -- сырой текст источника, timezone не подтверждён
comments_total        Integer, nullable  -- агрегат ИСТОЧНИКА по всем каналам (см. известные ограничения)
likes_count           Integer, nullable
dislikes_count        Integer, nullable
content_sha256_ru     String(64), nullable
content_sha256_kk     String(64), nullable
first_seen_at         DateTime(timezone=True), not null   -- наши часы, UTC
last_checked_at       DateTime(timezone=True), not null   -- наши часы, UTC
```

`raw_html_ru`/`raw_html_kk` на `legal_acts` больше нет — сырой HTML
хранится только в `legal_act_snapshots` (единственный источник
истины). API v1 эти поля и так никогда не отдавал наружу
(раздел 24.1 продуктового ТЗ), так что для фронтенда это прозрачно.

`content_sha256_ru`/`content_sha256_kk` хранят только хэш (не сам
HTML) — нужны, чтобы дёшево обнаруживать изменение содержимого при
каждом обходе без обращения к `legal_act_snapshots`.

### `comments`

```text
id                          PK
legal_act_id                FK -> legal_acts, not null   -- было document_id
external_comment_id         Integer, not null
parent_external_comment_id  Integer, nullable             -- без изменений логики
comment_channel              Integer, not null, default=6  -- typeComment: 1/3/4/6/7/8/9/10
author_name, body, article_ref, status, commented_at_raw, first_seen_at  -- без изменений

unique(legal_act_id, external_comment_id, comment_channel)
```

### `legal_act_snapshots` (новая — снапшоты + provenance)

```text
id                                     PK
legal_act_id                           FK -> legal_acts, not null
captured_at                            DateTime(timezone=True), not null  -- наши часы, UTC
raw_html_ru, raw_html_kk               Text, nullable   -- сырой HTML, единственное место хранения
content_sha256_ru, content_sha256_kk   String(64), nullable
title_ru, title_kk                     String, nullable
status                                 String, nullable
act_type_id                            FK -> act_types, nullable
government_body_id                     FK -> government_bodies, nullable
created_date                           String, nullable
discussion_end_date                    String, nullable
comments_total, likes_count, dislikes_count   Integer, nullable

index (legal_act_id, captured_at)
```

Копия состояния `legal_acts` на момент снимка. Последний raw HTML
получается запросом `ORDER BY captured_at DESC LIMIT 1` по индексу
`(legal_act_id, captured_at)` — отдельный указатель на «текущий»
снапшот не нужен.

### `crawl_queue`

Структура не меняется, кроме типа временных полей: `discovered_at` и
`processed_at` переводятся из `String` в `DateTime(timezone=True)`.
Это те же поля, что раздел 23.5 продуктового ТЗ называет одним
техдолгом вместе с `first_seen_at`/`last_checked_at` — они генерируются
нашим кодом (не источником), поэтому timezone (UTC) нам известен, в
отличие от `created_date`/`discussion_end_date`/`commented_at_raw`,
которые остаются строками с явно неопределённым timezone источника.

## Механика снапшотов и идемпотентность

При каждом апдейте `upsert_legal_act` (замена `upsert_document`):

1. Ищем существующий `LegalAct` по `external_id`.
2. Считаем SHA-256 свежепришедшего `raw_html_ru`/`raw_html_kk`.
3. Сравниваем новые значения полей (`status`, `discussion_end_date`,
   `comments_total`, `likes_count`, `dislikes_count`,
   `content_sha256_ru`, `content_sha256_kk`) с текущими полями
   `legal_acts`. Если это первая запись ИЛИ хоть одно из этих полей
   отличается — вставляется новая строка `legal_act_snapshots`
   (`captured_at=now`, копия нового состояния + сырой HTML).
4. Живые колонки `legal_acts` всегда перезаписываются свежими
   значениями и `last_checked_at=now`, независимо от того, создан ли
   снапшот.
5. `title_kk`/`raw_html_kk`: сохраняется текущее поведение — если
   источник не прислал kk-версию при повторном обходе, старое
   значение не затирается (уже реализовано в `store.py:18-21`,
   переносится в `upsert_legal_act` как есть).

Повторный обход без изменений на источнике → хэши и триггерные поля
совпадают → новых строк в `legal_act_snapshots` не появляется. Это
даёт идемпотентность, требуемую разделом 21 продуктового ТЗ.

## Миграция

Вводится Alembic (`backend/alembic/`: `alembic.ini`, `env.py`,
читающий `Settings.database_url` и `db.models.Base.metadata`).

Одна базовая ревизия сразу создаёт новую схему (`legal_acts`,
`comments`, `legal_act_snapshots`, `government_bodies`, `act_types`,
обновлённый `crawl_queue`) — без промежуточной ревизии,
воспроизводящей старую плоскую схему: БД пока не в продакшене,
сохранять историю миграций старой модели незачем.

`create_engine_and_session_factory()` (`backend/db/session.py`)
перестаёт вызывать `Base.metadata.create_all()` — схему теперь
создаёт только `alembic upgrade head`. Тесты на testcontainers тоже
переключаются на `alembic upgrade head` вместо `create_all()`, чтобы
миграции реально проверялись тестами.

`docker-compose.yml`: перед стартом `api`/`worker` нужен шаг миграции
(отдельный `migrate`-сервис или entrypoint-скрипт с
`alembic upgrade head`).

## Влияние на существующий код

- `backend/db/models.py` — переписывается под новые сущности.
- `backend/scraper/store.py` — `upsert_document` → `upsert_legal_act`
  (get-or-create для `GovernmentBody`/`ActType`, логика снапшота выше);
  `upsert_comments` получает параметр `comment_channel` (в этой версии
  всегда `6` — сборщик пока собирает только вкладку «Комментарий»,
  поле лишь освобождает место под Этап 2 без новой миграции).
- `backend/scraper/run.py` — переименования (`document_id` →
  `legal_act_id`), поведение не меняется.
- `backend/app/routers/documents.py`, `backend/app/routers/analytics.py`,
  `backend/app/schemas/*` — становятся адаптером: JOIN на
  `government_bodies`/`act_types` для тех же имён полей во внешнем
  ответе. **Внешний контракт API v1 (раздел 24.1 продуктового ТЗ) не
  меняется** — фронтенд не требует изменений.

## Тестирование

- Фикстуры и модельные тесты под новую схему.
- Тесты get-or-create хелперов для `GovernmentBody`/`ActType`.
- Тест «неизменный повторный обход не плодит новые снапшоты»
  (идемпотентность).
- Тест «повторный обход с изменением одного из триггерных полей
  создаёт ровно один новый снапшот».
- Тест уникальности `(legal_act_id, external_comment_id,
  comment_channel)`.
- Тест сохранения kk-полей при отсутствии kk-версии на повторном
  обходе.
- Smoke-тест `alembic upgrade head` на чистой БД testcontainers.
- Тесты адаптера API: форма ответа `/documents`, `/documents/{id}`,
  `/analytics/*` не изменилась после перехода на новую схему.

## Критерии приёмки

1. `backend/db/models.py` содержит `LegalAct`, `Comment` (с
   `comment_channel`), `LegalActSnapshot`, `GovernmentBody`, `ActType`;
   `Document` в старом виде удалён.
2. Alembic настроен, единственная базовая ревизия создаёт всю новую
   схему; `create_all()` для прод/dev пути не используется.
3. Повторный обход одного и того же состояния источника не создаёт
   новых строк в `legal_act_snapshots`.
4. Изменение статуса/сроков/счётчиков/текста акта на источнике при
   следующем обходе создаёт новую строку `legal_act_snapshots` и
   обновляет живые поля `legal_acts`.
5. `GET /documents`, `GET /documents/{id}`, `GET /analytics/summary`,
   `GET /analytics/timeseries` возвращают тот же формат ответа, что и
   до миграции (проверяется тестами адаптера).
6. Полный backend pytest-suite (включая новые тесты) проходит на
   PostgreSQL/testcontainers через `alembic upgrade head`.
7. `docker compose up --build` поднимает стек с шагом миграции перед
   стартом `api`/`worker`.

## Дальнейшие шаги (вне этого документа)

- ~~Исследовательская задача: карта полей и покрытие по годам, механика
  связи версий документа~~ — выполнено 2026-09-23, см. addendum
  «Уточнения по итогам исследования покрытия и связи версий» в
  `docs/superpowers/specs/2026-09-15-legalacts-scraper-design.md`.
  Итог: покрытие ~12 лет по `npa` без изменений структуры карточки за
  этот период (отдельная карта полей по годам не нужна); версии
  связаны через `/application/viewcardhistory?id=<N>` (отдельное
  пространство id, тот же шаблон `.view-npa`, без комментариев,
  рекурсивная цепочка).
- Этап 2 продуктового ТЗ: расширение сборщика на `Document[]`
  (карточка + 0..N версионных снапшотов через
  `/application/viewcardhistory`, механика уже описана в addendum
  выше), `Report[]`, `Category`, дополнительные вкладки
  `comment_channel` (1/3/4/7/8/9/10), после того как для каждого
  будет решено, что именно собирать.
