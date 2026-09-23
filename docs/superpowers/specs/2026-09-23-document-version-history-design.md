# Архитектурный дизайн: сбор истории версий документа (Этап 2, `DocumentVersion`)

Дата: 2026-09-23

## Контекст

Продуктовое ТЗ (`docs/superpowers/specs/2026-09-20-analytics-product-requirements.md`,
раздел 27, Этап 2) относит расширение сборщика на `Document[]`
(версии/файлы акта) к следующему после архитектурной модели данных
шагу. Механика связи версий на источнике исследована
2026-09-23 (`docs/superpowers/specs/2026-09-15-legalacts-scraper-design.md`,
addendum «Уточнения по итогам исследования покрытия и связи версий»):
прошлые версии акта живут на `/application/viewcardhistory?id=<N>`
(отдельное пространство id источника), тот же шаблон `.view-npa`, без
вкладок комментариев.

В ходе проектирования этого документа обнаружена и здесь же исправлена
неточность того addendum: он утверждал, что `document_page.py`
разберёт `viewcardhistory` без изменений вообще — верно для
`title`/`status`/`doc_type`/`created_date`/`discussion_end_date`
(метки совпадают), но не для `government_body`: на обычной карточке
он берётся из `<span class="gov-parent">` внутри `.blog-info`, а на
`viewcardhistory` `.blog-info` отсутствует целиком — орган там дан
отдельной меткой `«Государственный орган НПА:»`. Без фолбэка
`government_body` версий-снапшотов молча уходил бы в `NULL`. Точный
текст ссылки на предыдущую версию подтверждён живьём в русской
языковой сессии: `<b>Версия проекта:</b> Версия 2 ( <a
href="/application/viewcardhistory?id=52440">Версия 1</a> )`.

Этот документ — дизайн новой сущности `DocumentVersion`, реализующей
`Document[]` из целевой ER-диаграммы (раздел 21 продуктового ТЗ),
поверх уже смержённой модели `LegalAct` (`docs/superpowers/specs/2026-09-22-legalacts-data-model-design.md`).

## Область действия и решения по объёму

- Имя таблицы — **`DocumentVersion`**, не `Document`: старое имя
  `Document` уже использовалось для удалённой плоской схемы (заменённой
  на `LegalAct`), повторное использование запутывало бы git-историю и
  документацию.
- Метаданные приложенных файлов версии (`/application/downloadattfilehistory?id=...`)
  — **отложены**, тем же принципом, что и `conceptFiles` текущей
  версии (уже отмечено в CLAUDE.md как target/v2).
- Собираем только **ru**-вариант каждой версии — как и с комментариями,
  второстепенный исторический контент, двойной запрос ради kk не
  оправдан.
- При повторном обходе того же акта версии, уже сохранённые в БД
  (`external_id` уже есть), **повторно не запрашиваются** — они
  исторические и не меняются; проверка перед каждым запросом
  `viewcardhistory` останавливает цепочку, как только дошли до уже
  известной версии.
- Раздел `arv` **пропускается целиком** — у шаблона `.blog-item` нет
  поля «Версия проекта» вообще (нет смысла его искать).
- Никакого снапшот-механизма (`content_sha256`/history-таблицы) для
  `DocumentVersion` не нужно — insert-once по построению.

## Схема таблицы

### `document_versions` (новая)

```text
id                    PK (внутренний)
legal_act_id          FK -> legal_acts, not null
external_id           Integer, unique, not null   -- id из /application/viewcardhistory?id=<N>,
                                                     отдельное пространство id источника,
                                                     не выводимо из id самой карточки
version_number        Integer, nullable            -- из «Версия N»
title_ru              String, nullable
status                String, nullable             -- на источнике почти всегда пусто у версий-
                                                     снапшотов — не баг, особенность шаблона
act_type_id           FK -> act_types, nullable     -- тот же справочник, что у LegalAct
government_body_id    FK -> government_bodies, nullable  -- тот же справочник
created_date          String, nullable             -- сырой текст источника
discussion_end_date   String, nullable             -- сырой текст источника; ФОРМАТ ОТЛИЧАЕТСЯ
                                                     от live-версии ("2026-10-05 00:00:00.0"
                                                     вместо "22/09/2026") — хранится как есть,
                                                     парсинга дат в проекте нигде нет
raw_html_ru           Text, nullable                -- единственное место хранения этой версии
first_seen_at         DateTime(timezone=True), not null   -- наши часы, UTC

unique(legal_act_id, version_number)
index (legal_act_id)
```

