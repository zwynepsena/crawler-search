# services/crawler_service.py
import sqlite3
import threading
from typing import Optional

from services.storage import get_connection
from utils.crawler_job import CrawlJob

_jobs: dict[int, CrawlJob] = {}
_registry_lock = threading.Lock()


def create_session(
    db_path: str,
    origin_url: str,
    max_depth: int,
    max_urls: int = 500,
    queue_capacity: int = 200,
    num_workers: int = 4,
    requests_per_sec: float = 2.0,
) -> dict:
    origin_url = origin_url.strip()
    if not origin_url:
        raise ValueError("origin_url must not be empty.")
    if max_depth < 0:
        raise ValueError("max_depth must be >= 0.")

    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO crawl_sessions
                (origin_url, max_depth, max_urls, queue_capacity,
                 num_workers, requests_per_sec, status)
            VALUES (?, ?, ?, ?, ?, ?, 'running')
            """,
            (
                origin_url,
                max_depth,
                max_urls,
                queue_capacity,
                num_workers,
                requests_per_sec,
            ),
        )
        conn.commit()
        session_id = cur.lastrowid
    except sqlite3.Error as exc:
        raise RuntimeError(f"Failed to create session: {exc}") from exc
    finally:
        conn.close()

    job = CrawlJob(
        session_id=session_id,
        origin_url=origin_url,
        max_depth=max_depth,
        db_path=db_path,
        max_urls=max_urls,
        queue_capacity=queue_capacity,
        num_workers=num_workers,
        requests_per_sec=requests_per_sec,
    )
    job.start()

    with _registry_lock:
        _jobs[session_id] = job

    return get_session_status(db_path, session_id)


def get_session_status(db_path: str, session_id: int) -> Optional[dict]:
    db_row = _db_session_dict(db_path, session_id)
    if db_row is None:
        return None

    with _registry_lock:
        job = _jobs.get(session_id)

    if job is not None:
        if getattr(job, "is_done", False):
            with _registry_lock:
                _jobs.pop(session_id, None)

            refreshed = _db_session_dict(db_path, session_id)
            return refreshed

        live = _live_dict(session_id, job)
        db_row.update(
            {
                "status": live["status"],
                "pages_indexed": live["pages_indexed"],
                "urls_seen": live["urls_seen"],
                "urls_skipped": live["urls_skipped"],
                "active_workers": live["active_workers"],
                "queue_depth": live["queue_depth"],
                "hit_rate": live["hit_rate"],
                "error_message": live["error_message"],
            }
        )

    return _add_pressure_fields(db_row)


def list_sessions(db_path: str) -> list[dict]:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM crawl_sessions ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()

    result = []
    stale_ids = []

    with _registry_lock:
        for row in rows:
            sid = row["id"]
            base = _db_row_to_dict(row)
            job = _jobs.get(sid)

            if job is not None:
                if getattr(job, "is_done", False):
                    stale_ids.append(sid)
                else:
                    live = _live_dict(sid, job)
                    base.update(
                        {
                            "status": live["status"],
                            "pages_indexed": live["pages_indexed"],
                            "urls_seen": live["urls_seen"],
                            "urls_skipped": live["urls_skipped"],
                            "active_workers": live["active_workers"],
                            "queue_depth": live["queue_depth"],
                            "hit_rate": live["hit_rate"],
                            "error_message": live["error_message"],
                        }
                    )

            result.append(_add_pressure_fields(base))

        for sid in stale_ids:
            _jobs.pop(sid, None)

    return result


def _live_dict(session_id: int, job: CrawlJob) -> dict:
    s = job.stats
    return {
        "session_id": session_id,
        "origin_url": s.origin_url,
        "max_depth": s.max_depth,
        "max_urls": s.max_urls,
        "queue_capacity": s.queue_capacity,
        "num_workers": getattr(s, "num_workers", None),
        "requests_per_sec": getattr(s, "requests_per_sec", None),
        "status": s.status,
        "pages_indexed": s.pages_indexed,
        "urls_seen": s.urls_seen,
        "urls_skipped": s.urls_skipped,
        "active_workers": s.active_workers,
        "queue_depth": s.queue_depth,
        "hit_rate": round(s.hit_rate, 4),
        "error_message": s.error_message,
        "created_at": None,
        "updated_at": None,
    }


def _db_session_dict(db_path: str, session_id: int) -> Optional[dict]:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM crawl_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()

    return _db_row_to_dict(row) if row else None


def _db_row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "session_id": row["id"],
        "origin_url": row["origin_url"],
        "max_depth": row["max_depth"],
        "max_urls": row["max_urls"],
        "queue_capacity": row["queue_capacity"],
        "num_workers": row["num_workers"],
        "requests_per_sec": row["requests_per_sec"],
        "status": row["status"],
        "pages_indexed": row["pages_indexed"],
        "urls_seen": row["urls_seen"],
        "urls_skipped": row["urls_skipped"],
        "active_workers": row["active_workers"],
        "queue_depth": row["queue_depth"],
        "hit_rate": round(float(row["hit_rate"]), 4),
        "error_message": None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    
def _add_pressure_fields(data: dict) -> dict:
    queue_capacity = data.get("queue_capacity") or 0
    queue_depth = data.get("queue_depth") or 0

    ratio = queue_depth / max(queue_capacity, 1)

    if ratio >= 1.0:
        status = "full"
    elif ratio >= 0.8:
        status = "high"
    elif ratio >= 0.4:
        status = "moderate"
    else:
        status = "normal"

    data["queue_utilization"] = round(ratio, 2)
    data["back_pressure_status"] = status
    return data