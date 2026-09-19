from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import TIMESTAMP, func, select
from sqlalchemy.orm import Session

from app.deps import get_db, require_api_key
from app.schemas.analytics import AnalyticsSummaryOut, SectionCount, StatusCount, TimeseriesPoint
from db.models import Comment, Document

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(require_api_key)])


@router.get("/summary", response_model=AnalyticsSummaryOut)
def analytics_summary(db: Session = Depends(get_db)):
    by_section = db.execute(
        select(Document.section, func.count(Document.id)).group_by(Document.section)
    ).all()
    by_status = db.execute(
        select(Document.status, func.count(Document.id)).group_by(Document.status)
    ).all()
    total_comments = db.execute(select(func.count(Comment.id))).scalar_one()

    return AnalyticsSummaryOut(
        documents_by_section=[SectionCount(section=s, count=c) for s, c in by_section],
        documents_by_status=[StatusCount(status=s, count=c) for s, c in by_status],
        total_documents=sum(c for _, c in by_section),
        total_comments=total_comments,
    )


@router.get("/timeseries", response_model=list[TimeseriesPoint])
def analytics_timeseries(interval: str = "day", db: Session = Depends(get_db)):
    if interval not in {"day", "week"}:
        raise HTTPException(status_code=400, detail="interval must be 'day' or 'week'")

    bucket = func.date_trunc(interval, Document.first_seen_at.cast(TIMESTAMP(timezone=True)))
    stmt = (
        select(bucket.label("bucket"), func.count(Document.id))
        .group_by("bucket")
        .order_by("bucket")
    )
    rows = db.execute(stmt).all()
    return [TimeseriesPoint(bucket=bucket_value.isoformat(), count=count) for bucket_value, count in rows]
