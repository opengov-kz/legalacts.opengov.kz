import sqlite3

from scraper import db


def _connect():
    conn = sqlite3.connect(":memory:")
    db.init_db(conn)
    return conn


def test_init_db_creates_expected_tables():
    conn = _connect()
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"documents", "comments", "crawl_queue"}.issubset(tables)


def test_documents_table_has_expected_columns():
    conn = _connect()
    columns = {row[1] for row in conn.execute("PRAGMA table_info(documents)")}
    assert columns == {
        "id", "external_id", "section", "url", "title_ru", "title_kk",
        "status", "doc_type", "government_body", "created_date",
        "discussion_end_date", "comments_total", "likes_count",
        "dislikes_count", "raw_html_ru", "raw_html_kk", "first_seen_at",
        "last_checked_at",
    }


def test_comments_table_has_expected_columns():
    conn = _connect()
    columns = {row[1] for row in conn.execute("PRAGMA table_info(comments)")}
    assert columns == {
        "id", "document_id", "external_comment_id",
        "parent_external_comment_id", "author_name", "body", "article_ref",
        "status", "commented_at_raw", "first_seen_at",
    }


def test_crawl_queue_table_has_expected_columns():
    conn = _connect()
    columns = {row[1] for row in conn.execute("PRAGMA table_info(crawl_queue)")}
    assert columns == {
        "url", "page_type", "section", "status", "attempts", "last_error",
        "discovered_at", "processed_at",
    }
