import datetime
from pathlib import Path
from types import SimpleNamespace

from scraper import queue
from scraper import run as run_module
from scraper import store
from db.session import create_engine_and_session_factory

FIXTURES = Path(__file__).parent / "fixtures"
UTC = datetime.timezone.utc
T1 = datetime.datetime(2026, 9, 1, tzinfo=UTC)


def _fields(**overrides):
    base = dict(
        title_ru="Title_RU_001", title_kk="Title_KK_001",
        status="Status_Value_001", doc_type="DocType_Value_001",
        government_body="Body_Value_001", created_date="2026-01-01",
        discussion_end_date="2026-12-31", comments_total=42,
        likes_count=99, dislikes_count=88,
        raw_html_ru="<html>content_ru_001</html>",
        raw_html_kk="<html>content_kk_001</html>",
    )
    base.update(overrides)
    return base


class StubFetcher:
    def __init__(self, pages, status_codes=None):
        self._pages = {url: list(v) if isinstance(v, list) else [v] for url, v in pages.items()}
        self._status_codes = dict(status_codes or {})
        self.calls = []
        self.lang_calls = []
        self.events = []

    def get(self, url):
        self.calls.append(url)
        self.events.append(("get", url))
        remaining = self._pages.get(url)
        html = ""
        if remaining:
            html = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        status_code = self._status_codes.get(url, 200)
        return SimpleNamespace(text=html, status_code=status_code)

    def set_language(self, lang, location="/"):
        self.lang_calls.append(lang)
        self.events.append(("lang", lang))


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


def test_seed_category_queue_enqueues_category_list_for_every_seed_and_category(db_session):
    run_module.seed_category_queue(db_session)

    from db.models import CrawlQueueEntry
    category_rows = db_session.execute(
        CrawlQueueEntry.__table__.select().where(CrawlQueueEntry.page_type == "category_list")
    ).fetchall()
    assert len(category_rows) == len(run_module.SEED_LIST_URLS) * len(run_module.CATEGORIES)

    npa_urls = {row.url for row in category_rows if row.section == "npa"}
    assert "https://legalacts.egov.kz/list?categoryId=346" in npa_urls

    kdrp_urls = {row.url for row in category_rows if row.section == "kdrp"}
    assert any(
        "types%5B0%5D=7001" in url and "categoryId=346" in url for url in kdrp_urls
    )


def test_with_category_preserves_existing_query_params():
    url = run_module._with_category(
        "https://legalacts.egov.kz/list?types[0]=7001&types[1]=7002", 346,
    )
    assert "categoryId=346" in url
    assert "types" in url


def test_process_document_entry_stores_document_and_comments(db_session):
    ru_html = (FIXTURES / "document_with_comments.html").read_text(encoding="utf-8")
    kk_html = (FIXTURES / "document_with_comments_kk.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    fetcher = StubFetcher({url: [ru_html, kk_html]})

    run_module.process_document_entry(db_session, fetcher, url, section="withdraw")

    from db.models import Comment, LegalAct, LegalActSnapshot
    act = db_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 15906353)
    ).fetchone()
    assert act.section == "withdraw"
    assert act.status == "Архив"
    assert act.title_kk.startswith("Қазақстан Республикасы")

    snapshot = db_session.execute(
        LegalActSnapshot.__table__.select().where(LegalActSnapshot.legal_act_id == act.id)
    ).fetchone()
    assert snapshot.raw_html_ru == ru_html
    assert snapshot.raw_html_kk == kk_html

    comment_rows = db_session.execute(
        Comment.__table__.select().where(Comment.legal_act_id == act.id)
    ).fetchall()
    assert len(comment_rows) == 20
    assert all(row.comment_channel == run_module.DEFAULT_COMMENT_CHANNEL for row in comment_rows)
    assert fetcher.lang_calls == ["kk", "ru"]


