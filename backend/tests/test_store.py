import datetime
import hashlib

from scraper import store

UTC = datetime.timezone.utc
T1 = datetime.datetime(2026, 9, 1, tzinfo=UTC)
T2 = datetime.datetime(2026, 9, 15, tzinfo=UTC)


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


def test_upsert_legal_act_inserts_new_row_and_creates_snapshot(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 15906353, "npa_section_001",
        "https://legalacts.test/npa/view?id=15906353", _fields(), T1,
    )

    from db.models import ActType, GovernmentBody, LegalAct, LegalActSnapshot
    row = db_session.get(LegalAct, legal_act_id)

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
    assert row.first_seen_at == T1
    assert row.last_checked_at == T1

    government_body = db_session.query(GovernmentBody).filter_by(name="Body_Value_001").one()
    act_type = db_session.query(ActType).filter_by(name="DocType_Value_001").one()
    assert row.government_body_id == government_body.id
    assert row.act_type_id == act_type.id

    snapshots = db_session.query(LegalActSnapshot).filter_by(legal_act_id=legal_act_id).all()
    assert len(snapshots) == 1
    assert snapshots[0].raw_html_ru == "<html>content_ru_001</html>"
    assert snapshots[0].raw_html_kk == "<html>content_kk_001</html>"
    assert snapshots[0].content_sha256_ru == hashlib.sha256(
        "<html>content_ru_001</html>".encode("utf-8")
    ).hexdigest()
    assert snapshots[0].captured_at == T1


def test_upsert_legal_act_updates_existing_and_preserves_first_seen_at(db_session):
    store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(title_ru="V1"), T1)
    store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(title_ru="V2"), T2)

    from db.models import LegalAct
    row = db_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 1)
    ).fetchone()
    assert row.title_ru == "V2"
    assert row.first_seen_at == T1
    assert row.last_checked_at == T2


def test_upsert_legal_act_keeps_kk_fields_when_not_provided(db_session):
    store.upsert_legal_act(
        db_session, 1, "npa", "url1",
        _fields(title_ru="V1", title_kk="KK1", raw_html_kk="<html>kk1</html>"), T1,
    )
    fields_v2 = _fields(title_ru="V2")
    fields_v2.pop("title_kk")
    fields_v2.pop("raw_html_kk")
    store.upsert_legal_act(db_session, 1, "npa", "url1", fields_v2, T2)

    from db.models import LegalAct, LegalActSnapshot
    row = db_session.execute(
        LegalAct.__table__.select().where(LegalAct.external_id == 1)
    ).fetchone()
    assert row.title_kk == "KK1"

    latest_snapshot = db_session.execute(
        LegalActSnapshot.__table__.select()
        .where(LegalActSnapshot.legal_act_id == row.id)
        .order_by(LegalActSnapshot.captured_at.desc())
        .limit(1)
    ).fetchone()
    assert latest_snapshot.raw_html_kk == "<html>kk1</html>"


def test_upsert_legal_act_reuses_existing_lookup_rows_for_same_name(db_session):
    store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    store.upsert_legal_act(db_session, 2, "npa", "url2", _fields(), T1)

    from db.models import ActType, GovernmentBody
    assert db_session.query(GovernmentBody).filter_by(name="Body_Value_001").count() == 1
    assert db_session.query(ActType).filter_by(name="DocType_Value_001").count() == 1


def test_upsert_legal_act_does_not_create_new_snapshot_when_nothing_changed(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T2)

    from db.models import LegalActSnapshot
    snapshots = db_session.query(LegalActSnapshot).filter_by(legal_act_id=legal_act_id).all()
    assert len(snapshots) == 1


def test_upsert_legal_act_creates_new_snapshot_when_status_changes(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(status="A"), T1)
    store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(status="B"), T2)

    from db.models import LegalActSnapshot
    snapshots = (
        db_session.query(LegalActSnapshot)
        .filter_by(legal_act_id=legal_act_id)
        .order_by(LegalActSnapshot.captured_at)
        .all()
    )
    assert [s.status for s in snapshots] == ["A", "B"]
    assert [s.captured_at for s in snapshots] == [T1, T2]


def test_upsert_legal_act_creates_new_snapshot_when_content_hash_changes(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "url1", _fields(raw_html_ru="<html>content_ru_001</html>"), T1,
    )
    store.upsert_legal_act(
        db_session, 1, "npa", "url1", _fields(raw_html_ru="<html>content_ru_002</html>"), T2,
    )

    from db.models import LegalActSnapshot
    snapshots = (
        db_session.query(LegalActSnapshot)
        .filter_by(legal_act_id=legal_act_id)
        .order_by(LegalActSnapshot.captured_at)
        .all()
    )
    assert len(snapshots) == 2
    assert snapshots[0].content_sha256_ru != snapshots[1].content_sha256_ru


