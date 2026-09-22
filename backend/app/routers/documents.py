from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.deps import get_db, require_api_key
from app.schemas.documents import DocumentDetailOut, DocumentListItemOut
from db.models import LegalAct

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(require_api_key)])

PAGE_SIZE = 20


@router.get("", response_model=list[DocumentListItemOut])
def list_documents(
    section: Optional[str] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    db: Session = Depends(get_db),
):
    stmt = select(LegalAct).options(
        joinedload(LegalAct.government_body_ref), joinedload(LegalAct.act_type_ref)
    )
    if section is not None:
        stmt = stmt.where(LegalAct.section == section)
    if status_filter is not None:
        stmt = stmt.where(LegalAct.status == status_filter)
    stmt = stmt.order_by(LegalAct.id).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    return db.execute(stmt).scalars().all()


@router.get("/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: int, db: Session = Depends(get_db)):
    legal_act = db.execute(
        select(LegalAct)
        .where(LegalAct.id == document_id)
        .options(joinedload(LegalAct.government_body_ref), joinedload(LegalAct.act_type_ref))
    ).scalar_one_or_none()
    if legal_act is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return legal_act