def test_process_document_entry_fetches_expert_participation_channels(db_session):
    ru_html = (FIXTURES / "document_with_comments.html").read_text(encoding="utf-8")
    kk_html = (FIXTURES / "document_with_comments_kk.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    expert_comment_html = (
        '<div class="main-comments"><div class="media">'
        '<div class="media-body"><h4 class="media-heading">Expert A 01/09 - 10:00</h4>'
        '<p id="500">Expert opinion text</p></div></div></div>'
    )
    fetcher = StubFetcher({
        url: [ru_html, kk_html],
        f"{url}&typeComment=8": expert_comment_html,
    })

    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    from db.models import Comment, LegalAct
    act = db_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 15906353)
    ).fetchone()

    expert_comments = db_session.execute(
        Comment.__table__.select().where(
            Comment.legal_act_id == act.id, Comment.comment_channel == 8,
        )
    ).fetchall()
    assert len(expert_comments) == 1
    assert expert_comments[0].body == "Expert opinion text"

    default_comments = db_session.execute(
        Comment.__table__.select().where(
            Comment.legal_act_id == act.id,
            Comment.comment_channel == run_module.DEFAULT_COMMENT_CHANNEL,
        )
    ).fetchall()
    assert len(default_comments) == 20

    called_channel_urls = {u for u in fetcher.calls if "typeComment=" in u}
    assert called_channel_urls == {
        f"{url}&typeComment={channel}" for channel in run_module.EXPERT_COMMENT_CHANNELS
    }


def test_process_document_entry_skips_expert_channels_for_arv_section(db_session):
    ru_html = (FIXTURES / "document_arv_conclusion.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/npa/viewArvConclusion?id=99999"
    fetcher = StubFetcher({url: [ru_html, ru_html]})

    run_module.process_document_entry(db_session, fetcher, url, section="arv")

    assert not any("typeComment=" in call_url for call_url in fetcher.calls)


def test_process_document_entry_collects_full_version_chain(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    version2_url = "https://legalacts.egov.kz/application/viewcardhistory?id=200"
    version1_url = "https://legalacts.egov.kz/application/viewcardhistory?id=100"

    main_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<div class="blog-info"><span class="gov-parent">Main Body</span></div>'
        '<small><b>Статус:</b> Архив</small>'
        '<small><b>Версия проекта:</b> Версия 3 '
        '( <a href="/application/viewcardhistory?id=200">Версия 2</a> )</small>'
        '</div>'
    )
    version2_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<small><b>Статус:</b></small>'
        '<small><b>Версия проекта:</b> Версия 2 '
        '( <a href="/application/viewcardhistory?id=100">Версия 1</a> )</small>'
        '<small><b>Государственный орган НПА:</b> Version2 Body</small>'
        '</div>'
    )
    version1_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<small><b>Статус:</b></small>'
        '<small><b>Версия проекта:</b> Версия 1</small>'
        '<small><b>Государственный орган НПА:</b> Version1 Body</small>'
        '</div>'
    )

    fetcher = StubFetcher({
        url: main_html,
        version2_url: version2_html,
        version1_url: version1_html,
    })

    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    from db.models import DocumentVersion, LegalAct
    act = db_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 15906353)
    ).fetchone()

    versions = db_session.execute(
        DocumentVersion.__table__.select()
        .where(DocumentVersion.legal_act_id == act.id)
        .order_by(DocumentVersion.version_number)
    ).fetchall()
    assert len(versions) == 2
    versions_by_external_id = {v.external_id: v for v in versions}
    assert versions_by_external_id[100].version_number == 1
    assert versions_by_external_id[200].version_number == 2

    from db.models import GovernmentBody
    v200_body = db_session.get(GovernmentBody, versions_by_external_id[200].government_body_id)
    assert v200_body.name == "Version2 Body"

    assert fetcher.calls.count(version2_url) == 1
    assert fetcher.calls.count(version1_url) == 1