def test_upsert_comments_inserts_and_preserves_first_seen_at_on_update(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    comment = {
        "external_id": 100, "parent_external_id": None, "author_name": "A",
        "body": "text", "article_ref": None, "status": "rejected",
        "commented_at_raw": "10/09 - 11:05",
    }
    store.upsert_comments(db_session, legal_act_id, [comment], 6, T1)

    updated_comment = dict(comment, status="accepted")
    store.upsert_comments(db_session, legal_act_id, [updated_comment], 6, T2)

    from db.models import Comment
    row = db_session.execute(
        Comment.__table__.select().where(
            Comment.legal_act_id == legal_act_id, Comment.external_comment_id == 100,
            Comment.comment_channel == 6,
        )
    ).fetchone()
    assert row.status == "accepted"
    assert row.first_seen_at == T1


def test_upsert_comments_skips_comment_with_none_external_id(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    comments = [
        {"external_id": 100, "parent_external_id": None, "author_name": "A",
         "body": "text A", "article_ref": None, "status": "accepted",
         "commented_at_raw": "10/09 - 11:05"},
        {"external_id": None, "parent_external_id": None, "author_name": "B",
         "body": "text with no id", "article_ref": None, "status": None,
         "commented_at_raw": None},
        {"external_id": 101, "parent_external_id": None, "author_name": "C",
         "body": "text C", "article_ref": None, "status": "rejected",
         "commented_at_raw": "11/09 - 12:00"},
    ]

    store.upsert_comments(db_session, legal_act_id, comments, 6, T1)

    from db.models import Comment
    rows = db_session.execute(
        Comment.__table__.select()
        .where(Comment.legal_act_id == legal_act_id)
        .order_by(Comment.external_comment_id)
    ).fetchall()
    assert [row.external_comment_id for row in rows] == [100, 101]


def test_upsert_comments_same_external_id_different_channel_creates_separate_rows(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    comment = {
        "external_id": 100, "parent_external_id": None, "author_name": "A",
        "body": "public comment", "article_ref": None, "status": None,
        "commented_at_raw": "10/09 - 11:05",
    }
    expert_comment = dict(comment, body="expert comment")

    store.upsert_comments(db_session, legal_act_id, [comment], 6, T1)
    store.upsert_comments(db_session, legal_act_id, [expert_comment], 8, T1)

    from db.models import Comment
    rows = db_session.execute(
        Comment.__table__.select()
        .where(Comment.legal_act_id == legal_act_id, Comment.external_comment_id == 100)
        .order_by(Comment.comment_channel)
    ).fetchall()
    assert [(r.comment_channel, r.body) for r in rows] == [(6, "public comment"), (8, "expert comment")]


def test_document_version_exists_returns_false_before_insert_and_true_after(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    assert store.document_version_exists(db_session, 200) is False

    store.upsert_document_version(
        db_session, legal_act_id, 200,
        {"title": "V1 title", "status": None, "doc_type": "Решение",
         "government_body": "Body A", "created_date": "01/01/2020",
         "discussion_end_date": "01/02/2020", "raw_html_ru": "<html>v1</html>"},
        1, T1,
    )
    assert store.document_version_exists(db_session, 200) is True


def test_upsert_document_version_stores_fields_and_reuses_lookup_rows(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)

    store.upsert_document_version(
        db_session, legal_act_id, 200,
        {"title": "V1 title", "status": None, "doc_type": "DocType_Value_001",
         "government_body": "Body_Value_001", "created_date": "01/01/2020",
         "discussion_end_date": "01/02/2020", "raw_html_ru": "<html>v1</html>"},
        1, T1,
    )

    from db.models import ActType, DocumentVersion, GovernmentBody
    row = db_session.query(DocumentVersion).filter_by(external_id=200).one()
    assert row.legal_act_id == legal_act_id
    assert row.version_number == 1
    assert row.title_ru == "V1 title"
    assert row.status is None
    assert row.created_date == "01/01/2020"
    assert row.discussion_end_date == "01/02/2020"
    assert row.raw_html_ru == "<html>v1</html>"
    assert row.first_seen_at == T1

    # _fields() (used to create the parent legal act) already created these
    # lookup rows with the same names — must be reused, not duplicated.
    assert db_session.query(GovernmentBody).filter_by(name="Body_Value_001").count() == 1
    assert db_session.query(ActType).filter_by(name="DocType_Value_001").count() == 1


def test_report_exists_returns_false_before_insert_and_true_after(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    assert store.report_exists(db_session, legal_act_id) is False

    store.upsert_report(db_session, legal_act_id, "<html>report</html>", T1)
    assert store.report_exists(db_session, legal_act_id) is True


def test_upsert_report_stores_raw_html_and_first_seen_at(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)

    store.upsert_report(db_session, legal_act_id, "<html>report</html>", T1)

    from db.models import Report
    row = db_session.query(Report).filter_by(legal_act_id=legal_act_id).one()
    assert row.raw_html_ru == "<html>report</html>"
    assert row.first_seen_at == T1
