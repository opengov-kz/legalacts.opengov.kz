# Graph Report - legalacts.opengov.kz  (2026-09-16)

## Corpus Check
- 27 files · ~77,795 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 1 file(s) not represented in the graph (top: (none) 1)

## Summary
- 136 nodes · 311 edges · 9 communities (8 shown, 1 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 2 edges (avg confidence: 0.9)
- Token cost: 84,194 input · 0 output

## Community Hubs (Navigation)
- Orchestration Run Tests
- List Page Crawling
- HTTP Fetching & Politeness
- Crawl Queue Management
- Storage & Project Docs
- Comments Parsing
- Document Page Parsing
- Database Schema Tests

## God Nodes (most connected - your core abstractions)
1. `run()` - 20 edges
2. `Fetcher` - 14 edges
3. `StubFetcher` - 14 edges
4. `enqueue()` - 12 edges
5. `process_list_entry()` - 11 edges
6. `FakeSession` - 10 edges
7. `_connect()` - 10 edges
8. `process_document_entry()` - 9 edges
9. `FakeResponse` - 9 edges
10. `init_db()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `CLAUDE.md (Root Project Guidance)` --conceptually_related_to--> `Парсер legalacts.egov.kz — план реализации`  [AMBIGUOUS]
  CLAUDE.md → docs/superpowers/plans/2026-09-15-legalacts-scraper.md
- `_connect()` --calls--> `init_db()`  [EXTRACTED]
  tests/test_db.py → scraper/db.py
- `_connect()` --calls--> `init_db()`  [EXTRACTED]
  tests/test_queue.py → scraper/db.py
- `_connect()` --calls--> `init_db()`  [EXTRACTED]
  tests/test_store.py → scraper/db.py
- `test_run_marks_404_document_entry_done_not_error()` --calls--> `enqueue()`  [EXTRACTED]
  tests/test_run.py → scraper/queue.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Модули конвейера обхода: очередь, HTTP-клиент, парсеры, хранение, оркестрация** — scraper_db, scraper_queue, scraper_fetch, scraper_parsers_list_page, scraper_parsers_document_page, scraper_parsers_comments, scraper_store, scraper_run [EXTRACTED 1.00]
- **Реальные сохранённые HTML-страницы, используемые как тестовые фикстуры** — tests_fixtures_document_no_comments, tests_fixtures_document_with_comments, tests_fixtures_document_with_comments_kk, tests_fixtures_list_page [EXTRACTED 1.00]
- **Уточнения по итогам разведки реальной разметки, определившие финальную модель данных MVP** — concept_mvp_scope_reduction, concept_comments_single_body_field, concept_reply_as_child_comment, concept_lang_switch_via_cookie, concept_kdrp_is_filtered_npa, concept_robots_txt_override [EXTRACTED 1.00]

## Communities (9 total, 1 thin omitted)

### Community 0 - "Orchestration Run Tests"
Cohesion: 0.17
Nodes (16): init_db(), _connect(), FlakyStubFetcher, Guards the incremental-crawl contract (C1): once a list page's queue row has…, StubFetcher variant where .get() raises for a chosen set of URLs, simulating a…, StubFetcher, test_process_document_entry_404_stores_nothing(), test_process_document_entry_stores_document_and_comments() (+8 more)

### Community 1 - "List Page Crawling"
Cohesion: 0.18
Nodes (16): КДРП как /list с фильтром types[] (не отдельный раздел), Ленивый обход пагинации списочных страниц, parse_list_page(), parse_total_pages(), _current_page(), main(), now_iso(), process_document_entry() (+8 more)

### Community 2 - "HTTP Fetching & Politeness"
Cohesion: 0.20
Nodes (12): Политика вежливости обхода (задержка, джиттер, User-Agent), Осознанное игнорирование robots.txt для /npa/view и /application, Fetcher, FakeResponse, FakeSession, test_get_raises_after_exhausting_retries_on_network_error(), test_get_raises_after_exhausting_retries_on_server_error(), test_get_retries_on_server_error_then_succeeds() (+4 more)

### Community 3 - "Crawl Queue Management"
Cohesion: 0.25
Nodes (18): Изоляция ошибок на уровне одной страницы (обход не останавливается), Хранение section в crawl_queue вместо вывода из URL документа, enqueue(), mark_done(), mark_error(), next_pending(), requeue_stale_documents(), requeue_stale_lists() (+10 more)

### Community 4 - "Storage & Project Docs"
Cohesion: 0.21
Nodes (14): CLAUDE.md (Root Project Guidance), crawl_queue (очередь обхода — источник истины резюмируемости), Решение по объёму MVP: исключение category_id/government_id/region_id, Парсер legalacts.egov.kz — план реализации, Дизайн: парсер портала legalacts.egov.kz, connect(), upsert_comments(), upsert_document() (+6 more)

### Community 5 - "Comments Parsing"
Cohesion: 0.15
Nodes (15): Единое поле body для комментариев (без перевода ru/kk), comments_total может превышать число разобранных комментариев (вкладки экспертизы), Переключение языка через cookie egovLang и /application/changelang, Ответ ведомства как вложенный дочерний комментарий (не отдельная сущность), requirements.txt (зависимости проекта), beautifulsoup4 (HTML-парсинг), lxml (парсер для BeautifulSoup), pytest (тестовый фреймворк) (+7 more)

### Community 6 - "Document Page Parsing"
Cohesion: 0.35
Nodes (9): _count_by_class_prefix(), _label_text(), parse_document_page(), Фикстура: карточка НПА с 24 комментариями (Приказ Минтруда, ru), Фикстура: та же карточка НПА, казахская версия (kk), _read(), test_parse_document_page_extracts_core_fields_without_comments(), test_parse_document_page_reads_counts_with_comments() (+1 more)

### Community 7 - "Database Schema Tests"
Cohesion: 0.60
Nodes (5): _connect(), test_comments_table_has_expected_columns(), test_crawl_queue_table_has_expected_columns(), test_documents_table_has_expected_columns(), test_init_db_creates_expected_tables()

## Ambiguous Edges - Review These
- `CLAUDE.md (Root Project Guidance)` → `Парсер legalacts.egov.kz — план реализации`  [AMBIGUOUS]
  CLAUDE.md · relation: conceptually_related_to

## Knowledge Gaps
- **4 isolated node(s):** `CLAUDE.md (Root Project Guidance)`, `Дизайн: парсер портала legalacts.egov.kz`, `lxml (парсер для BeautifulSoup)`, `pytest (тестовый фреймворк)`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 18 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `CLAUDE.md (Root Project Guidance)` and `Парсер legalacts.egov.kz — план реализации`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `Fetcher` connect `HTTP Fetching & Politeness` to `List Page Crawling`?**
  _High betweenness centrality (0.210) - this node is a cross-community bridge._
- **Why does `run()` connect `List Page Crawling` to `Orchestration Run Tests`, `HTTP Fetching & Politeness`, `Crawl Queue Management`, `Storage & Project Docs`?**
  _High betweenness centrality (0.198) - this node is a cross-community bridge._
- **Why does `process_document_entry()` connect `List Page Crawling` to `Orchestration Run Tests`, `Storage & Project Docs`, `Comments Parsing`, `Document Page Parsing`?**
  _High betweenness centrality (0.104) - this node is a cross-community bridge._
- **What connects `CLAUDE.md (Root Project Guidance)`, `Дизайн: парсер портала legalacts.egov.kz`, `lxml (парсер для BeautifulSoup)` to the rest of the system?**
  _4 weakly-connected nodes found - possible documentation gaps or missing edges._