def test_collect_prior_versions_stops_on_404_without_storing_garbage(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    version1_url = "https://legalacts.egov.kz/application/viewcardhistory?id=100"

    main_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<div class="blog-info"><span class="gov-parent">Main Body</span></div>'
        '<small><b>Версия проекта:</b> Версия 2 '
        '( <a href="/application/viewcardhistory?id=100">Версия 1</a> )</small>'
        '</div>'
    )

    fetcher = StubFetcher({url: main_html}, status_codes={version1_url: 404})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    from db.models import DocumentVersion
    versions = db_session.execute(DocumentVersion.__table__.select()).fetchall()
    assert versions == []


def test_process_document_entry_does_not_refetch_known_versions_on_recrawl(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    version1_url = "https://legalacts.egov.kz/application/viewcardhistory?id=100"

    main_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<div class="blog-info"><span class="gov-parent">Main Body</span></div>'
        '<small><b>Версия проекта:</b> Версия 2 '
        '( <a href="/application/viewcardhistory?id=100">Версия 1</a> )</small>'
        '</div>'
    )
    version1_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<small><b>Версия проекта:</b> Версия 1</small>'
        '</div>'
    )

    fetcher = StubFetcher({url: main_html, version1_url: version1_html})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")
    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    assert fetcher.calls.count(version1_url) == 1


def test_process_document_entry_skips_version_chain_for_arv_section(db_session):
    ru_html = (FIXTURES / "document_arv_conclusion.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/npa/viewArvConclusion?id=99999"
    fetcher = StubFetcher({url: [ru_html, ru_html]})

    run_module.process_document_entry(db_session, fetcher, url, section="arv")

    assert not any("viewcardhistory" in call_url for call_url in fetcher.calls)


def test_process_document_entry_collects_report_when_link_present(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    report_url = "https://legalacts.egov.kz/report?id=15906353"

    main_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<div class="blog-info"><span class="gov-parent">Main Body</span></div>'
        '<small><b>Статус:</b> Архив</small>'
        '<a href="/report?id=15906353">Посмотреть отчет</a>'
        '</div>'
    )
    report_html = "<html>report content</html>"

    fetcher = StubFetcher({url: main_html, report_url: report_html})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    from db.models import LegalAct, Report
    act = db_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 15906353)
    ).fetchone()
    report = db_session.execute(
        Report.__table__.select().where(Report.legal_act_id == act.id)
    ).fetchone()
    assert report is not None
    assert report.raw_html_ru == report_html


def test_process_document_entry_does_not_refetch_existing_report(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    report_url = "https://legalacts.egov.kz/report?id=15906353"

    main_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<div class="blog-info"><span class="gov-parent">Main Body</span></div>'
        '<a href="/report?id=15906353">Посмотреть отчет</a>'
        '</div>'
    )
    fetcher = StubFetcher({url: main_html, report_url: "<html>report</html>"})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")
    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    assert fetcher.calls.count(report_url) == 1


def test_process_document_entry_skips_report_when_no_link(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=15906353"

    main_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<div class="blog-info"><span class="gov-parent">Main Body</span></div>'
        '</div>'
    )
    fetcher = StubFetcher({url: main_html})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    from db.models import Report
    assert db_session.execute(Report.__table__.select()).fetchall() == []
    assert not any("/report?id=" in call_url for call_url in fetcher.calls)


