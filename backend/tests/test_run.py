import sqlite3
from pathlib import Path
from types import SimpleNamespace

from scraper import db, queue
from scraper import run as run_module

FIXTURES = Path(__file__).parent / "fixtures"


def _connect():
    conn = sqlite3.connect(":memory:")
    # Bug fix (plan reference test omitted this): every other test module sets
    # row_factory = sqlite3.Row before init_db (see tests/test_store.py). Without
    # it, both store.upsert_document's internal dict-style row access and this
    # file's own assertions (doc_rows[0]["url"], doc["section"], ...) raise
    # TypeError: tuple indices must be integers or slices, not str.
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


class StubFetcher:
    def __init__(self, pages, status_codes=None):
        self._pages = {url: list(v) if isinstance(v, list) else [v] for url, v in pages.items()}
        self._status_codes = dict(status_codes or {})
        self.calls = []
        self.lang_calls = []

    def get(self, url):
        self.calls.append(url)
        remaining = self._pages.get(url)
        html = ""
        if remaining:
            html = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        status_code = self._status_codes.get(url, 200)
        return SimpleNamespace(text=html, status_code=status_code)

    def set_language(self, lang, location="/"):
        self.lang_calls.append(lang)


def test_user_agent_is_latin1_encodable():
    # HTTP header values (RFC 7230 §3.2) must be ISO-8859-1-encodable. requests
    # sets this header directly on the socket write, so a non-latin-1 User-Agent
    # (e.g. raw Cyrillic) raises UnicodeEncodeError on every real request while
    # still passing unit tests that stub out the session entirely.
    run_module.USER_AGENT.encode("latin-1")


class FlakyStubFetcher(StubFetcher):
    """StubFetcher variant where .get() raises for a chosen set of URLs,
    simulating a broken/unreachable page so run()'s per-entry error handling
    (mark_error + continue) can be exercised."""

    def __init__(self, pages, fail_urls=()):
        super().__init__(pages)
        self._fail_urls = set(fail_urls)

    def get(self, url):
        if url in self._fail_urls:
            self.calls.append(url)
            raise RuntimeError("simulated network failure")
        return super().get(url)


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


