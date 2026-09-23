# Архитектурный дизайн: автоматические проверки качества, группа B (агрегатные)

Дата: 2026-09-23

## Контекст

Раздел 22.3 продуктового ТЗ («Автоматические проверки») содержал 9
пунктов. К этому моменту закрыты: уникальность `source_id` (структурно),
журнал ошибок/повторная очередь (`requeue_stale_errors`), четыре проверки
уровня записи (`invalid_url`, `invalid_date`, `end_before_start`,
`counter_null_flip` — см. `docs/superpowers/specs/2026-09-23-quality-checks-record-level-design.md`),
сравнение `comments_total` источника с фактически собранным числом
комментариев (`store.record_comments_total_mismatch`). `response time` вне
v1. Остаются последние два пункта — настоящие агрегатные проверки,
которые сравнивают текущее наблюдение с прошлым известным состоянием, а
не работают на уровне одной записи:

- «контроль резкого падения числа объектов»;
- «обнаружение новых статусов, типов, категорий и HTML-структур».

Живьём подтверждено (2026-09-23), что `doc_type`/`government_body`/
`category` уже нормализованы в lookup-таблицы с get-or-create — появление
нового значения там уже физически создаёт новую строку, просто не
фиксируется как событие качества. У `status` такой таблицы нет — это
свободная строка без реестра. «HTML-структура» — не поле данных, а
факт того, что ни один из двух известных шаблонов карточки (`.view-npa`,
`.blog-item`) не совпал при разборе.

Собственная база сборщика только растёт (в кодовой базе нет ни одного
`DELETE`) — поэтому «резкое падение числа объектов» не может относиться
к количеству строк в `legal_acts`. Единственный источник, который
реально может «упасть» — отчёт самого источника: `totalPages`,
парсящийся `list_page.parse_total_pages()` на каждой списочной странице.

## Решения по объёму (подтверждены владельцем продукта 2026-09-23)

- Падение `totalPages` фиксируется **без порога** — любое уменьшение
  относительно последнего известного значения для того же списочного
  URL. Решение о значимости (шум против реальной проблемы) — за
  дальнейшим анализом истории, не за этой итерацией. Тот же принцип,
  что уже применён во всех предыдущих проверках качества.
- «Новые статусы и HTML-структуры» реализуются **оба сразу**, в этой же
  итерации.

## Ключевое следствие для схемы: `QualityEvent.legal_act_id` становится nullable

Событие `list_total_pages_decreased` не привязано ни к какому конкретному
акту — это свойство списочной страницы. Существующая колонка
`quality_events.legal_act_id` сейчас `NOT NULL` (см. миграцию `0006`).
Ослабление констрейнта безопасно: существующие строки уже все имеют
непустое значение, `NOT NULL` → nullable не требует backfill и не ломает
ни один существующий запрос (ни один запрос в кодовой базе не полагается
на `NOT NULL` этой колонки — подтверждено: `quality_events` нигде не
джойнится и не фильтруется, кроме тестов). Все остальные типы событий
(включая два новых из этой итерации — `new_status` и
`unrecognized_html_structure`) по-прежнему всегда заполняют
`legal_act_id`.

## Схема

### Изменение `quality_events`

```text
legal_act_id      FK -> legal_acts, NULLABLE (было NOT NULL)
```

### `known_status_values` (новая)

```text
id                PK (внутренний)
value             String, unique, not null
first_seen_at     DateTime(timezone=True), not null
```

Реестр status-значений, когда-либо встреченных. Прямого аналога у
`doc_type`/`government_body`/`category` нет — те уже сами являются
такими реестрами (лишь без события качества при создании новой строки),
`status` — обычная строка на `LegalAct`, отдельной таблицы для неё
никогда не создавалось.

### `list_page_totals` (новая)

```text
id                PK (внутренний)
url               String, unique, not null   -- канонический вид: page=1
total_pages       Integer, not null           -- последнее известное значение
updated_at        DateTime(timezone=True), not null
```

Один ряд на «списочную серию» (section × базовый URL × categoryId, если
применимо) — итого потенциально до ~156 строк (6 `SEED_LIST_URLS` + 150
category-фильтров), растёт не безгранично, в отличие от `quality_events`.
`url` — тот же URL, что обрабатывается `process_list_entry`/
`process_category_list_entry`, приведённый к `page=1` через уже
существующий `_set_page_param(url, 1)` — так разные страницы одной и той
же пагинации совпадают в один ряд.

## Три проверки

### 1. `list_total_pages_decreased`

Новая функция `store.record_list_total_pages_change(session, url, total_pages, now)`:

```text
canonical_url = _set_page_param(url, 1)   -- переиспользует существующий helper run.py
existing = ListPageTotal по url=canonical_url
если existing и total_pages < existing.total_pages:
    QualityEvent(legal_act_id=None, event_type="list_total_pages_decreased",
                 field_name="total_pages", detail=f"{existing.total_pages} -> {total_pages}", detected_at=now)
если existing: existing.total_pages = total_pages; existing.updated_at = now
иначе: создать ListPageTotal(url=canonical_url, total_pages=total_pages, updated_at=now)
```