def test_process_document_entry_skips_report_for_arv_section(db_session):
    ru_html = (FIXTURES / "document_arv_conclusion.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/npa/viewArvConclusion?id=99999"
    fetcher = StubFetcher({url: [ru_html, ru_html]})

    run_module.process_document_entry(db_session, fetcher, url, section="arv")

    assert not any("/report?id=" in call_url for call_url in fetcher.calls)


def test_report_fetch_404_does_not_store_anything(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=15906353"
    report_url = "https://legalacts.egov.kz/report?id=15906353"

    main_html = (
        '<div class="view-npa"><h2>Test Act</h2>'
        '<div class="blog-info"><span class="gov-parent">Main Body</span></div>'
        '<a href="/report?id=15906353">Посмотреть отчет</a>'
        '</div>'
    )
    fetcher = StubFetcher({url: main_html}, status_codes={report_url: 404})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    from db.models import Report
    assert db_session.execute(Report.__table__.select()).fetchall() == []


def test_process_document_entry_404_stores_nothing(db_session):
    url = "https://legalacts.egov.kz/npa/view?id=404404"
    fetcher = StubFetcher({}, status_codes={url: 404})

    run_module.process_document_entry(db_session, fetcher, url, section="npa")

    from db.models import LegalAct
    assert db_session.execute(LegalAct.__table__.select()).fetchone() is None
    assert fetcher.calls == [url]
    assert fetcher.lang_calls == []


def test_process_list_entry_404_enqueues_nothing(db_session):
    url = "https://legalacts.egov.kz/list?status=IN_ARCHIVE"
    fetcher = StubFetcher({}, status_codes={url: 404})

    run_module.process_list_entry(db_session, fetcher, url, section="npa")

    from db.models import CrawlQueueEntry
    assert db_session.execute(CrawlQueueEntry.__table__.select()).fetchall() == []


def test_process_category_list_entry_links_known_act(db_session):
    store.upsert_legal_act(db_session, 15908401, "npa", "url1", _fields(), T1)

    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/list?categoryId=346"
    fetcher = StubFetcher({url: list_html})

    run_module.process_category_list_entry(db_session, fetcher, url, section="npa")

    from db.models import Category, LegalAct, LegalActCategory
    act = db_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 15908401)
    ).fetchone()
    category = db_session.query(Category).filter_by(external_id=346).one()
    link = db_session.query(LegalActCategory).filter_by(
        legal_act_id=act.id, category_id=category.id,
    ).one_or_none()
    assert link is not None
    assert category.name == "Информационные технологии"


def test_process_category_list_entry_skips_unknown_act(db_session):
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/list?categoryId=346"
    fetcher = StubFetcher({url: list_html})

    run_module.process_category_list_entry(db_session, fetcher, url, section="npa")

    from db.models import LegalAct, LegalActCategory
    assert db_session.execute(LegalAct.__table__.select()).fetchall() == []
    assert db_session.execute(LegalActCategory.__table__.select()).fetchall() == []


def test_process_category_list_entry_falls_back_to_static_name_when_dropdown_missing(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 100, "npa", "url1", _fields(), T1)
    url = "https://legalacts.egov.kz/list?categoryId=346"
    html = '<div class="contentlist"><h3><a href="/npa/view?id=100">Title</a></h3></div>'
    fetcher = StubFetcher({url: html})

    run_module.process_category_list_entry(db_session, fetcher, url, section="npa")

    from db.models import Category
    category = db_session.query(Category).filter_by(external_id=346).one()
    assert category.name == run_module.CATEGORY_NAMES[346]


def test_process_category_list_entry_returns_early_when_category_id_unknown(db_session):
    url = "https://legalacts.egov.kz/list?categoryId=999999"
    html = '<div class="contentlist"><h3><a href="/npa/view?id=100">Title</a></h3></div>'
    fetcher = StubFetcher({url: html})

    run_module.process_category_list_entry(db_session, fetcher, url, section="npa")

    from db.models import Category
    assert db_session.execute(Category.__table__.select()).fetchall() == []


