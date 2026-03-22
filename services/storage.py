# services/storage.py
"""
Database layer for the web crawler.

Responsibilities:
  - Open SQLite connections with consistent settings (WAL, foreign keys).
  - Create all tables, FTS index, triggers, and indexes via init_db().
  - Serve as the single source of truth for the schema.
"""

import sqlite3


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------

def get_connection(db_path: str) -> sqlite3.Connection:
    """
    Open and return a SQLite connection configured for concurrent use.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------

def init_db(db_path: str) -> None:
    """
    Create all tables, indexes, and triggers if they do not already exist.
    Safe to call on every application startup.
    """
    conn = get_connection(db_path)
    try:
        _create_tables(conn)
        _migrate_schema(conn)
        _create_indexes(conn)
        _create_triggers(conn)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Table definitions
# ---------------------------------------------------------------------------

_SQL_CRAWL_SESSIONS = """
CREATE TABLE IF NOT EXISTS crawl_sessions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Crawl configuration
    origin_url       TEXT    NOT NULL,
    max_depth        INTEGER NOT NULL,
    max_urls         INTEGER NOT NULL DEFAULT 500,
    queue_capacity   INTEGER NOT NULL DEFAULT 200,
    num_workers      INTEGER NOT NULL DEFAULT 4,
    requests_per_sec REAL    NOT NULL DEFAULT 2.0,

    -- Lifecycle
    -- Allowed values: running | stopping | paused | done | error
    status           TEXT    NOT NULL DEFAULT 'running',

    -- Live counters
    pages_indexed    INTEGER NOT NULL DEFAULT 0,
    urls_seen        INTEGER NOT NULL DEFAULT 0,
    urls_skipped     INTEGER NOT NULL DEFAULT 0,
    active_workers   INTEGER NOT NULL DEFAULT 0,
    queue_depth      INTEGER NOT NULL DEFAULT 0,

    -- Derived metric
    hit_rate         REAL    NOT NULL DEFAULT 0.0,

    -- Timestamps
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

_SQL_PAGES = """
CREATE TABLE IF NOT EXISTS pages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES crawl_sessions(id),

    url             TEXT    NOT NULL,
    url_normalized  TEXT    NOT NULL,

    origin_url      TEXT    NOT NULL,
    depth           INTEGER NOT NULL,

    title           TEXT    NOT NULL DEFAULT '',
    body_text       TEXT    NOT NULL DEFAULT '',

    indexed_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (session_id, url_normalized)
)
"""

_SQL_PAGES_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    url,
    title,
    body_text,
    content='pages',
    content_rowid='id',
    tokenize='porter unicode61'
)
"""

_SQL_CRAWL_QUEUE = """
CREATE TABLE IF NOT EXISTS crawl_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER NOT NULL REFERENCES crawl_sessions(id),

    url             TEXT    NOT NULL,
    url_normalized  TEXT    NOT NULL,
    depth           INTEGER NOT NULL,

    -- pending | done | failed
    status          TEXT    NOT NULL DEFAULT 'pending',

    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (session_id, url_normalized)
)
"""


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.execute(_SQL_CRAWL_SESSIONS)
    conn.execute(_SQL_PAGES)
    conn.execute(_SQL_PAGES_FTS)
    conn.execute(_SQL_CRAWL_QUEUE)


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """
    Lightweight additive migrations for older DB files.
    Safe to run repeatedly.
    """
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(crawl_sessions)").fetchall()
    }

    if "queue_depth" not in columns:
        conn.execute("""
            ALTER TABLE crawl_sessions
            ADD COLUMN queue_depth INTEGER NOT NULL DEFAULT 0
        """)

    conn.commit()


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------

def _create_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_pages_session
            ON pages (session_id, depth);

        CREATE INDEX IF NOT EXISTS idx_sessions_status
            ON crawl_sessions (status);

        CREATE INDEX IF NOT EXISTS idx_queue_session_status
            ON crawl_queue (session_id, status);
    """)


# ---------------------------------------------------------------------------
# FTS consistency triggers
# ---------------------------------------------------------------------------

def _create_triggers(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TRIGGER IF NOT EXISTS pages_fts_insert
        AFTER INSERT ON pages BEGIN
            INSERT INTO pages_fts (rowid, url, title, body_text)
            VALUES (new.id, new.url, new.title, new.body_text);
        END;

        CREATE TRIGGER IF NOT EXISTS pages_fts_delete
        AFTER DELETE ON pages BEGIN
            INSERT INTO pages_fts (pages_fts, rowid, url, title, body_text)
            VALUES ('delete', old.id, old.url, old.title, old.body_text);
        END;

        CREATE TRIGGER IF NOT EXISTS pages_fts_update
        AFTER UPDATE ON pages BEGIN
            INSERT INTO pages_fts (pages_fts, rowid, url, title, body_text)
            VALUES ('delete', old.id, old.url, old.title, old.body_text);
            INSERT INTO pages_fts (rowid, url, title, body_text)
            VALUES (new.id, new.url, new.title, new.body_text);
        END;
    """)
    
    
def enqueue_url(
    db_path: str,
    session_id: int,
    url: str,
    url_normalized: str,
    depth: int,
) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO crawl_queue (
                session_id, url, url_normalized, depth, status
            )
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (session_id, url, url_normalized, depth),
        )
        conn.commit()
    finally:
        conn.close()
        
def count_pages_for_session(db_path: str, session_id: int) -> int:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM pages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["c"] or 0)
    finally:
        conn.close()