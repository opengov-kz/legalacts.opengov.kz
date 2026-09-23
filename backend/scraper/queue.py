from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.models import CrawlQueueEntry


def enqueue(session, url, page_type, discovered_at, section=None):
    stmt = (
        pg_insert(CrawlQueueEntry)
        .values(
            url=url, page_type=page_type, section=section,
            status="pending", attempts=0, discovered_at=discovered_at,
        )
        .on_conflict_do_nothing(index_elements=["url"])
    )
    session.execute(stmt)
    session.commit()


def next_pending(session, page_type):
    stmt = (
        select(CrawlQueueEntry.url)
        .where(CrawlQueueEntry.page_type == page_type, CrawlQueueEntry.status == "pending")
        .order_by(CrawlQueueEntry.discovered_at)
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none()


def any_exist(session, page_type):
    stmt = select(CrawlQueueEntry.url).where(CrawlQueueEntry.page_type == page_type).limit(1)
    return session.execute(stmt).scalar_one_or_none() is not None


def section_for(session, url):
    stmt = select(CrawlQueueEntry.section).where(CrawlQueueEntry.url == url)
    return session.execute(stmt).scalar_one_or_none()


def mark_done(session, url, processed_at):
    entry = session.get(CrawlQueueEntry, url)
    entry.status = "done"
    entry.processed_at = processed_at
    entry.attempts += 1
    session.commit()


def mark_error(session, url, error_message, processed_at):
    entry = session.get(CrawlQueueEntry, url)
    entry.status = "error"
    entry.last_error = error_message
    entry.processed_at = processed_at
    entry.attempts += 1
    session.commit()


def requeue_stale_documents(session, older_than_iso):
    session.execute(
        update(CrawlQueueEntry)
        .where(
            CrawlQueueEntry.page_type == "document",
            CrawlQueueEntry.status == "done",
            CrawlQueueEntry.processed_at < older_than_iso,
        )
        .values(status="pending")
    )
    session.commit()


def requeue_stale_lists(session, older_than_iso):
    session.execute(
        update(CrawlQueueEntry)
        .where(
            CrawlQueueEntry.page_type.in_(["list", "category_list"]),
            CrawlQueueEntry.status == "done",
            CrawlQueueEntry.processed_at < older_than_iso,
        )
        .values(status="pending")
    )
    session.commit()
