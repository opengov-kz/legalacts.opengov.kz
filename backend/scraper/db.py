import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id INTEGER NOT NULL UNIQUE,
    section TEXT NOT NULL,
    url TEXT NOT NULL,
    title_ru TEXT,
    title_kk TEXT,
    status TEXT,
    doc_type TEXT,
    government_body TEXT,
    created_date TEXT,
    discussion_end_date TEXT,
    comments_total INTEGER,
    likes_count INTEGER,
    dislikes_count INTEGER,
    raw_html_ru TEXT,
    raw_html_kk TEXT,
    first_seen_at TEXT NOT NULL,
    last_checked_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    external_comment_id INTEGER NOT NULL,
    parent_external_comment_id INTEGER,
    author_name TEXT,
    body TEXT NOT NULL,
    article_ref TEXT,
    status TEXT,
    commented_at_raw TEXT,
    first_seen_at TEXT NOT NULL,
    UNIQUE(document_id, external_comment_id)
);

CREATE TABLE IF NOT EXISTS crawl_queue (
    url TEXT PRIMARY KEY,
    page_type TEXT NOT NULL,
    section TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    discovered_at TEXT NOT NULL,
    processed_at TEXT
);
"""


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()
