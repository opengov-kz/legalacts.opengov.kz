from sqlalchemy import inspect


def test_create_all_creates_expected_tables(pg_engine):
    from db.models import Base

    Base.metadata.create_all(pg_engine)
    tables = set(inspect(pg_engine).get_table_names())
    assert {"documents", "comments", "crawl_queue"}.issubset(tables)


def test_documents_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("documents")}
    assert columns == {
        "id", "external_id", "section", "url", "title_ru", "title_kk",
        "status", "doc_type", "government_body", "created_date",
        "discussion_end_date", "comments_total", "likes_count",
        "dislikes_count", "raw_html_ru", "raw_html_kk", "first_seen_at",
        "last_checked_at",
    }


def test_comments_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("comments")}
    assert columns == {
        "id", "document_id", "external_comment_id",
        "parent_external_comment_id", "author_name", "body", "article_ref",
        "status", "commented_at_raw", "first_seen_at",
    }


def test_crawl_queue_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("crawl_queue")}
    assert columns == {
        "url", "page_type", "section", "status", "attempts", "last_error",
        "discovered_at", "processed_at",
    }