def test_process_category_list_entry_enqueues_next_page(db_session):
    list_html = (FIXTURES / "list_page.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/list?categoryId=346"
    fetcher = StubFetcher({url: list_html})

    run_module.process_category_list_entry(db_session, fetcher, url, section="npa")

    from db.models import CrawlQueueEntry
    next_page = db_session.execute(
        CrawlQueueEntry.__table__.select().where(CrawlQueueEntry.page_type == "category_list")
    ).fetchall()
    assert len(next_page) == 1
    assert "page=2" in next_page[0].url
    assert "categoryId=346" in next_page[0].url


def test_process_category_list_entry_skips_card_with_unparsable_id(db_session):
    url = "https://legalacts.egov.kz/list?categoryId=346"
    html = (
        '<select id="categoryId"><option value="346">Информационные технологии</option></select>'
        '<div class="contentlist"><h3><a href="/npa/view?id=not-a-number">Bad</a></h3></div>'
        '<div class="contentlist"><h3><a href="/npa/view">No id at all</a></h3></div>'
    )
    fetcher = StubFetcher({url: html})

    run_module.process_category_list_entry(db_session, fetcher, url, section="npa")

    from db.models import CrawlQueueEntry
    next_page = db_session.execute(
        CrawlQueueEntry.__table__.select().where(CrawlQueueEntry.page_type == "category_list")
    ).fetchall()
    # totalPages defaults to 1 when absent from this minimal HTML, current page is 1,
    # so no next-page entry is expected here — this test's point is that processing
    # the malformed cards above did not raise.
    assert next_page == []


def test_process_category_list_entry_404_enqueues_nothing(db_session):
    url = "https://legalacts.egov.kz/list?categoryId=346"
    fetcher = StubFetcher({}, status_codes={url: 404})

    run_module.process_category_list_entry(db_session, fetcher, url, section="npa")

    from db.models import Category, CrawlQueueEntry
    assert db_session.execute(Category.__table__.select()).fetchall() == []
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


def test_run_switches_to_russian_before_first_document_fetch(database_url, monkeypatch):
    ru_html = (FIXTURES / "document_with_comments.html").read_text(encoding="utf-8")
    kk_html = (FIXTURES / "document_with_comments_kk.html").read_text(encoding="utf-8")
    url = "https://legalacts.egov.kz/npa/view?id=15906353"

    _, SessionLocal = create_engine_and_session_factory(database_url)
    seed_session = SessionLocal()
    queue.enqueue(seed_session, url, "document", datetime.datetime(2020, 1, 1, tzinfo=UTC), section="npa")
    seed_session.close()

    fetcher = StubFetcher({url: [ru_html, kk_html]})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(database_url, limit=1)

    first_get_index = fetcher.events.index(("get", url))
    assert fetcher.events[:first_get_index] == [("lang", "ru")], (
        "run() must switch the session language to ru before the first document "
        "GET, otherwise a cold session defaults to kk and mislabels the response "
        "as raw_html_ru"
    )


def test_run_marks_broken_entry_as_error_and_continues_processing_others(database_url, monkeypatch):
    ru_html = (FIXTURES / "document_with_comments.html").read_text(encoding="utf-8")
    kk_html = (FIXTURES / "document_with_comments_kk.html").read_text(encoding="utf-8")

    bad_url = "https://legalacts.egov.kz/npa/view?id=99999999"
    good_url = "https://legalacts.egov.kz/npa/view?id=15906353"

    _, SessionLocal = create_engine_and_session_factory(database_url)
    seed_session = SessionLocal()
    queue.enqueue(seed_session, bad_url, "document", datetime.datetime(2020, 1, 1, tzinfo=UTC), section="npa")
    queue.enqueue(seed_session, good_url, "document", datetime.datetime(2020, 1, 1, 0, 0, 1, tzinfo=UTC), section="npa")
    seed_session.close()

    fetcher = FlakyStubFetcher({good_url: [ru_html, kk_html]}, fail_urls={bad_url})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(database_url, limit=2)

    check_session = SessionLocal()
    from db.models import CrawlQueueEntry, LegalAct

    bad_row = check_session.get(CrawlQueueEntry, bad_url)
    assert bad_row.status == "error"
    assert bad_row.last_error

    good_row = check_session.get(CrawlQueueEntry, good_url)
    assert good_row.status == "done"

    act = check_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 15906353)
    ).fetchone()
    assert act is not None
    assert act.status == "Архив"

    failed_act = check_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 99999999)
    ).fetchone()
    assert failed_act is None
    check_session.close()


