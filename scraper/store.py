DOCUMENT_FIELD_ORDER = [
    "section", "url", "title_ru", "title_kk", "status", "doc_type",
    "government_body", "created_date", "discussion_end_date",
    "comments_total", "likes_count", "dislikes_count", "raw_html_ru",
    "raw_html_kk",
]


def upsert_document(conn, external_id, section, url, fields, now):
    existing = conn.execute(
        "SELECT id, title_kk, raw_html_kk FROM documents WHERE external_id = ?",
        (external_id,),
    ).fetchone()

    title_kk = fields.get("title_kk") or (existing["title_kk"] if existing else None)
    raw_html_kk = fields.get("raw_html_kk") or (
        existing["raw_html_kk"] if existing else None
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
        conn.execute(
            "INSERT INTO documents (external_id, " + ", ".join(DOCUMENT_FIELD_ORDER) +
            ", first_seen_at, last_checked_at) VALUES (?, "
            + ", ".join("?" for _ in DOCUMENT_FIELD_ORDER) + ", ?, ?)",
            (external_id, *(values[key] for key in DOCUMENT_FIELD_ORDER), now, now),
        )
        conn.commit()
        return conn.execute(
            "SELECT id FROM documents WHERE external_id = ?", (external_id,)
        ).fetchone()["id"]

    conn.execute(
        "UPDATE documents SET "
        + ", ".join(f"{key} = ?" for key in DOCUMENT_FIELD_ORDER)
        + ", last_checked_at = ? WHERE id = ?",
        (*(values[key] for key in DOCUMENT_FIELD_ORDER), now, existing["id"]),
    )
    conn.commit()
    return existing["id"]


def upsert_comments(conn, document_id, comments, now):
    for comment in comments:
        if comment["external_id"] is None:
            # A comment whose <p> element is missing or has no id attribute can't
            # be de-duplicated across re-crawls (external_comment_id is NOT NULL
            # in the schema); dropping just this one comment is strictly better
            # than letting the INSERT raise and lose the whole document.
            continue
        conn.execute(
            """
            INSERT INTO comments (
                document_id, external_comment_id, parent_external_comment_id,
                author_name, body, article_ref, status, commented_at_raw,
                first_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id, external_comment_id) DO UPDATE SET
                parent_external_comment_id = excluded.parent_external_comment_id,
                author_name = excluded.author_name,
                body = excluded.body,
                article_ref = excluded.article_ref,
                status = excluded.status,
                commented_at_raw = excluded.commented_at_raw
            """,
            (
                document_id, comment["external_id"], comment["parent_external_id"],
                comment["author_name"], comment["body"], comment["article_ref"],
                comment["status"], comment["commented_at_raw"], now,
            ),
        )
    conn.commit()
