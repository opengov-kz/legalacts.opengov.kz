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
