from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from app.deps import get_db, require_api_key
from app.schemas.documents import DocumentDetailOut, DocumentListItemOut
from db.models import Document

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(require_api_key)])

PAGE_SIZE = 20


@router.get("", response_model=list[DocumentListItemOut])
def list_documents(
    section: Optional[str] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
):
    stmt = select(Document).options(defer(Document.raw_html_ru), defer(Document.raw_html_kk))
    if section is not None:
        stmt = stmt.where(Document.section == section)
    if status_filter is not None:
        stmt = stmt.where(Document.status == status_filter)
    stmt = stmt.order_by(Document.id).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    return db.execute(stmt).scalars().all()


@router.get("/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: int, db: Session = Depends(get_db)):
    document = db.execute(
        select(Document)
        .where(Document.id == document_id)
        .options(defer(Document.raw_html_ru), defer(Document.raw_html_kk))
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document
