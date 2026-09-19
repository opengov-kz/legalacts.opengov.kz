from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import get_db, require_api_key
from app.schemas.crawl import CrawlErrorOut, CrawlStatusCountOut, CrawlStatusOut
from db.models import CrawlQueueEntry

router = APIRouter(prefix="/crawl", tags=["crawl"], dependencies=[Depends(require_api_key)])

ERROR_LIMIT = 20


@router.get("/status", response_model=CrawlStatusOut)
def crawl_status(db: Session = Depends(get_db)):
    counts = db.execute(
        select(CrawlQueueEntry.page_type, CrawlQueueEntry.status, func.count(CrawlQueueEntry.url))
        .group_by(CrawlQueueEntry.page_type, CrawlQueueEntry.status)
    ).all()
    last_processed_at = db.execute(select(func.max(CrawlQueueEntry.processed_at))).scalar_one()
    errors = db.execute(
        select(CrawlQueueEntry)
        .where(CrawlQueueEntry.status == "error")
        .order_by(CrawlQueueEntry.processed_at.desc())
        .limit(ERROR_LIMIT)
    ).scalars().all()

    return CrawlStatusOut(
        counts=[CrawlStatusCountOut(page_type=pt, status=st, count=c) for pt, st, c in counts],
        last_processed_at=last_processed_at,
        recent_errors=[
            CrawlErrorOut(url=e.url, page_type=e.page_type, last_error=e.last_error, processed_at=e.processed_at)
            for e in errors
        ],
    )