def test_run_marks_404_document_entry_done_not_error(database_url, monkeypatch):
    url = "https://legalacts.egov.kz/npa/view?id=404404"

    _, SessionLocal = create_engine_and_session_factory(database_url)
    seed_session = SessionLocal()
    queue.enqueue(seed_session, url, "document", datetime.datetime(2020, 1, 1, tzinfo=UTC), section="npa")
    seed_session.close()

    fetcher = StubFetcher({}, status_codes={url: 404})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(database_url, limit=1)

    check_session = SessionLocal()
    from db.models import CrawlQueueEntry, LegalAct
    row = check_session.get(CrawlQueueEntry, url)
    assert row.status == "done"
    assert row.last_error is None
    assert check_session.execute(LegalAct.__table__.select()).fetchone() is None
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
    entry.processed_at = datetime.datetime(2020, 1, 1, tzinfo=UTC)
    session.commit()
    session.close()

    run_module.run(database_url, limit=1)

    assert fetcher.calls.count(seed_url) == 2


def test_run_processes_category_list_only_after_list_and_document_queues_empty(database_url, monkeypatch):
    # Fix 1 makes has_pending consider only list/document, so once both drain,
    # run() re-fires seed_queue() (that's the point of the fix). This test is
    # about queue *priority* (category_list is dispatched last), not about
    # reseeding, so neutralize SEED_LIST_URLS to keep the second run() call
    # from repopulating "list" and masking the category_list dispatch.
    monkeypatch.setattr(run_module, "SEED_LIST_URLS", [])
    ru_html = (FIXTURES / "document_with_comments.html").read_text(encoding="utf-8")
    kk_html = (FIXTURES / "document_with_comments_kk.html").read_text(encoding="utf-8")
    doc_url = "https://legalacts.egov.kz/npa/view?id=15906353"
    category_url = "https://legalacts.egov.kz/list?categoryId=346"
    category_html = (
        '<select id="categoryId"><option value="346">Информационные технологии</option></select>'
    )

    _, SessionLocal = create_engine_and_session_factory(database_url)
    seed_session = SessionLocal()
    queue.enqueue(seed_session, doc_url, "document", datetime.datetime(2020, 1, 1, tzinfo=UTC), section="npa")
    queue.enqueue(seed_session, category_url, "category_list", datetime.datetime(2020, 1, 1, tzinfo=UTC), section="npa")
    seed_session.close()

    fetcher = StubFetcher({doc_url: [ru_html, kk_html], category_url: category_html})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(database_url, limit=1)

    check_session = SessionLocal()
    from db.models import CrawlQueueEntry
    assert check_session.get(CrawlQueueEntry, doc_url).status == "done"
    assert check_session.get(CrawlQueueEntry, category_url).status == "pending"
    check_session.close()

    run_module.run(database_url, limit=1)

    check_session2 = SessionLocal()
    assert check_session2.get(CrawlQueueEntry, category_url).status == "done"
    check_session2.close()


def test_run_seeds_category_queue_even_when_list_and_document_queues_are_busy(database_url, monkeypatch):
    doc_url = "https://legalacts.egov.kz/npa/view?id=15906353"

    _, SessionLocal = create_engine_and_session_factory(database_url)
    seed_session = SessionLocal()
    queue.enqueue(seed_session, doc_url, "document", datetime.datetime(2020, 1, 1, tzinfo=UTC), section="npa")
    seed_session.close()

    fetcher = StubFetcher({})
    monkeypatch.setattr(run_module, "Fetcher", lambda user_agent: fetcher)

    run_module.run(database_url, limit=0)

    check_session = SessionLocal()
    from db.models import CrawlQueueEntry
    category_rows = check_session.execute(
        CrawlQueueEntry.__table__.select().where(CrawlQueueEntry.page_type == "category_list")
    ).fetchall()
    assert len(category_rows) == len(run_module.SEED_LIST_URLS) * len(run_module.CATEGORIES)
    check_session.close()
