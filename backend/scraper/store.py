from sqlalchemy import select

from db.models import Comment, Document

DOCUMENT_FIELD_ORDER = [
    "section", "url", "title_ru", "title_kk", "status", "doc_type",
    "government_body", "created_date", "discussion_end_date",
    "comments_total", "likes_count", "dislikes_count", "raw_html_ru",
    "raw_html_kk",
]


def upsert_document(session, external_id, section, url, fields, now):
    existing = session.execute(
        select(Document).where(Document.external_id == external_id)
    ).scalar_one_or_none()

    title_kk = fields.get("title_kk") or (existing.title_kk if existing else None)
    raw_html_kk = fields.get("raw_html_kk") or (
        existing.raw_html_kk if existing else None
    )

    values = {
        "section": section,
        "url": url,
        "title_ru": fields.get("title_ru"),
        "title_kk": title_kk,
        "status": fields.get("status"),
        "doc_type": fields.get("doc_type"),
        "government_body": fields.get("government_body"),
        "created_date": fields.get("created_date"),
        "discussion_end_date": fields.get("discussion_end_date"),
        "comments_total": fields.get("comments_total"),
        "likes_count": fields.get("likes_count"),
        "dislikes_count": fields.get("dislikes_count"),
        "raw_html_ru": fields.get("raw_html_ru"),
        "raw_html_kk": raw_html_kk,
    }

    if existing is None:
        document = Document(
            external_id=external_id, first_seen_at=now, last_checked_at=now, **values,
        )
        session.add(document)
        session.commit()
        return document.id

    for key, value in values.items():
        setattr(existing, key, value)
    existing.last_checked_at = now
    session.commit()
    return existing.id


def upsert_comments(session, document_id, comments, now):
    for comment in comments:
        if comment["external_id"] is None:
            continue

        existing = session.execute(
            select(Comment).where(
                Comment.document_id == document_id,
                Comment.external_comment_id == comment["external_id"],
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(Comment(
                document_id=document_id,
                external_comment_id=comment["external_id"],
                parent_external_comment_id=comment["parent_external_id"],
                author_name=comment["author_name"],
                body=comment["body"],
                article_ref=comment["article_ref"],
                status=comment["status"],
                commented_at_raw=comment["commented_at_raw"],
                first_seen_at=now,
            ))
        else:
            existing.parent_external_comment_id = comment["parent_external_id"]
            existing.author_name = comment["author_name"]
            existing.body = comment["body"]
            existing.article_ref = comment["article_ref"]
            existing.status = comment["status"]
            existing.commented_at_raw = comment["commented_at_raw"]

    session.commit()
