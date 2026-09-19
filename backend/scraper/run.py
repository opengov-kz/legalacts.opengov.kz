import argparse
import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import db, queue, store
from .fetch import Fetcher
from .parsers import comments as comments_parser
from .parsers import document_page, list_page

BASE_URL = "https://legalacts.egov.kz"
USER_AGENT = (
    "legalacts-research-bot/0.1 (personal research project; "
    "contact: k.nefyodov@qbs.kz)"
)
STALE_AFTER_DAYS = 7

SEED_LIST_URLS = [
    ("npa", f"{BASE_URL}/list"),
    ("npa", f"{BASE_URL}/list?status=IN_ARCHIVE"),
    ("kdrp", f"{BASE_URL}/list?types[0]=7001&types[1]=7002"),
    ("arv", f"{BASE_URL}/Arvlist"),
    ("arv", f"{BASE_URL}/Arvlist?status=IN_ARCHIVE"),
    ("withdraw", f"{BASE_URL}/application/withdraw"),
]

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def seed_queue(conn):
    discovered = now_iso()
    for section, url in SEED_LIST_URLS:
        queue.enqueue(conn, url, "list", discovered, section=section)


def _current_page(url):
    query = dict(parse_qsl(urlsplit(url).query))
    return int(query.get("page", 1))


def _set_page_param(url, page):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query["page"] = str(page)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def process_list_entry(conn, fetcher, url, section="npa"):
    response = fetcher.get(url)
    if response.status_code == 404:
        return
    html = response.text

    discovered = now_iso()
    for card in list_page.parse_list_page(html):
        queue.enqueue(conn, card["url"], "document", discovered, section=section)

    total_pages = list_page.parse_total_pages(html)
    current_page = _current_page(url)
    if current_page < total_pages:
        queue.enqueue(
            conn, _set_page_param(url, current_page + 1), "list", discovered, section=section
        )


def process_document_entry(conn, fetcher, url, section="npa"):
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
        # The Fetcher's single session is reused for the whole crawl, so its
        # server-side language cookie must always be reverted to "ru" here,
        # even if the kk fetch/parse above raised — otherwise every later
        # document's "ru" fetch in this run would silently receive kk HTML.
        fetcher.set_language("ru", location=url)

    external_id = int(dict(parse_qsl(urlsplit(url).query))["id"])
    parsed_comments = comments_parser.parse_comments(ru_html)

    timestamp = now_iso()
    document_id = store.upsert_document(conn, external_id, section, url, fields, timestamp)
    store.upsert_comments(conn, document_id, parsed_comments, timestamp)


def run(db_path, limit=None):
    conn = db.connect(db_path)
    db.init_db(conn)

    has_pending = (
        queue.next_pending(conn, "list") is not None
        or queue.next_pending(conn, "document") is not None
    )
    if not has_pending:
        seed_queue(conn)

    stale_threshold = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=STALE_AFTER_DAYS)
    ).isoformat()
    queue.requeue_stale_documents(conn, stale_threshold)
    queue.requeue_stale_lists(conn, stale_threshold)

    fetcher = Fetcher(USER_AGENT)
    processed = 0

    while limit is None or processed < limit:
        list_url = queue.next_pending(conn, "list")
        if list_url is not None:
            # Раздел записан в очередь при постановке этой строки (см. Task 2) —
            # по самому URL списочной страницы его тоже можно было бы вычислить
            # (/Arvlist, /application/withdraw, /list?types[]=... различимы),
            # но чтение из очереди даёт один источник истины и для списков, и для
            # документов, у которых URL раздел не выдаёт (Task 8).
            section = queue.section_for(conn, list_url) or "npa"
            try:
                process_list_entry(conn, fetcher, list_url, section=section)
                queue.mark_done(conn, list_url, now_iso())
            except Exception as exc:
                # Одна сломанная страница не должна останавливать весь обход (спек, раздел 3).
                queue.mark_error(conn, list_url, str(exc), now_iso())
            processed += 1
            continue

        document_url = queue.next_pending(conn, "document")
        if document_url is not None:
            section = queue.section_for(conn, document_url) or "npa"
            try:
                process_document_entry(conn, fetcher, document_url, section=section)
                queue.mark_done(conn, document_url, now_iso())
            except Exception as exc:
                queue.mark_error(conn, document_url, str(exc), now_iso())
            processed += 1
            continue

        break

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Обход портала legalacts.egov.kz")
    parser.add_argument("--db", default="legalacts.db")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(args.db, limit=args.limit)


if __name__ == "__main__":
    main()