Вызывается из `run.py` в двух местах, сразу после существующего
`total_pages = list_page.parse_total_pages(html)`:
- `process_list_entry` — до текущей логики пагинации (`if current_page <
  total_pages: ...`), не влияет на неё.
- `process_category_list_entry` — аналогично.

`_set_page_param` уже находится в `run.py` (используется для пагинации) —
новых helper'ов для построения канонического URL не требуется, функция
принимает исходный `url` (с любым `page`) как есть и сама приводит его к
`page=1` перед сравнением/сохранением, так что вызывающий код передаёт
`url` без изменений.

### 2. `new_status`

Расширение уже существующей `store._record_quality_events` (группа A,
`docs/superpowers/specs/2026-09-23-quality-checks-record-level-design.md`) —
пятая проверка, тот же call site внутри `upsert_legal_act`, тот же
принцип «ничего не блокирует»:

```text
status = values["status"]
если status:
    существует ли status в known_status_values?
    если нет:
        создать KnownStatusValue(value=status, first_seen_at=now)
        events.append(("new_status", "status", status))
```

Как и остальные проверки группы A, выполняется при каждом upsert'е —
если значение уже видели (для этого или любого другого акта), новое
событие не создаётся.

### 3. `unrecognized_html_structure`

`document_page.parse_document_page(html)` получает новый ключ в
возвращаемом словаре:

```python
title_el = soup.select_one(".view-npa h2, .blog-item h2")
title = title_el.get_text(strip=True) if title_el else None
...
return {
    "title": title,
    "template_recognized": title_el is not None,
    ...
}
```

Новая функция `store.record_unrecognized_html_structure(session,
legal_act_id, template_recognized, now)`:

```text
если не template_recognized:
    QualityEvent(legal_act_id=legal_act_id, event_type="unrecognized_html_structure",
                 field_name="title", detail="ни .view-npa, ни .blog-item не совпали",
                 detected_at=now)
```

Вызывается из `run.py`'s `process_document_entry`, после
`legal_act_id = store.upsert_legal_act(...)` (нужен `legal_act_id` для
FK), используя `fields.get("template_recognized")` — ключ, добавленный
парсером на ru-разборе (`fields` до `fields.pop("title")`). Проверяется
только на ru-разборе (основной источник данных акта), не на kk.

Раздел `arv` не требует специальной обработки: его шаблон `.blog-item`
уже входит в комбинированный селектор, так что `template_recognized`
будет `True` для корректных arv-карточек без дополнительных условий.

## Изменения по файлам

- `backend/db/models.py`: `QualityEvent.legal_act_id` → `nullable=True`;
  новые классы `KnownStatusValue`, `ListPageTotal`.
- `backend/alembic/versions/0007_quality_checks_aggregate.py`: одна
  ревизия — `alter_column` на nullable, `create_table` × 2.
- `backend/scraper/parsers/document_page.py`: `parse_document_page`
  возвращает `template_recognized`.
- `backend/scraper/store.py`: `record_list_total_pages_change`,
  `record_unrecognized_html_structure`, расширение
  `_record_quality_events` третьей проверкой (`new_status`).
- `backend/scraper/run.py`: вызовы новых функций в `process_list_entry`,
  `process_category_list_entry`, `process_document_entry`.

## Тестирование

- `test_db.py`: `quality_events.legal_act_id` допускает `NULL`; новые
  таблицы `known_status_values`/`list_page_totals` с ожидаемыми
  колонками.
- `test_document_page.py`: `parse_document_page` возвращает
  `template_recognized=True` для `.view-npa` и `.blog-item` фикстур,
  `False` для HTML без обоих селекторов.
- `test_store.py`: `record_list_total_pages_change` — первый вызов не
  создаёт событие (нет `existing`), но создаёт `ListPageTotal`; уменьшение
  создаёт событие с `legal_act_id=None`; увеличение/равенство не создаёт
  события, но обновляет `total_pages`. `record_unrecognized_html_structure` —
  `True` не создаёт событие, `False` создаёт. Расширение
  `upsert_legal_act`-тестов: новый статус создаёт `new_status` + строку в
  `known_status_values`; повторный тот же статус (в т.ч. на другом акте)
  не создаёт события повторно.
- `test_run.py`: `process_list_entry`/`process_category_list_entry`
  вызывают проверку totalPages на реальной фикстуре (без изменения
  существующего поведения пагинации); `process_document_entry` пишет
  `unrecognized_html_structure`, когда используется HTML без известных
  селекторов.

## Критерии приёмки

1. `db/models.py`/миграция `0007` применяются чисто поверх `0006`;
   `quality_events.legal_act_id` — nullable, обе новые таблицы созданы.
2. Уменьшение `totalPages` для одного и того же списочного URL создаёт
   `list_total_pages_decreased` с `legal_act_id=None`; увеличение/
   равенство — нет.
3. Новое значение `status` (глобально, впервые для всего датасета)
   создаёт `new_status`; повторное — нет.
4. HTML без `.view-npa`/`.blog-item` создаёт `unrecognized_html_structure`;
   корректные `npa`/`kdrp`/`arv`/`withdraw` карточки — нет.
5. Ничего не блокирует существующий обход — все три проверки только
   добавляют события, не меняют сохранение актов/списков.
6. Полный backend pytest-suite проходит.
