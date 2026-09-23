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
        government_body="Body_Value_001", created_date="01/01/2026",
        discussion_end_date="31/12/2026", comments_total=42,
        likes_count=99, dislikes_count=88,
        raw_html_ru="<html>content_ru_001</html>",
        raw_html_kk="<html>content_kk_001</html>",
    )
    base.update(overrides)
    return base


def test_base_url_matches_run_module_base_url():
    from scraper import run as run_module
    assert store.BASE_URL == run_module.BASE_URL


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
    assert row.created_date == "01/01/2026"
    assert row.discussion_end_date == "31/12/2026"
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


def test_legal_act_id_for_external_id_returns_none_before_insert_and_id_after(db_session):
    assert store.legal_act_id_for_external_id(db_session, 15906353) is None

    legal_act_id = store.upsert_legal_act(db_session, 15906353, "npa", "url1", _fields(), T1)
    assert store.legal_act_id_for_external_id(db_session, 15906353) == legal_act_id


def test_get_or_create_category_inserts_new_row(db_session):
    category = store.get_or_create_category(db_session, 346, "Информационные технологии")

    from db.models import Category
    row = db_session.get(Category, category.id)
    assert row.external_id == 346
    assert row.name == "Информационные технологии"


def test_get_or_create_category_reuses_existing_row_by_external_id(db_session):
    first = store.get_or_create_category(db_session, 346, "Информационные технологии")
    second = store.get_or_create_category(db_session, 346, "Информационные технологии")

    assert first.id == second.id
    from db.models import Category
    assert db_session.query(Category).filter_by(external_id=346).count() == 1


def test_get_or_create_category_updates_name_when_site_renamed_it(db_session):
    first = store.get_or_create_category(db_session, 346, "Старое имя")
    second = store.get_or_create_category(db_session, 346, "Новое имя")

    assert first.id == second.id
    from db.models import Category
    row = db_session.get(Category, first.id)
    assert row.name == "Новое имя"


def test_link_legal_act_category_creates_row(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    category = store.get_or_create_category(db_session, 346, "Информационные технологии")

    store.link_legal_act_category(db_session, legal_act_id, category.id, T1)

    from db.models import LegalActCategory
    row = db_session.query(LegalActCategory).filter_by(
        legal_act_id=legal_act_id, category_id=category.id,
    ).one()
    assert row.first_seen_at == T1


def test_link_legal_act_category_is_idempotent(db_session):
    legal_act_id = store.upsert_legal_act(db_session, 1, "npa", "url1", _fields(), T1)
    category = store.get_or_create_category(db_session, 346, "Информационные технологии")

    store.link_legal_act_category(db_session, legal_act_id, category.id, T1)
    store.link_legal_act_category(db_session, legal_act_id, category.id, T2)

    from db.models import LegalActCategory
    rows = db_session.query(LegalActCategory).filter_by(
        legal_act_id=legal_act_id, category_id=category.id,
    ).all()
    assert len(rows) == 1
    assert rows[0].first_seen_at == T1


def test_upsert_legal_act_records_invalid_url_event(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://not-legalacts.example/view?id=1", _fields(), T1,
    )

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="invalid_url",
    ).all()
    assert len(events) == 1
    assert events[0].field_name == "url"


def test_upsert_legal_act_does_not_record_invalid_url_event_for_real_url(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1", _fields(), T1,
    )

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="invalid_url",
    ).count() == 0


def test_upsert_legal_act_records_invalid_date_event(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(created_date="not-a-date", discussion_end_date="09/09/2026"), T1,
    )

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="invalid_date",
    ).all()
    assert len(events) == 1
    assert events[0].field_name == "created_date"


def test_upsert_legal_act_does_not_record_invalid_date_event_for_valid_dates(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(created_date="01/01/2026", discussion_end_date="09/09/2026"), T1,
    )

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="invalid_date",
    ).count() == 0


def test_upsert_legal_act_records_end_before_start_event(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(created_date="09/09/2026", discussion_end_date="01/01/2026"), T1,
    )

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="end_before_start",
    ).all()
    assert len(events) == 1
    assert events[0].field_name == "discussion_end_date"


def test_upsert_legal_act_does_not_record_end_before_start_when_dates_ordered_correctly(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(created_date="01/01/2026", discussion_end_date="09/09/2026"), T1,
    )

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="end_before_start",
    ).count() == 0


def test_upsert_legal_act_first_save_does_not_record_counter_null_flip(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=None), T1,
    )

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="counter_null_flip",
    ).count() == 0


def test_upsert_legal_act_records_counter_null_flip_value_to_null(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=42), T1,
    )
    store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=None), T2,
    )

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="counter_null_flip", field_name="comments_total",
    ).all()
    assert len(events) == 1
    assert events[0].detail == "42 -> None"


def test_upsert_legal_act_records_counter_null_flip_null_to_value(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=None), T1,
    )
    store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=42), T2,
    )

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="counter_null_flip", field_name="comments_total",
    ).all()
    assert len(events) == 1


def test_upsert_legal_act_does_not_record_counter_null_flip_when_both_are_numbers(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=42), T1,
    )
    store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=43), T2,
    )

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="counter_null_flip", field_name="comments_total",
    ).count() == 0


def test_upsert_legal_act_records_invalid_date_event_for_non_string_date(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(created_date=20260101), T1,
    )

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="invalid_date", field_name="created_date",
    ).all()
    assert len(events) == 1