Сознательно нет: `content_sha256_ru`/детекции изменений (insert-once,
не перезапрашиваем), `title_kk`/`raw_html_kk` (только ru, решено выше),
`comments_total`/`likes_count`/`dislikes_count` (на `viewcardhistory`
`.blog-info` отсутствует целиком — на источнике их физически нет для
архивной версии, это не нулевые значения, а отсутствующие).

## Изменения в парсере (`backend/scraper/parsers/document_page.py`)

1. **Фолбэк для `government_body`**: если `.blog-info .gov-parent`
   не найден — брать по метке `«Государственный орган НПА:»` тем же
   механизмом `_label_text`, что уже используют `status`/`doc_type`/
   даты. Безопасно для существующих шаблонов (`.view-npa`, `.blog-item`
   раздела `arv`) — фолбэк срабатывает только когда `.gov-parent`
   отсутствует, то есть только на `viewcardhistory`.
2. **Новая функция `parse_version_info(html)`** →
   `{"version_number": int | None, "previous_version_url": str | None}`.
   Ищет `<small>`, содержащий `<b>Версия проекта:</b>`, извлекает номер
   регэкспом `Версия\s+(\d+)` из оставшегося текста и `href` вложенной
   `<a>` (если есть — не последняя версия в цепочке). Используется и
   для текущей карточки `LegalAct`, и рекурсивно для каждой найденной
   версии — один и тот же шаблон.

## Механика обхода (`backend/scraper/run.py`)

В `process_document_entry`, после сохранения канала 6 и (если не
`arv`) остальных 7 каналов:

```text
если section != "arv":
    version_info = parse_version_info(ru_html)   # текущей карточки
    next_url = version_info["previous_version_url"]
    пока next_url не None:
        external_id = id из query next_url
        если document_version_exists(external_id) → выход из цикла
            (цепочка дальше уже собрана в прошлый обход)
        response = fetcher.get(urljoin(BASE_URL, next_url))
        fields = parse_document_page(response.text)
        version_info = parse_version_info(response.text)
        upsert_document_version(legal_act_id, external_id, fields,
                                 version_info["version_number"], timestamp)
        next_url = version_info["previous_version_url"]
```

Без try/except вокруg цикла — сетевой сбой на любом шаге всплывает в
`run()` и помечает всю запись очереди `error`, тем же принципом, что
уже действует для остального тела `process_document_entry`.

## Изменения в `store.py`

- `document_version_exists(session, external_id) -> bool`.
- `upsert_document_version(session, legal_act_id, external_id, fields, version_number, now)`
  — `_get_or_create` для `GovernmentBody`/`ActType` (переиспользует
  уже существующий хелпер), вставляет строку `DocumentVersion`. Только
  insert — обновлений не бывает по построению (см. «Область действия»).

## Миграция

Одна новая Alembic-ревизия поверх `0001_baseline_schema.py`: создаёт
`document_versions` с колонками из «Схема таблицы» выше, FK на
`legal_acts`/`act_types`/`government_bodies`, `unique(legal_act_id, version_number)`
и `unique(external_id)`.

## Тестирование

- `test_document_page.py`: тест на фолбэк `government_body` при
  отсутствии `.gov-parent`; тест на `parse_version_info` — с версией
  без ссылки (последняя в цепочке) и с версией со ссылкой.
- `test_store.py`: `document_version_exists` до/после вставки;
  `upsert_document_version` переиспользует существующие
  `GovernmentBody`/`ActType` по имени (как `upsert_legal_act`).
- `test_run.py`: обход собирает всю цепочку версий за один проход
  документа (2-3 версии в фикстуре); повторный обход не перезапрашивает
  уже известные версии (мок фиксирует отсутствие лишних `fetcher.get`);
  `arv`-документ не порождает ни одного запроса `viewcardhistory`.

## Критерии приёмки

1. `db/models.py` содержит `DocumentVersion` с полями и констрейнтами
   выше; новая Alembic-ревизия применяется чисто на пустой БД.
2. Для документа с версией > 1 обход сохраняет все версии в цепочке
   (не только непосредственно предыдущую) без дублирования.
3. Повторный обход того же акта не делает ни одного лишнего запроса
   `viewcardhistory` для уже сохранённых версий.
4. `government_body`/`act_type`/`created_date`/`discussion_end_date`
   версии-снапшота заполнены (не `NULL` там, где на источнике есть
   значение) — включая `government_body` через новый фолбэк.
5. `arv`-документы не порождают запросов к `viewcardhistory` и не
   падают на отсутствии поля «Версия проекта».
6. Полный backend pytest-suite проходит.
