import hashlib

from sqlalchemy import select

from db.models import (
    ActType, Category, Comment, DocumentVersion, GovernmentBody, LegalAct,
    LegalActCategory, LegalActSnapshot, Report,
)

SNAPSHOT_TRIGGER_FIELDS = (
    "status", "discussion_end_date", "comments_total", "likes_count",
    "dislikes_count", "content_sha256_ru", "content_sha256_kk",
)


def _sha256(text):
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _get_or_create(session, model, name):
    if not name:
        return None
    existing = session.execute(select(model).where(model.name == name)).scalar_one_or_none()
    if existing is not None:
        return existing
    obj = model(name=name)
    session.add(obj)
    session.flush()
    return obj


def upsert_legal_act(session, external_id, section, url, fields, now):
    existing = session.execute(
        select(LegalAct).where(LegalAct.external_id == external_id)
    ).scalar_one_or_none()

    previous_snapshot = None
    if existing is not None:
        previous_snapshot = session.execute(
            select(LegalActSnapshot)
            .where(LegalActSnapshot.legal_act_id == existing.id)
            .order_by(LegalActSnapshot.captured_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    title_kk = fields.get("title_kk") or (existing.title_kk if existing else None)
    raw_html_ru = fields.get("raw_html_ru")
    raw_html_kk = fields.get("raw_html_kk") or (
        previous_snapshot.raw_html_kk if previous_snapshot else None
    )

    government_body = _get_or_create(session, GovernmentBody, fields.get("government_body"))
    act_type = _get_or_create(session, ActType, fields.get("doc_type"))

    content_sha256_ru = _sha256(raw_html_ru)
    content_sha256_kk = _sha256(raw_html_kk)

    values = {
        "section": section,
        "url": url,
        "title_ru": fields.get("title_ru"),
        "title_kk": title_kk,
        "status": fields.get("status"),
        "act_type_id": act_type.id if act_type else None,
        "government_body_id": government_body.id if government_body else None,
        "created_date": fields.get("created_date"),
        "discussion_end_date": fields.get("discussion_end_date"),
        "comments_total": fields.get("comments_total"),
        "likes_count": fields.get("likes_count"),
        "dislikes_count": fields.get("dislikes_count"),
        "content_sha256_ru": content_sha256_ru,
        "content_sha256_kk": content_sha256_kk,
    }

    changed = existing is None or any(
        getattr(existing, key) != values[key] for key in SNAPSHOT_TRIGGER_FIELDS
    )

    if existing is None:
        legal_act = LegalAct(external_id=external_id, first_seen_at=now, last_checked_at=now, **values)
        session.add(legal_act)
        session.flush()
    else:
        for key, value in values.items():
            setattr(existing, key, value)
        existing.last_checked_at = now
        legal_act = existing

    if changed:
        session.add(LegalActSnapshot(
            legal_act_id=legal_act.id,
            captured_at=now,
            raw_html_ru=raw_html_ru,
            raw_html_kk=raw_html_kk,
            content_sha256_ru=content_sha256_ru,
            content_sha256_kk=content_sha256_kk,
            title_ru=values["title_ru"],
            title_kk=title_kk,
            status=values["status"],
            act_type_id=values["act_type_id"],
            government_body_id=values["government_body_id"],
            created_date=values["created_date"],
            discussion_end_date=values["discussion_end_date"],
            comments_total=values["comments_total"],
            likes_count=values["likes_count"],
            dislikes_count=values["dislikes_count"],
        ))

    session.commit()
    return legal_act.id


def upsert_comments(session, legal_act_id, comments, comment_channel, now):
    for comment in comments:
        if comment["external_id"] is None:
            continue

        existing = session.execute(
            select(Comment).where(
                Comment.legal_act_id == legal_act_id,
                Comment.external_comment_id == comment["external_id"],
                Comment.comment_channel == comment_channel,
            )
        ).scalar_one_or_none()

        if existing is None:
            session.add(Comment(
                legal_act_id=legal_act_id,
                external_comment_id=comment["external_id"],
                parent_external_comment_id=comment["parent_external_id"],
                comment_channel=comment_channel,
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


def document_version_exists(session, external_id):
    return session.execute(
        select(DocumentVersion.id).where(DocumentVersion.external_id == external_id)
    ).scalar_one_or_none() is not None


def upsert_document_version(session, legal_act_id, external_id, fields, version_number, now):
    government_body = _get_or_create(session, GovernmentBody, fields.get("government_body"))
    act_type = _get_or_create(session, ActType, fields.get("doc_type"))

    session.add(DocumentVersion(
        legal_act_id=legal_act_id,
        external_id=external_id,
        version_number=version_number,
        title_ru=fields.get("title"),
        status=fields.get("status"),
        act_type_id=act_type.id if act_type else None,
        government_body_id=government_body.id if government_body else None,
        created_date=fields.get("created_date"),
        discussion_end_date=fields.get("discussion_end_date"),
        raw_html_ru=fields.get("raw_html_ru"),
        first_seen_at=now,
    ))
    session.commit()


def report_exists(session, legal_act_id):
    return session.execute(
        select(Report.id).where(Report.legal_act_id == legal_act_id)
    ).scalar_one_or_none() is not None


def upsert_report(session, legal_act_id, raw_html_ru, now):
    session.add(Report(legal_act_id=legal_act_id, raw_html_ru=raw_html_ru, first_seen_at=now))
    session.commit()


def legal_act_id_for_external_id(session, external_id):
    return session.execute(
        select(LegalAct.id).where(LegalAct.external_id == external_id)
    ).scalar_one_or_none()


def get_or_create_category(session, external_id, name):
    existing = session.execute(
        select(Category).where(Category.external_id == external_id)
    ).scalar_one_or_none()
    if existing is not None:
        if name and existing.name != name:
            existing.name = name
            session.commit()
        return existing

    category = Category(external_id=external_id, name=name)
    session.add(category)
    session.commit()
    return category


def link_legal_act_category(session, legal_act_id, category_id, now):
    existing = session.execute(
        select(LegalActCategory.id).where(
            LegalActCategory.legal_act_id == legal_act_id,
            LegalActCategory.category_id == category_id,
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(LegalActCategory(
            legal_act_id=legal_act_id, category_id=category_id, first_seen_at=now,
        ))
        session.commit()
