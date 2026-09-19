from pathlib import Path
from types import SimpleNamespace

from scraper import queue
from scraper import run as run_module
from db.session import create_engine_and_session_factory

FIXTURES = Path(__file__).parent / "fixtures"


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


class FlakyStubFetcher(StubFetcher):
    def __init__(self, pages, fail_urls=()):
        super().__init__(pages)
        self._fail_urls = set(fail_urls)

    def get(self, url):
        if url in self._fail_urls:
            self.calls.append(url)
            raise RuntimeError("simulated network failure")
        return super().get(url)


def test_user_agent_is_latin1_encodable():
    run_module.USER_AGENT.encode("latin-1")


def test_process_list_entry_enqueues_documents_and_next_page(db_session):
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE"
    fetcher = StubFetcher({url: list_html})

    run_module.process_list_entry(db_session, fetcher, url, section="npa")

    assert queue.next_pending(db_session, "document") is not None
    from db.models import CrawlQueueEntry
    doc_urls = db_session.execute(
        CrawlQueueEntry.__table__.select().where(CrawlQueueEntry.page_type == "document")
    ).fetchall()
    assert len(doc_urls) == 5
    assert queue.section_for(db_session, doc_urls[0].url) == "npa"

    page_rows = db_session.execute(
        CrawlQueueEntry.__table__.select().where(CrawlQueueEntry.page_type == "list")
    ).fetchall()
    assert len(page_rows) == 1
    assert "page=2" in page_rows[0].url
    assert "status=IN_ARCHIVE" in page_rows[0].url


def test_process_list_entry_stops_pagination_at_last_page(db_session):
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE&page=29852"
    fetcher = StubFetcher({url: list_html})

    run_module.process_list_entry(db_session, fetcher, url)

    from db.models import CrawlQueueEntry
    page_rows = db_session.execute(
        CrawlQueueEntry.__table__.select().where(CrawlQueueEntry.page_type == "list")
    ).fetchall()
    assert len(page_rows) == 0


def test_process_document_entry_stores_document_and_comments(db_session):
    ru_html = (FIXTURES / "document_with_comments.html").read_text(encoding="utf-8")
    kk_html = (FIXTURES / "document_with_comments_kk.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    fetcher = StubFetcher({url: [ru_html, kk_html]})

    run_module.process_document_entry(db_session, fetcher, url, section="withdraw")

    from db.models import Comment, Document
    doc = db_session.execute(
        Document.__table__.select().where(Document.external_id == 15906353)
    ).fetchone()
    assert doc.section == "withdraw"
    assert doc.status == "Архив"
    assert doc.title_kk.startswith("Қазақстан Республикасы")
    assert doc.raw_html_ru == ru_html
    assert doc.raw_html_kk == kk_html

    comment_count = db_session.execute(
        Comment.__table__.select().where(Comment.document_id == doc.id)
    ).fetchall()
    assert len(comment_count) == 20
    assert fetcher.lang_calls == ["kk", "ru"]


def test_process_document_entry_404_stores_nothing(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=404404"
    fetcher = StubFetcher({}, status_codes={url: 404})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    from db.models import Document
    assert db_session.execute(Document.__table__.select()).fetchone() is None
    assert fetcher.calls == [url]
    assert fetcher.lang_calls == []


def test_process_list_entry_404_enqueues_nothing(db_session):
    url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE"
    fetcher = StubFetcher({}, status_codes={url: 404})

    run_module.process_list_entry(db_session, fetcher, url, section="npa")

    from db.models import CrawlQueueEntry
    assert db_session.execute(CrawlQueueEntry.__table__.select()).fetchall() == []


def test_run_seeds_queue_and_respects_limit(database_url, monkeypatch):
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    seed_url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE"

    monkeypatch.setattr(run_module, "SEED_LIST_URLS", [("npa", seed_url)])
    fake_fetcher = StubFetcher({seed_url: list_html})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fake_fetcher)

    run_module.run(database_url, limit=1)

    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    from db.models import CrawlQueueEntry
    doc_rows = session.execute(
        CrawlQueueEntry.__table__.select().where(CrawlQueueEntry.page_type == "document")
    ).fetchall()
    assert len(doc_rows) == 5
    assert queue.section_for(session, doc_rows[0].url) == "npa"
    session.close()


def test_run_marks_broken_entry_as_error_and_continues_processing_others(database_url, monkeypatch):
    ru_html = (FIXTURES / "document_with_comments.html").read_text(encoding="utf-8")
    kk_html = (FIXTURES / "document_with_comments_kk.html").read_text(encoding="utf-8")

    bad_url = "https://legalacts.egov.kz/npa/view?id=99999999"
    good_url = "https://legalacts.egov.kz/npa/view?id=15906353"

    _, SessionLocal = create_engine_and_session_factory(database_url)
    seed_session = SessionLocal()
    queue.enqueue(seed_session, bad_url, "document", "2020-01-01T00:00:00+00:00", section="npa")
    queue.enqueue(seed_session, good_url, "document", "2020-01-01T00:00:01+00:00", section="npa")
    seed_session.close()

    fetcher = FlakyStubFetcher({good_url: [ru_html, kk_html]}, fail_urls={bad_url})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(database_url, limit=2)

    check_session = SessionLocal()
    from db.models import CrawlQueueEntry, Document

    bad_row = check_session.get(CrawlQueueEntry, bad_url)
    assert bad_row.status == "error"
    assert bad_row.last_error

    good_row = check_session.get(CrawlQueueEntry, good_url)
    assert good_row.status == "done"

    doc = check_session.execute(
        Document.__table__.select().where(Document.external_id == 15906353)
    ).fetchone()
    assert doc is not None
    assert doc.status == "Архив"

    failed_doc = check_session.execute(
        Document.__table__.select().where(Document.external_id == 99999999)
    ).fetchone()
    assert failed_doc is None
    check_session.close()


def test_run_marks_404_document_entry_done_not_error(database_url, monkeypatch):
    url = "https://legalacts.egov.kz/npa/view?id=404404"

    _, SessionLocal = create_engine_and_session_factory(database_url)
    seed_session = SessionLocal()
    queue.enqueue(seed_session, url, "document", "2020-01-01T00:00:00+00:00", section="npa")
    seed_session.close()

    fetcher = StubFetcher({}, status_codes={url: 404})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(database_url, limit=1)

    check_session = SessionLocal()
    from db.models import CrawlQueueEntry, Document
    row = check_session.get(CrawlQueueEntry, url)
    assert row.status == "done"
    assert row.last_error is None
    assert check_session.execute(Document.__table__.select()).fetchone() is None
    check_session.close()


def test_second_run_rediscovers_stale_list_page(database_url, monkeypatch):
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    seed_url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE&page=29852"

    monkeypatch.setattr(run_module, "SEED_LIST_URLS", [("npa", seed_url)])
    fetcher = StubFetcher({seed_url: list_html})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(database_url, limit=1)
    assert fetcher.calls.count(seed_url) == 1

    _, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()
    from db.models import CrawlQueueEntry
    entry = session.get(CrawlQueueEntry, seed_url)
    assert entry.status == "done"
    entry.processed_at = "2020-01-01T00:00:00+00:00"
    session.commit()
    session.close()

    run_module.run(database_url, limit=1)

    assert fetcher.calls.count(seed_url) == 2
