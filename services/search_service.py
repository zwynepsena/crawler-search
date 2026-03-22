# services/search_service.py
import sqlite3
from typing import Optional

from services.storage import get_connection

_DEFAULT_LIMIT = 50


def search(
    db_path:    str,
    query:      str,
    session_id: Optional[int] = None,
    limit:      int           = _DEFAULT_LIMIT,
) -> list[dict]:
    query = query.strip()
    if not query:
        return []

    conn = get_connection(db_path)
    try:
        if _fts_available(conn):
            results = _fts_search(conn, query, session_id, limit)
            if not results:
                results = _fallback_search(conn, query, session_id, limit)
            return results
        return _fallback_search(conn, query, session_id, limit)
    finally:
        conn.close()


def get_session_pages(
    db_path:    str,
    session_id: int,
    limit:      int = 100,
) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT url, origin_url, depth, title, session_id,
                   0.0 AS score
              FROM pages
             WHERE session_id = ?
             ORDER BY id DESC
             LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_queue_items(
    db_path:    str,
    session_id: int,
    limit:      int = 50,
) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT url, url_normalized, depth, status, created_at
              FROM crawl_queue
             WHERE session_id = ?
               AND status     = 'pending'
             ORDER BY id ASC
             LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()
        return [
            {
                "url":        r["url"],
                "normalized": r["url_normalized"],
                "depth":      r["depth"],
                "status":     r["status"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def _fts_available(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='pages_fts'"
    ).fetchone()
    return row is not None


def _fts_search(
    conn:       sqlite3.Connection,
    query:      str,
    session_id: Optional[int],
    limit:      int,
) -> list[dict]:
    safe = _sanitise(query)
    if not safe:
        return []

    sql = """
        SELECT p.url, p.origin_url, p.depth, p.title, p.session_id,
               -bm25(pages_fts) AS score
          FROM pages_fts
          JOIN pages AS p ON pages_fts.rowid = p.id
         WHERE pages_fts MATCH ?
    """
    params: list = [safe]
    if session_id is not None:
        sql += " AND p.session_id = ?"
        params.append(session_id)
    sql += " ORDER BY score DESC LIMIT ?"
    params.append(limit)

    try:
        return [_row_to_dict(r) for r in conn.execute(sql, params).fetchall()]
    except sqlite3.OperationalError:
        return []


def _fallback_search(
    conn:       sqlite3.Connection,
    query:      str,
    session_id: Optional[int],
    limit:      int,
) -> list[dict]:
    pat = f"%{query}%"
    sql = """
        SELECT url, origin_url, depth, title, session_id,
               (CASE WHEN title     LIKE ? THEN 2 ELSE 0 END +
                CASE WHEN body_text LIKE ? THEN 1 ELSE 0 END +
                CASE WHEN url       LIKE ? THEN 1 ELSE 0 END) AS score
          FROM pages
         WHERE (title LIKE ? OR body_text LIKE ? OR url LIKE ?)
    """
    params: list = [pat, pat, pat, pat, pat, pat]
    if session_id is not None:
        sql += " AND session_id = ?"
        params.append(session_id)
    sql += " ORDER BY score DESC, id DESC LIMIT ?"
    params.append(limit)
    return [_row_to_dict(r) for r in conn.execute(sql, params).fetchall()]


def _sanitise(query: str) -> str:
    cleaned = query.replace('"', "").replace("'", "").strip()
    if not cleaned:
        return ""
    tokens = cleaned.split()
    if len(tokens) == 1:
        return f"{tokens[0]}*"
    return f'"{" ".join(tokens)}"'


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "url":        row["url"],
        "origin_url": row["origin_url"],
        "depth":      row["depth"],
        "title":      row["title"] or "",
        "score":      round(float(row["score"]), 4),
        "session_id": row["session_id"],
    }