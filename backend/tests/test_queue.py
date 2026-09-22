import datetime

from scraper import queue

UTC = datetime.timezone.utc


def test_enqueue_then_next_pending_returns_url(db_session):
    queue.enqueue(db_session, "https://example.test/list", "list", datetime.datetime(2026, 9, 15, tzinfo=UTC))
    assert queue.next_pending(db_session, "list") == "https://example.test/list"
    assert queue.next_pending(db_session, "document") is None


def test_enqueue_is_idempotent_for_same_url(db_session):
    queue.enqueue(db_session, "https://example.test/list", "list", datetime.datetime(2026, 9, 15, tzinfo=UTC))
    queue.enqueue(db_session, "https://example.test/list", "list", datetime.datetime(2026, 9, 15, 0, 5, tzinfo=UTC))
    from db.models import CrawlQueueEntry
    count = db_session.query(CrawlQueueEntry).count()
    assert count == 1


def test_mark_done_removes_url_from_pending(db_session):
    queue.enqueue(db_session, "https://example.test/list", "list", datetime.datetime(2026, 9, 15, tzinfo=UTC))
    queue.mark_done(db_session, "https://example.test/list", datetime.datetime(2026, 9, 15, 0, 5, tzinfo=UTC))
    assert queue.next_pending(db_session, "list") is None

    from db.models import CrawlQueueEntry
    row = db_session.get(CrawlQueueEntry, "https://example.test/list")
    assert row.status == "done"
    assert row.processed_at == datetime.datetime(2026, 9, 15, 0, 5, tzinfo=UTC)
    assert row.attempts == 1


def test_mark_error_records_message_and_keeps_out_of_pending(db_session):
    queue.enqueue(db_session, "https://example.test/list", "list", datetime.datetime(2026, 9, 15, tzinfo=UTC))
    queue.mark_error(db_session, "https://example.test/list", "timeout", datetime.datetime(2026, 9, 15, 0, 5, tzinfo=UTC))
    assert queue.next_pending(db_session, "list") is None

    from db.models import CrawlQueueEntry
    row = db_session.get(CrawlQueueEntry, "https://example.test/list")
    assert row.status == "error"
    assert row.last_error == "timeout"


def test_enqueue_stores_section_and_section_for_reads_it_back(db_session):
    queue.enqueue(
        db_session, "https://example.test/npa/view?id=1", "document",
        datetime.datetime(2026, 9, 15, tzinfo=UTC), section="arv",
    )
    assert queue.section_for(db_session, "https://example.test/npa/view?id=1") == "arv"


def test_section_for_returns_none_for_unknown_url(db_session):
    assert queue.section_for(db_session, "https://example.test/missing") is None


def test_requeue_stale_documents_resets_old_done_documents_only(db_session):
    queue.enqueue(db_session, "https://example.test/doc-old", "document", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.enqueue(db_session, "https://example.test/doc-new", "document", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.enqueue(db_session, "https://example.test/list", "list", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.mark_done(db_session, "https://example.test/doc-old", datetime.datetime(2026, 9, 1, tzinfo=UTC))
    queue.mark_done(db_session, "https://example.test/doc-new", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.mark_done(db_session, "https://example.test/list", datetime.datetime(2026, 9, 1, tzinfo=UTC))

    queue.requeue_stale_documents(db_session, datetime.datetime(2026, 9, 10, tzinfo=UTC))

    assert queue.next_pending(db_session, "document") == "https://example.test/doc-old"

    from db.models import CrawlQueueEntry
    assert db_session.get(CrawlQueueEntry, "https://example.test/doc-new").status == "done"
    assert db_session.get(CrawlQueueEntry, "https://example.test/list").status == "done"


def test_requeue_stale_lists_resets_old_done_lists_only(db_session):
    queue.enqueue(db_session, "https://example.test/list-old", "list", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.enqueue(db_session, "https://example.test/list-new", "list", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.enqueue(db_session, "https://example.test/doc", "document", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.mark_done(db_session, "https://example.test/list-old", datetime.datetime(2026, 9, 1, tzinfo=UTC))
    queue.mark_done(db_session, "https://example.test/list-new", datetime.datetime(2026, 9, 14, tzinfo=UTC))
    queue.mark_done(db_session, "https://example.test/doc", datetime.datetime(2026, 9, 1, tzinfo=UTC))

    queue.requeue_stale_lists(db_session, datetime.datetime(2026, 9, 10, tzinfo=UTC))

    assert queue.next_pending(db_session, "list") == "https://example.test/list-old"

    from db.models import CrawlQueueEntry
    assert db_session.get(CrawlQueueEntry, "https://example.test/list-new").status == "done"
    assert db_session.get(CrawlQueueEntry, "https://example.test/doc").status == "done"
