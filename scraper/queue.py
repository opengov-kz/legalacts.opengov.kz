def enqueue(conn, url, page_type, discovered_at, section=None):
    conn.execute(
        "INSERT OR IGNORE INTO crawl_queue (url, page_type, section, status, attempts, discovered_at) "
        "VALUES (?, ?, ?, 'pending', 0, ?)",
        (url, page_type, section, discovered_at),
    )
    conn.commit()


def next_pending(conn, page_type):
    row = conn.execute(
        "SELECT url FROM crawl_queue WHERE page_type = ? AND status = 'pending' "
        "ORDER BY discovered_at LIMIT 1",
        (page_type,),
    ).fetchone()
    return row["url"] if row else None


def section_for(conn, url):
    row = conn.execute(
        "SELECT section FROM crawl_queue WHERE url = ?", (url,)
    ).fetchone()
    return row["section"] if row else None


def mark_done(conn, url, processed_at):
    conn.execute(
        "UPDATE crawl_queue SET status = 'done', processed_at = ?, attempts = attempts + 1 "
        "WHERE url = ?",
        (processed_at, url),
    )
    conn.commit()


def mark_error(conn, url, error_message, processed_at):
    conn.execute(
        "UPDATE crawl_queue SET status = 'error', last_error = ?, processed_at = ?, "
        "attempts = attempts + 1 WHERE url = ?",
        (error_message, processed_at, url),
    )
    conn.commit()


def requeue_stale_documents(conn, older_than_iso):
    conn.execute(
        "UPDATE crawl_queue SET status = 'pending' WHERE page_type = 'document' "
        "AND status = 'done' AND processed_at < ?",
        (older_than_iso,),
    )
    conn.commit()


def requeue_stale_lists(conn, older_than_iso):
    conn.execute(
        "UPDATE crawl_queue SET status = 'pending' WHERE page_type = 'list' "
        "AND status = 'done' AND processed_at < ?",
        (older_than_iso,),
    )
    conn.commit()
