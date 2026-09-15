import sqlite3

from scraper import db, store


def _connect():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


def test_upsert_document_inserts_new_row():
    conn = _connect()
    fields = {
        "title_ru": "Заголовок", "status": "Архив", "doc_type": "Приказ",
        "government_body": "Минтруда", "created_date": "09/09/2026",
        "discussion_end_date": "14/09/2026", "comments_total": 24,
        "likes_count": 0, "dislikes_count": 1, "raw_html_ru": "<html>ru</html>",
    }
    doc_id = store.upsert_document(
        conn, 15906353, "npa", "https://legalacts.egov.kz/npa/view?id=15906353",
        fields, "2026-09-15T00:00:00",
    )
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    assert row["external_id"] == 15906353
    assert row["title_ru"] == "Заголовок"
    assert row["comments_total"] == 24
    assert row["first_seen_at"] == "2026-09-15T00:00:00"
    assert row["last_checked_at"] == "2026-09-15T00:00:00"


def test_upsert_document_updates_existing_and_preserves_first_seen_at():
    conn = _connect()
    store.upsert_document(conn, 1, "npa", "url1", {"title_ru": "V1"}, "2026-09-01T00:00:00")
    store.upsert_document(conn, 1, "npa", "url1", {"title_ru": "V2"}, "2026-09-15T00:00:00")
    row = conn.execute("SELECT * FROM documents WHERE external_id = 1").fetchone()
    assert row["title_ru"] == "V2"
    assert row["first_seen_at"] == "2026-09-01T00:00:00"
    assert row["last_checked_at"] == "2026-09-15T00:00:00"


def test_upsert_document_keeps_kk_fields_when_not_provided():
    conn = _connect()
    store.upsert_document(
        conn, 1, "npa", "url1", {"title_ru": "V1", "title_kk": "KK1"}, "t1"
    )
    store.upsert_document(conn, 1, "npa", "url1", {"title_ru": "V2"}, "t2")
    row = conn.execute("SELECT * FROM documents WHERE external_id = 1").fetchone()
    assert row["title_kk"] == "KK1"


def test_upsert_comments_inserts_and_preserves_first_seen_at_on_update():
    conn = _connect()
    doc_id = store.upsert_document(conn, 1, "npa", "url1", {"title_ru": "V"}, "t0")
    comment = {
        "external_id": 100, "parent_external_id": None, "author_name": "A",
        "body": "text", "article_ref": None, "status": "rejected",
        "commented_at_raw": "10/09 - 11:05",
    }
    store.upsert_comments(conn, doc_id, [comment], "2026-09-01T00:00:00")

    updated_comment = dict(comment, status="accepted")
    store.upsert_comments(conn, doc_id, [updated_comment], "2026-09-15T00:00:00")

    row = conn.execute(
        "SELECT * FROM comments WHERE document_id = ? AND external_comment_id = 100",
        (doc_id,),
    ).fetchone()
    assert row["status"] == "accepted"
    assert row["first_seen_at"] == "2026-09-01T00:00:00"