def test_run_marks_broken_entry_as_error_and_continues_processing_others(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    ru_html = (FIXTURES / "document_with_comments.html").read_text(encoding="utf-8")
    kk_html = (FIXTURES / "document_with_comments_kk.html").read_text(encoding="utf-8")

    bad_url = "https://legalacts.egov.kz/npa/view?id=99999999"
    good_url = "https://legalacts.egov.kz/npa/view?id=15906353"

    # Pre-seed the queue directly (bypassing seed_queue/process_list_entry)
    # so run() finds pending work and skips seeding entirely. The bad entry
    # is discovered first so it is processed before the good one.
    seed_conn = sqlite3.connect(db_path)
    seed_conn.row_factory = sqlite3.Row
    db.init_db(seed_conn)
    queue.enqueue(seed_conn, bad_url, "document", "2020-01-01T00:00:00+00:00", section="npa")
    queue.enqueue(seed_conn, good_url, "document", "2020-01-01T00:00:01+00:00", section="npa")
    seed_conn.close()

    fetcher = FlakyStubFetcher({good_url: [ru_html, kk_html]}, fail_urls={bad_url})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(db_path, limit=2)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    bad_row = conn.execute(
        "SELECT status, last_error FROM crawl_queue WHERE url = ?", (bad_url,)
    ).fetchone()
    assert bad_row["status"] == "error"
    assert bad_row["last_error"]

    good_row = conn.execute(
        "SELECT status FROM crawl_queue WHERE url = ?", (good_url,)
    ).fetchone()
    assert good_row["status"] == "done"

    doc = conn.execute(
        "SELECT * FROM documents WHERE external_id = 15906353"
    ).fetchone()
    assert doc is not None
    assert doc["status"] == "Архив"

    comment_count = conn.execute(
        "SELECT COUNT(*) AS n FROM comments WHERE document_id = ?", (doc["id"],)
    ).fetchone()["n"]
    assert comment_count == 20

    # No row exists for the failed document (upsert_document was never reached).
    failed_doc = conn.execute(
        "SELECT * FROM documents WHERE external_id = 99999999"
    ).fetchone()
    assert failed_doc is None


def test_process_document_entry_404_stores_nothing():
    conn = _connect()
    url = "https://legalacts.egov.kz/npa/view?id=404404"
    fetcher = StubFetcher({}, status_codes={url: 404})

    run_module.process_document_entry(conn, fetcher, url, section="npa")

    doc = conn.execute("SELECT * FROM documents").fetchone()
    assert doc is None
    comment_count = conn.execute("SELECT COUNT(*) AS n FROM comments").fetchone()["n"]
    assert comment_count == 0
    # Only the ru fetch happens for a 404 - no language switch/kk fetch.
    assert fetcher.calls == [url]
    assert fetcher.lang_calls == []


def test_process_list_entry_404_enqueues_nothing():
    conn = _connect()
    url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE"
    fetcher = StubFetcher({}, status_codes={url: 404})

    run_module.process_list_entry(conn, fetcher, url, section="npa")

    doc_rows = conn.execute(
        "SELECT * FROM crawl_queue WHERE page_type = 'document'"
    ).fetchall()
    assert doc_rows == []
    list_rows = conn.execute(
        "SELECT * FROM crawl_queue WHERE page_type = 'list'"
    ).fetchall()
    assert list_rows == []


def test_run_marks_404_document_entry_done_not_error(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    url = "https://legalacts.egov.kz/npa/view?id=404404"

    seed_conn = sqlite3.connect(db_path)
    seed_conn.row_factory = sqlite3.Row
    db.init_db(seed_conn)
    queue.enqueue(seed_conn, url, "document", "2020-01-01T00:00:00+00:00", section="npa")
    seed_conn.close()

    fetcher = StubFetcher({}, status_codes={url: 404})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(db_path, limit=1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT status, last_error FROM crawl_queue WHERE url = ?", (url,)
    ).fetchone()
    assert row["status"] == "done"
    assert row["last_error"] is None
    doc = conn.execute("SELECT * FROM documents").fetchone()
    assert doc is None


def test_run_marks_404_list_entry_done_not_error(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE"

    monkeypatch.setattr(run_module, "SEED_LIST_URLS", [("npa", url)])
    fetcher = StubFetcher({}, status_codes={url: 404})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(db_path, limit=1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT status, last_error FROM crawl_queue WHERE url = ?", (url,)
    ).fetchone()
    assert row["status"] == "done"
    assert row["last_error"] is None
    doc_rows = conn.execute(
        "SELECT * FROM crawl_queue WHERE page_type = 'document'"
    ).fetchall()
    assert doc_rows == []


def test_second_run_rediscovers_stale_list_page(tmp_path, monkeypatch):
    """Guards the incremental-crawl contract (C1): once a list page's queue
    row has gone stale (processed_at older than the staleness threshold),
    the next run() must re-walk it, not permanently skip it forever."""
    db_path = str(tmp_path / "test.db")
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    # Last-page URL (mirrors test_process_list_entry_stops_pagination_at_last_page)
    # so processing it enqueues only the 5 document cards and no further list page.
    seed_url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE&page=29852"

    monkeypatch.setattr(run_module, "SEED_LIST_URLS", [("npa", seed_url)])
    fetcher = StubFetcher({seed_url: list_html})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(db_path, limit=1)
    assert fetcher.calls.count(seed_url) == 1

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT status FROM crawl_queue WHERE url = ? AND page_type = 'list'", (seed_url,)
    ).fetchone()
    assert row["status"] == "done"

    # Simulate the list page having gone stale: its processed_at is old
    # enough that run()'s requeue_stale_lists call should reset it to pending.
    conn.execute(
        "UPDATE crawl_queue SET processed_at = ? WHERE url = ? AND page_type = 'list'",
        ("2020-01-01T00:00:00+00:00", seed_url),
    )
    conn.commit()
    conn.close()

    run_module.run(db_path, limit=1)

    # The stale list page must have been re-fetched, not permanently skipped.
    assert fetcher.calls.count(seed_url) == 2

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT status FROM crawl_queue WHERE url = ? AND page_type = 'list'", (seed_url,)
    ).fetchone()
    assert row["status"] == "done"
    conn.close()
