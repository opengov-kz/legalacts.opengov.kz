import sqlite3

from scraper import db, queue


def _connect():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


def test_enqueue_then_next_pending_returns_url():
    conn = _connect()
    queue.enqueue(conn, "https://example.test/list", "list", "2026-09-15T00:00:00")
    assert queue.next_pending(conn, "list") == "https://example.test/list"
    assert queue.next_pending(conn, "document") is None


def test_enqueue_is_idempotent_for_same_url():
    conn = _connect()
    queue.enqueue(conn, "https://example.test/list", "list", "t1")
    queue.enqueue(conn, "https://example.test/list", "list", "t2")
    count = conn.execute("SELECT COUNT(*) AS n FROM crawl_queue").fetchone()["n"]
    assert count == 1


def test_mark_done_removes_url_from_pending():
    conn = _connect()
    queue.enqueue(conn, "https://example.test/list", "list", "t1")
    queue.mark_done(conn, "https://example.test/list", "t2")
    assert queue.next_pending(conn, "list") is None
    row = conn.execute(
        "SELECT status, processed_at, attempts FROM crawl_queue WHERE url = ?",
        ("https://example.test/list",),
    ).fetchone()
    assert row["status"] == "done"
    assert row["processed_at"] == "t2"
    assert row["attempts"] == 1


def test_mark_error_records_message_and_keeps_out_of_pending():
    conn = _connect()
    queue.enqueue(conn, "https://example.test/list", "list", "t1")
    queue.mark_error(conn, "https://example.test/list", "timeout", "t2")
    assert queue.next_pending(conn, "list") is None
    row = conn.execute(
        "SELECT status, last_error FROM crawl_queue WHERE url = ?",
        ("https://example.test/list",),
    ).fetchone()
    assert row["status"] == "error"
    assert row["last_error"] == "timeout"


def test_enqueue_stores_section_and_section_for_reads_it_back():
    conn = _connect()
    queue.enqueue(conn, "https://example.test/npa/view?id=1", "document", "t1", section="arv")
    assert queue.section_for(conn, "https://example.test/npa/view?id=1") == "arv"


def test_section_for_returns_none_for_unknown_url():
    conn = _connect()
    assert queue.section_for(conn, "https://example.test/missing") is None


def test_requeue_stale_documents_resets_old_done_documents_only():
    conn = _connect()
    queue.enqueue(conn, "https://example.test/doc-old", "document", "t0")
    queue.enqueue(conn, "https://example.test/doc-new", "document", "t0")
    queue.enqueue(conn, "https://example.test/list", "list", "t0")
    queue.mark_done(conn, "https://example.test/doc-old", "2026-09-01T00:00:00")
    queue.mark_done(conn, "https://example.test/doc-new", "2026-09-14T00:00:00")
    queue.mark_done(conn, "https://example.test/list", "2026-09-01T00:00:00")

    queue.requeue_stale_documents(conn, "2026-09-10T00:00:00")

    assert queue.next_pending(conn, "document") == "https://example.test/doc-old"
    row_new = conn.execute(
        "SELECT status FROM crawl_queue WHERE url = ?",
        ("https://example.test/doc-new",),
    ).fetchone()
    assert row_new["status"] == "done"
    row_list = conn.execute(
        "SELECT status FROM crawl_queue WHERE url = ?",
        ("https://example.test/list",),
    ).fetchone()
    assert row_list["status"] == "done"