def _comment(external_id, **overrides):
    base = dict(
        external_id=external_id, parent_external_id=None, author_name="A",
        body="text", article_ref=None, status=None, commented_at_raw="10/09 - 11:05",
    )
    base.update(overrides)
    return base


def test_record_comments_total_mismatch_creates_event_when_counts_differ(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=5), T1,
    )
    store.upsert_comments(db_session, legal_act_id, [_comment(100), _comment(101)], 6, T1)

    store.record_comments_total_mismatch(db_session, legal_act_id, 5, T1)

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="comments_total_mismatch",
    ).all()
    assert len(events) == 1
    assert events[0].field_name == "comments_total"
    assert events[0].detail == "source=5, collected=2"


def test_record_comments_total_mismatch_no_event_when_counts_match(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=2), T1,
    )
    store.upsert_comments(db_session, legal_act_id, [_comment(100), _comment(101)], 6, T1)

    store.record_comments_total_mismatch(db_session, legal_act_id, 2, T1)

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="comments_total_mismatch",
    ).count() == 0


def test_record_comments_total_mismatch_counts_across_all_channels(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=2), T1,
    )
    store.upsert_comments(db_session, legal_act_id, [_comment(100)], 6, T1)
    store.upsert_comments(db_session, legal_act_id, [_comment(200)], 8, T1)

    store.record_comments_total_mismatch(db_session, legal_act_id, 2, T1)

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="comments_total_mismatch",
    ).count() == 0


def test_record_comments_total_mismatch_skips_when_comments_total_is_none(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(comments_total=None), T1,
    )
    store.upsert_comments(db_session, legal_act_id, [_comment(100)], 6, T1)

    store.record_comments_total_mismatch(db_session, legal_act_id, None, T1)

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="comments_total_mismatch",
    ).count() == 0


def test_upsert_legal_act_records_new_status_event(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(status="Совершенно новый статус XYZ"), T1,
    )

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="new_status",
    ).all()
    assert len(events) == 1
    assert events[0].detail == "Совершенно новый статус XYZ"


def test_upsert_legal_act_does_not_record_new_status_event_for_known_status(db_session):
    store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1",
        _fields(status="Status_Value_001"), T1,
    )
    legal_act_id_2 = store.upsert_legal_act(
        db_session, 2, "npa", "https://legalacts.egov.kz/npa/view?id=2",
        _fields(status="Status_Value_001"), T1,
    )

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id_2, event_type="new_status",
    ).count() == 0


def test_record_list_total_pages_change_first_call_creates_baseline_no_event(db_session):
    store.record_list_total_pages_change(db_session, "https://legalacts.egov.kz/list", 100, T1)

    from db.models import ListPageTotal, QualityEvent
    row = db_session.query(ListPageTotal).filter_by(url="https://legalacts.egov.kz/list").one()
    assert row.total_pages == 100
    assert db_session.query(QualityEvent).filter_by(event_type="list_total_pages_decreased").count() == 0


def test_record_list_total_pages_change_decrease_creates_event(db_session):
    store.record_list_total_pages_change(db_session, "https://legalacts.egov.kz/list", 100, T1)
    store.record_list_total_pages_change(db_session, "https://legalacts.egov.kz/list", 80, T2)

    from db.models import ListPageTotal, QualityEvent
    events = db_session.query(QualityEvent).filter_by(event_type="list_total_pages_decreased").all()
    assert len(events) == 1
    assert events[0].legal_act_id is None
    assert events[0].detail == "https://legalacts.egov.kz/list: 100 -> 80"

    row = db_session.query(ListPageTotal).filter_by(url="https://legalacts.egov.kz/list").one()
    assert row.total_pages == 80


def test_record_list_total_pages_change_increase_no_event(db_session):
    store.record_list_total_pages_change(db_session, "https://legalacts.egov.kz/list", 100, T1)
    store.record_list_total_pages_change(db_session, "https://legalacts.egov.kz/list", 150, T2)

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(event_type="list_total_pages_decreased").count() == 0

    from db.models import ListPageTotal
    row = db_session.query(ListPageTotal).filter_by(url="https://legalacts.egov.kz/list").one()
    assert row.total_pages == 150
    assert row.updated_at == T2


def test_record_list_total_pages_change_equal_no_event(db_session):
    store.record_list_total_pages_change(db_session, "https://legalacts.egov.kz/list", 100, T1)
    store.record_list_total_pages_change(db_session, "https://legalacts.egov.kz/list", 100, T2)

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(event_type="list_total_pages_decreased").count() == 0

    from db.models import ListPageTotal
    row = db_session.query(ListPageTotal).filter_by(url="https://legalacts.egov.kz/list").one()
    assert row.total_pages == 100
    assert row.updated_at == T2


def test_record_unrecognized_html_structure_creates_event_when_not_recognized(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1", _fields(), T1,
    )

    store.record_unrecognized_html_structure(db_session, legal_act_id, False, T1)

    from db.models import QualityEvent
    events = db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="unrecognized_html_structure",
    ).all()
    assert len(events) == 1


def test_record_unrecognized_html_structure_no_event_when_recognized(db_session):
    legal_act_id = store.upsert_legal_act(
        db_session, 1, "npa", "https://legalacts.egov.kz/npa/view?id=1", _fields(), T1,
    )

    store.record_unrecognized_html_structure(db_session, legal_act_id, True, T1)

    from db.models import QualityEvent
    assert db_session.query(QualityEvent).filter_by(
        legal_act_id=legal_act_id, event_type="unrecognized_html_structure",
    ).count() == 0
