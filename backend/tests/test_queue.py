from scraper import queue


def test_enqueue_then_next_pending_returns_url(db_session):
    queue.enqueue(db_session, "https://example.test/list", "list", "2026-09-15T00:00:00+00:00")
    assert queue.next_pending(db_session, "list") == "https://example.test/list"
    assert queue.next_pending(db_session, "document") is None


def test_enqueue_is_idempotent_for_same_url(db_session):
    queue.enqueue(db_session, "https://example.test/list", "list", "2026-09-15T00:00:00+00:00")
    queue.enqueue(db_session, "https://example.test/list", "list", "2026-09-15T00:05:00+00:00")
    from db.models import CrawlQueueEntry
    count = db_session.query(CrawlQueueEntry).count()
    assert count == 1


def test_mark_done_removes_url_from_pending(db_session):
    queue.enqueue(db_session, "https://example.test/list", "list", "2026-09-15T00:00:00+00:00")
    queue.mark_done(db_session, "https://example.test/list", "2026-09-15T00:05:00+00:00")
    assert queue.next_pending(db_session, "list") is None

    from db.models import CrawlQueueEntry
    row = db_session.get(CrawlQueueEntry, "https://example.test/list")
    assert row.status == "done"
    assert row.processed_at == "2026-09-15T00:05:00+00:00"
    assert row.attempts == 1


def test_mark_error_records_message_and_keeps_out_of_pending(db_session):
    queue.enqueue(db_session, "https://example.test/list", "list", "2026-09-15T00:00:00+00:00")
    queue.mark_error(db_session, "https://example.test/list", "timeout", "2026-09-15T00:05:00+00:00")
    assert queue.next_pending(db_session, "list") is None

    from db.models import CrawlQueueEntry
    row = db_session.get(CrawlQueueEntry, "https://example.test/list")
    assert row.status == "error"
    assert row.last_error == "timeout"


def test_enqueue_stores_section_and_section_for_reads_it_back(db_session):
    queue.enqueue(
        db_session, "https://example.test/npa/view?id=1", "document",
        "2026-09-15T00:00:00+00:00", section="arv",
    )
    assert queue.section_for(db_session, "https://example.test/npa/view?id=1") == "arv"


def test_section_for_returns_none_for_unknown_url(db_session):
    assert queue.section_for(db_session, "https://example.test/missing") is None


def test_requeue_stale_documents_resets_old_done_documents_only(db_session):
    queue.enqueue(db_session, "https://example.test/doc-old", "document", "2026-09-14T00:00:00+00:00")
    queue.enqueue(db_session, "https://example.test/doc-new", "document", "2026-09-14T00:00:00+00:00")
    queue.enqueue(db_session, "https://example.test/list", "list", "2026-09-14T00:00:00+00:00")
    queue.mark_done(db_session, "https://example.test/doc-old", "2026-09-01T00:00:00+00:00")
    queue.mark_done(db_session, "https://example.test/doc-new", "2026-09-14T00:00:00+00:00")
    queue.mark_done(db_session, "https://example.test/list", "2026-09-01T00:00:00+00:00")

    queue.requeue_stale_documents(db_session, "2026-09-10T00:00:00+00:00")

    assert queue.next_pending(db_session, "document") == "https://example.test/doc-old"

    from db.models import CrawlQueueEntry
    assert db_session.get(CrawlQueueEntry, "https://example.test/doc-new").status == "done"
    assert db_session.get(CrawlQueueEntry, "https://example.test/list").status == "done"


def test_requeue_stale_lists_resets_old_done_lists_only(db_session):
    queue.enqueue(db_session, "https://example.test/list-old", "list", "2026-09-14T00:00:00+00:00")
    queue.enqueue(db_session, "https://example.test/list-new", "list", "2026-09-14T00:00:00+00:00")
    queue.enqueue(db_session, "https://example.test/doc", "document", "2026-09-14T00:00:00+00:00")
    queue.mark_done(db_session, "https://example.test/list-old", "2026-09-01T00:00:00+00:00")
    queue.mark_done(db_session, "https://example.test/list-new", "2026-09-14T00:00:00+00:00")
    queue.mark_done(db_session, "https://example.test/doc", "2026-09-01T00:00:00+00:00")

    queue.requeue_stale_lists(db_session, "2026-09-10T00:00:00+00:00")

    assert queue.next_pending(db_session, "list") == "https://example.test/list-old"

    from db.models import CrawlQueueEntry
    assert db_session.get(CrawlQueueEntry, "https://example.test/list-new").status == "done"
    assert db_session.get(CrawlQueueEntry, "https://example.test/doc").status == "done"
