import argparse
import datetime
import os
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from db.session import create_engine_and_session_factory
from scraper import queue, store
from scraper.fetch import Fetcher
from scraper.parsers import comments as comments_parser
from scraper.parsers import document_page, list_page

BASE_URL = "https://legalacts.egov.kz"
USER_AGENT = (
    "legalacts-research-bot/0.1 (personal research project; "
    "contact: k.nefyodov@qbs.kz)"
)
STALE_AFTER_DAYS = 7
DEFAULT_COMMENT_CHANNEL = 6  # вкладка «Комментарий» (typeComment=6)
EXPERT_COMMENT_CHANNELS = (1, 3, 4, 7, 8, 9, 10)  # остальные вкладки экспертного участия

SEED_LIST_URLS = [
    ("npa", f"{BASE_URL}/list"),
    ("npa", f"{BASE_URL}/list?status=IN_ARCHIVE"),
    ("kdrp", f"{BASE_URL}/list?types[0]=7001&types[1]=7002"),
    ("arv", f"{BASE_URL}/Arvlist"),
    ("arv", f"{BASE_URL}/Arvlist?status=IN_ARCHIVE"),
    ("withdraw", f"{BASE_URL}/application/withdraw"),
]


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def seed_queue(session):
    discovered = now()
    for section, url in SEED_LIST_URLS:
        queue.enqueue(session, url, "list", discovered, section=section)


def _current_page(url):
    query = dict(parse_qsl(urlsplit(url).query))
    return int(query.get("page", 1))


def _set_page_param(url, page):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["page"] = str(page)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _with_type_comment(url, channel):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["typeComment"] = str(channel)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _collect_prior_versions(session, fetcher, legal_act_id, next_url, timestamp):
    while next_url is not None:
        full_url = urljoin(BASE_URL, next_url)
        external_id = int(dict(parse_qsl(urlsplit(full_url).query))["id"])
        if store.document_version_exists(session, external_id):
            return
        response = fetcher.get(full_url)
        if response.status_code == 404:
            return
        html = response.text
        fields = document_page.parse_document_page(html)
        fields["raw_html_ru"] = html
        version_info = document_page.parse_version_info(html)
        store.upsert_document_version(
            session, legal_act_id, external_id, fields, version_info["version_number"], timestamp,
        )
        next_url = version_info["previous_version_url"]


def process_list_entry(session, fetcher, url, section="npa"):
    response = fetcher.get(url)
    if response.status_code == 404:
        return
    html = response.text

    discovered = now()
    for card in list_page.parse_list_page(html):
        queue.enqueue(session, card["url"], "document", discovered, section=section)

    total_pages = list_page.parse_total_pages(html)
    current_page = _current_page(url)
    if current_page < total_pages:
        queue.enqueue(
            session, _set_page_param(url, current_page + 1), "list", discovered, section=section
        )


def process_document_entry(session, fetcher, url, section="npa"):
    ru_response = fetcher.get(url)
    if ru_response.status_code == 404:
        return
    ru_html = ru_response.text
    fields = document_page.parse_document_page(ru_html)
    fields["title_ru"] = fields.pop("title")
    fields["raw_html_ru"] = ru_html

    fetcher.set_language("kk", location=url)
    try:
        kk_response = fetcher.get(url)
        kk_html = kk_response.text
        kk_fields = document_page.parse_document_page(kk_html)
        fields["title_kk"] = kk_fields["title"]
        fields["raw_html_kk"] = kk_html
    finally:
        fetcher.set_language("ru", location=url)

    external_id = int(dict(parse_qsl(urlsplit(url).query))["id"])
    parsed_comments = comments_parser.parse_comments(ru_html)

    timestamp = now()
    legal_act_id = store.upsert_legal_act(session, external_id, section, url, fields, timestamp)
    store.upsert_comments(session, legal_act_id, parsed_comments, DEFAULT_COMMENT_CHANNEL, timestamp)

    if section != "arv":
        for channel in EXPERT_COMMENT_CHANNELS:
            channel_response = fetcher.get(_with_type_comment(url, channel))
            channel_comments = comments_parser.parse_comments(channel_response.text)
            store.upsert_comments(session, legal_act_id, channel_comments, channel, timestamp)

        version_info = document_page.parse_version_info(ru_html)
        _collect_prior_versions(
            session, fetcher, legal_act_id, version_info["previous_version_url"], timestamp,
        )

        report_url = document_page.parse_report_link(ru_html)
        if report_url is not None and not store.report_exists(session, legal_act_id):
            report_response = fetcher.get(urljoin(BASE_URL, report_url))
            if report_response.status_code != 404:
                store.upsert_report(session, legal_act_id, report_response.text, timestamp)


def run(database_url, limit=None):
    engine, SessionLocal = create_engine_and_session_factory(database_url)
    session = SessionLocal()

    has_pending = (
        queue.next_pending(session, "list") is not None
        or queue.next_pending(session, "document") is not None
    )
    if not has_pending:
        seed_queue(session)

    stale_threshold = now() - datetime.timedelta(days=STALE_AFTER_DAYS)
    queue.requeue_stale_documents(session, stale_threshold)
    queue.requeue_stale_lists(session, stale_threshold)

    fetcher = Fetcher(USER_AGENT)
    fetcher.set_language("ru")
    processed = 0

    while limit is None or processed < limit:
        list_url = queue.next_pending(session, "list")
        if list_url is not None:
            section = queue.section_for(session, list_url) or "npa"
            try:
                process_list_entry(session, fetcher, list_url, section=section)
                queue.mark_done(session, list_url, now())
            except Exception as exc:
                session.rollback()
                queue.mark_error(session, list_url, str(exc), now())
            processed += 1
            continue

        document_url = queue.next_pending(session, "document")
        if document_url is not None:
            section = queue.section_for(session, document_url) or "npa"
            try:
                process_document_entry(session, fetcher, document_url, section=section)
                queue.mark_done(session, document_url, now())
            except Exception as exc:
                session.rollback()
                queue.mark_error(session, document_url, str(exc), now())
            processed += 1
            continue

        break

    session.close()
    engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Обход портала legalacts.egov.kz")
    parser.add_argument("--database-url", default=None, help="Override DATABASE_URL env var")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    database_url = args.database_url or os.environ["DATABASE_URL"]
    run(database_url, limit=args.limit)


if __name__ == "__main__":
    main()
