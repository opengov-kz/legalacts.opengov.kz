from scraper import store


def test_upsert_document_inserts_new_row(db_session):
    fields = {
        "title_ru": "Title_RU_001", "title_kk": "Title_KK_001",
        "status": "Status_Value_001", "doc_type": "DocType_Value_001",
        "government_body": "Body_Value_001", "created_date": "2026-01-01",
        "discussion_end_date": "2026-12-31", "comments_total": 42,
        "likes_count": 99, "dislikes_count": 88,
        "raw_html_ru": "<html>content_ru_001</html>",
        "raw_html_kk": "<html>content_kk_001</html>",
    }
    doc_id = store.upsert_document(
        db_session, 15906353, "npa_section_001",
        "https://legalacts.test/npa/view?id=15906353", fields,
        "2026-09-15T00:00:00+00:00",
    )

    from db.models import Document
    row = db_session.get(Document, doc_id)

    assert row.external_id == 15906353
    assert row.section == "npa_section_001"
    assert row.url == "https://legalacts.test/npa/view?id=15906353"
    assert row.title_ru == "Title_RU_001"
    assert row.title_kk == "Title_KK_001"
    assert row.status == "Status_Value_001"
    assert row.doc_type == "DocType_Value_001"
    assert row.government_body == "Body_Value_001"
    assert row.created_date == "2026-01-01"
    assert row.discussion_end_date == "2026-12-31"
    assert row.comments_total == 42
    assert row.likes_count == 99
    assert row.dislikes_count == 88
    assert row.raw_html_ru == "<html>content_ru_001</html>"
    assert row.raw_html_kk == "<html>content_kk_001</html>"
    assert row.first_seen_at == "2026-09-15T00:00:00+00:00"
    assert row.last_checked_at == "2026-09-15T00:00:00+00:00"


def test_upsert_document_updates_existing_and_preserves_first_seen_at(db_session):
    store.upsert_document(db_session, 1, "npa", "url1", {"title_ru": "V1"}, "2026-09-01T00:00:00+00:00")
    store.upsert_document(db_session, 1, "npa", "url1", {"title_ru": "V2"}, "2026-09-15T00:00:00+00:00")

    from db.models import Document
    row = db_session.execute(
        Document.__table__.select().where(Document.external_id == 1)
    ).fetchone()
    assert row.title_ru == "V2"
    assert row.first_seen_at == "2026-09-01T00:00:00+00:00"
    assert row.last_checked_at == "2026-09-15T00:00:00+00:00"


def test_upsert_document_keeps_kk_fields_when_not_provided(db_session):
    store.upsert_document(
        db_session, 1, "npa", "url1", {"title_ru": "V1", "title_kk": "KK1"},
        "2026-09-01T00:00:00+00:00",
    )
    store.upsert_document(db_session, 1, "npa", "url1", {"title_ru": "V2"}, "2026-09-15T00:00:00+00:00")

    from db.models import Document
    row = db_session.execute(
        Document.__table__.select().where(Document.external_id == 1)
    ).fetchone()
    assert row.title_kk == "KK1"


def test_upsert_comments_inserts_and_preserves_first_seen_at_on_update(db_session):
    doc_id = store.upsert_document(db_session, 1, "npa", "url1", {"title_ru": "V"}, "2026-09-01T00:00:00+00:00")
    comment = {
        "external_id": 100, "parent_external_id": None, "author_name": "A",
        "body": "text", "article_ref": None, "status": "rejected",
        "commented_at_raw": "10/09 - 11:05",
    }
    store.upsert_comments(db_session, doc_id, [comment], "2026-09-01T00:00:00+00:00")

    updated_comment = dict(comment, status="accepted")
    store.upsert_comments(db_session, doc_id, [updated_comment], "2026-09-15T00:00:00+00:00")

    from db.models import Comment
    row = db_session.execute(
        Comment.__table__.select().where(
            Comment.document_id == doc_id, Comment.external_comment_id == 100
        )
    ).fetchone()
    assert row.status == "accepted"
    assert row.first_seen_at == "2026-09-01T00:00:00+00:00"


def test_upsert_comments_skips_comment_with_none_external_id(db_session):
    doc_id = store.upsert_document(db_session, 1, "npa", "url1", {"title_ru": "V"}, "2026-09-01T00:00:00+00:00")
    comments = [
        {
            "external_id": 100, "parent_external_id": None, "author_name": "A",
            "body": "text A", "article_ref": None, "status": "accepted",
            "commented_at_raw": "10/09 - 11:05",
        },
        {
            "external_id": None, "parent_external_id": None, "author_name": "B",
            "body": "text with no id", "article_ref": None, "status": None,
            "commented_at_raw": None,
        },
        {
            "external_id": 101, "parent_external_id": None, "author_name": "C",
            "body": "text C", "article_ref": None, "status": "rejected",
            "commented_at_raw": "11/09 - 12:00",
        },
    ]

    store.upsert_comments(db_session, doc_id, comments, "2026-09-01T00:00:00+00:00")

    from db.models import Comment
    rows = db_session.execute(
        Comment.__table__.select()
        .where(Comment.document_id == doc_id)
        .order_by(Comment.external_comment_id)
    ).fetchall()
    assert [row.external_comment_id for row in rows] == [100, 101]
