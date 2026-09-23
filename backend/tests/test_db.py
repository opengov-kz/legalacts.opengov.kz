from sqlalchemy import inspect


def test_migration_creates_expected_tables(pg_engine):
    tables = set(inspect(pg_engine).get_table_names())
    assert {
        "legal_acts", "comments", "crawl_queue",
        "government_bodies", "act_types", "legal_act_snapshots", "document_versions", "reports",
    }.issubset(tables)


def test_legal_acts_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("legal_acts")}
    assert columns == {
        "id", "external_id", "section", "url", "title_ru", "title_kk", "status",
        "act_type_id", "government_body_id", "created_date", "discussion_end_date",
        "comments_total", "likes_count", "dislikes_count",
        "content_sha256_ru", "content_sha256_kk", "first_seen_at", "last_checked_at",
    }


def test_comments_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("comments")}
    assert columns == {
        "id", "legal_act_id", "external_comment_id", "parent_external_comment_id",
        "comment_channel", "author_name", "body", "article_ref", "status",
        "commented_at_raw", "first_seen_at",
    }


def test_legal_act_snapshots_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("legal_act_snapshots")}
    assert columns == {
        "id", "legal_act_id", "captured_at", "raw_html_ru", "raw_html_kk",
        "content_sha256_ru", "content_sha256_kk", "title_ru", "title_kk", "status",
        "act_type_id", "government_body_id", "created_date", "discussion_end_date",
        "comments_total", "likes_count", "dislikes_count",
    }


def test_crawl_queue_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("crawl_queue")}
    assert columns == {
        "url", "page_type", "section", "status", "attempts", "last_error",
        "discovered_at", "processed_at",
    }


def test_government_bodies_and_act_types_tables_have_expected_columns(db_session):
    gb_columns = {col["name"] for col in inspect(db_session.bind).get_columns("government_bodies")}
    at_columns = {col["name"] for col in inspect(db_session.bind).get_columns("act_types")}
    assert gb_columns == {"id", "name"}
    assert at_columns == {"id", "name"}


def test_document_versions_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("document_versions")}
    assert columns == {
        "id", "legal_act_id", "external_id", "version_number", "title_ru",
        "status", "act_type_id", "government_body_id", "created_date",
        "discussion_end_date", "raw_html_ru", "first_seen_at",
    }


def test_reports_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("reports")}
    assert columns == {"id", "legal_act_id", "raw_html_ru", "first_seen_at"}


def test_migration_creates_category_tables(pg_engine):
    tables = set(inspect(pg_engine).get_table_names())
    assert {"categories", "legal_act_categories"}.issubset(tables)


def test_categories_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("categories")}
    assert columns == {"id", "external_id", "name"}


def test_legal_act_categories_table_has_expected_columns(db_session):
    columns = {col["name"] for col in inspect(db_session.bind).get_columns("legal_act_categories")}
    assert columns == {"id", "legal_act_id", "category_id", "first_seen_at"}
