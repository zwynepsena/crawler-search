"""
Core crawl loop for a single session.

Each CrawlJob owns:
  - A bounded Queue for back pressure.
  - A visited set (normalized URLs) protected by a lock.
  - A configurable thread pool of worker threads.
  - Incremental SQLite writes so search sees results immediately.
  - Stats that crawler_service can poll for the status page.
"""

import queue
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import services.storage as storage
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from services.storage import get_connection
from utils.html_parser import extract_links, extract_text


_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_url(url: str) -> str:
    """
    Return a canonical form of *url* for deduplication.
    """
    try:
        p = urlparse(url)
        scheme = p.scheme.lower()
        host = p.hostname or ""
        port = p.port

        if port and port == _DEFAULT_PORTS.get(scheme):
            port = None

        netloc = f"{host}:{port}" if port else host
        path = p.path.rstrip("/") or "/"
        query = urlencode(sorted(parse_qsl(p.query)))
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return url


DEBUG_LOGS = False


def dprint(*args, **kwargs):
    if DEBUG_LOGS:
        print(*args, **kwargs)


@dataclass
class CrawlStats:
    session_id: int
    origin_url: str
    max_depth: int
    max_urls: int
    queue_capacity: int
    num_workers: int
    requests_per_sec: float
    status: str = "running"  # running | completed | error
    pages_indexed: int = 0
    urls_seen: int = 0
    urls_skipped: int = 0
    active_workers: int = 0
    queue_depth: int = 0
    hit_rate: float = 0.0
    error_message: Optional[str] = None

    def update_hit_rate(self) -> None:
        self.hit_rate = (
            self.pages_indexed / self.urls_seen if self.urls_seen > 0 else 0.0
        )


class _RateLimiter:
    """
    Allows at most *rate* requests per second across all workers in a session.
    """

    def __init__(self, rate: float):
        self._rate = max(rate, 0.01)
        self._lock = threading.Lock()
        self._tokens = self._rate
        self._last = time.monotonic()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self._rate, self._tokens + elapsed * self._rate)

            if self._tokens >= 1:
                self._tokens -= 1
                return

            sleep_for = (1 - self._tokens) / self._rate

        time.sleep(sleep_for)


class CrawlJob:
    """
    Manages one crawl session end-to-end.
    """

    def __init__(
        self,
        session_id: int,
        origin_url: str,
        max_depth: int,
        db_path: str,
        max_urls: int = 500,
        queue_capacity: int = 200,
        num_workers: int = 4,
        requests_per_sec: float = 2.0,
        resume_urls: Optional[list[tuple[str, int]]] = None,
    ):
        self.db_path = db_path

        self.stats = CrawlStats(
            session_id=session_id,
            origin_url=origin_url,
            max_depth=max_depth,
            max_urls=max_urls,
            queue_capacity=queue_capacity,
            num_workers=num_workers,
            requests_per_sec=requests_per_sec,
        )

        self._q: queue.Queue[tuple[str, str, int]] = queue.Queue(maxsize=queue_capacity)

        self._visited: set[str] = set()
        self._visited_lock = threading.Lock()
        self._stats_lock = threading.RLock()

        self._rate_limiter = _RateLimiter(requests_per_sec)
        self._num_workers = num_workers
        self._threads: list[threading.Thread] = []

        self._inflight = 0
        self._inflight_lock = threading.Lock()

        if resume_urls:
            for raw_url, depth in resume_urls:
                norm = normalize_url(raw_url)
                with self._visited_lock:
                    self._visited.add(norm)
                try:
                    self._q.put_nowait((raw_url, origin_url, depth))
                except queue.Full:
                    pass
        else:
            norm = normalize_url(origin_url)
            with self._visited_lock:
                self._visited.add(norm)
            self._q.put_nowait((origin_url, origin_url, 0))

    def start(self) -> None:
        for i in range(self._num_workers):
            t = threading.Thread(
                target=self._worker,
                name=f"crawler-{self.stats.session_id}-{i}",
                daemon=True,
            )
            t.start()
            self._threads.append(t)

        with self._stats_lock:
            self.stats.active_workers = 0
            self.stats.queue_depth = self._q.qsize()

        watcher = threading.Thread(
            target=self._watchdog,
            name=f"watchdog-{self.stats.session_id}",
            daemon=True,
        )
        watcher.start()

    @property
    def is_done(self) -> bool:
        return self.stats.status in ("completed", "error")

    def _worker(self) -> None:
        conn = get_connection(self.db_path)
        try:
            while True:
                item = None
                try:
                    with self._stats_lock:
                        if self.stats.status in ("completed", "error"):
                            return

                    item = self._q.get(timeout=0.5)

                    with self._inflight_lock:
                        self._inflight += 1

                    raw_url, origin_url, depth = item

                    self._process(raw_url, origin_url, depth, conn)

                except queue.Empty:
                    with self._stats_lock:
                        if self.stats.status in ("completed", "error"):
                            return
                    continue

                except Exception as exc:
                    print(f"[worker error] session={self.stats.session_id} -> {exc}")

                finally:
                    if item is not None:
                        try:
                            self._q.task_done()
                        except Exception:
                            pass

                        with self._inflight_lock:
                            self._inflight = max(0, self._inflight - 1)

                        with self._stats_lock:
                            self.stats.active_workers = self._inflight
                            self.stats.queue_depth = self._q.qsize()
        finally:
            conn.close()

    def _process(
        self,
        raw_url: str,
        origin_url: str,
        depth: int,
        conn: sqlite3.Connection,
    ) -> None:
        with self._stats_lock:
            if self.stats.urls_seen >= self.stats.max_urls:
                self.stats.urls_skipped += 1
                return
            self.stats.urls_seen += 1
            self.stats.update_hit_rate()

        self._rate_limiter.acquire()

        html = self._fetch(raw_url)
        norm_url = normalize_url(raw_url)

        if html is None:
            self._mark_queue_status(conn, norm_url, "failed")
            self._update_session_stats(conn)
            return

        title, body_text = extract_text(html)
        links = extract_links(html, raw_url)

        stored = self._store_page(
            conn=conn,
            raw_url=raw_url,
            norm_url=norm_url,
            origin_url=origin_url,
            depth=depth,
            title=title,
            body_text=body_text,
        )

        if stored:
            with self._stats_lock:
                self.stats.pages_indexed += 1
                self.stats.update_hit_rate()

        self._mark_queue_status(conn, norm_url, "done")

        if depth < self.stats.max_depth:
            for link in links:
                with self._stats_lock:
                    if self.stats.urls_seen >= self.stats.max_urls:
                        break
                self._try_enqueue(link, origin_url, depth + 1)

        self._update_session_stats(conn)

        with self._stats_lock:
            self.stats.queue_depth = self._q.qsize()
            
    def _bump_skipped(self, amount: int = 1) -> None:
        with self._stats_lock:
            self.stats.urls_skipped += amount
            self.stats.update_hit_rate()

    def _try_enqueue(self, url: str, origin_url: str, depth: int) -> bool:
        normalized = normalize_url(url)
        if not normalized:
            return False

        with self._visited_lock:
            if normalized in self._visited:
                self._bump_skipped()
                return False
            self._visited.add(normalized)

        item = (url, origin_url, depth)

        try:
            self._q.put_nowait(item)
        except queue.Full:
            with self._visited_lock:
                self._visited.discard(normalized)
            self._bump_skipped()
            return False

        try:
            storage.enqueue_url(
                self.db_path,
                session_id=self.stats.session_id,
                url=url,
                url_normalized=normalized,
                depth=depth,
            )
        except Exception:
            try:
                _ = self._q.get_nowait()
                self._q.task_done()
            except Exception:
                pass

            with self._visited_lock:
                self._visited.discard(normalized)

            self._bump_skipped()
            return False

        return True

    def _mark_queue_status(
        self,
        conn: sqlite3.Connection,
        norm_url: str,
        status: str,
    ) -> None:
        try:
            conn.execute(
                """
                UPDATE crawl_queue
                   SET status = ?
                 WHERE session_id = ?
                   AND url_normalized = ?
                """,
                (status, self.stats.session_id, norm_url),
            )
            conn.commit()
        except sqlite3.Error as exc:
            print(f"[queue update error] {norm_url} -> {exc}")

    def _clear_pending_queue(self, conn: sqlite3.Connection) -> None:
        try:
            conn.execute(
                """
                DELETE FROM crawl_queue
                 WHERE session_id = ?
                   AND status = 'pending'
                """,
                (self.stats.session_id,),
            )
            conn.commit()
        except sqlite3.Error as exc:
            print(f"[queue clear error] session={self.stats.session_id} -> {exc}")

    def _fetch(self, url: str) -> Optional[str]:
        import ssl
        import gzip
        import zlib

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept-Encoding": "identity",
                },
            )

            ctx = ssl._create_unverified_context()

            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                content_type = resp.headers.get("Content-Type", "")
                content_encoding = (resp.headers.get("Content-Encoding") or "").lower()
                raw = resp.read()

                if "text/html" not in content_type.lower():
                    dprint(f"[fetch skip] non-html: {url}")
                    return None

                if content_encoding == "gzip":
                    raw = gzip.decompress(raw)
                elif content_encoding == "deflate":
                    raw = zlib.decompress(raw)

                charset = resp.headers.get_content_charset() or "utf-8"
                html = raw.decode(charset, errors="replace")
                return html

        except urllib.error.HTTPError as exc:
            print(f"[fetch HTTP error] {url} -> {exc.code} {exc.reason}")
            return None
        except urllib.error.URLError as exc:
            print(f"[fetch URL error] {url} -> {exc}")
            return None
        except Exception as exc:
            print(f"[fetch error] {url} -> {exc}")
            return None

    def _store_page(
        self,
        conn: sqlite3.Connection,
        raw_url: str,
        norm_url: str,
        origin_url: str,
        depth: int,
        title: str,
        body_text: str,
    ) -> bool:
        try:
            cur = conn.execute(
                """
                INSERT INTO pages
                    (session_id, url, url_normalized, origin_url, depth, title, body_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id, url_normalized) DO UPDATE SET
                    url        = excluded.url,
                    origin_url = excluded.origin_url,
                    depth      = excluded.depth,
                    title      = CASE
                                   WHEN trim(pages.title) = '' THEN excluded.title
                                   ELSE pages.title
                                 END,
                    body_text  = CASE
                                   WHEN trim(pages.body_text) = '' THEN excluded.body_text
                                   ELSE pages.body_text
                                 END,
                    indexed_at = CURRENT_TIMESTAMP
                """,
                (
                    self.stats.session_id,
                    raw_url,
                    norm_url,
                    origin_url,
                    depth,
                    title or "",
                    body_text or "",
                ),
            )
            conn.commit()
            return True
        except sqlite3.Error as exc:
            print(f"[store error] {raw_url} -> {exc}")
            return False

    def _update_session_stats(self, conn: sqlite3.Connection) -> None:
        with self._stats_lock:
            pages_indexed = self.stats.pages_indexed
            urls_seen = self.stats.urls_seen
            urls_skipped = self.stats.urls_skipped
            active_workers = self.stats.active_workers
            queue_depth = self.stats.queue_depth
            hit_rate = self.stats.hit_rate
            status = self.stats.status

        try:
            conn.execute(
                """
                UPDATE crawl_sessions
                   SET status = ?,
                       pages_indexed = ?,
                       urls_seen = ?,
                       urls_skipped = ?,
                       active_workers = ?,
                       queue_depth = ?,
                       hit_rate = ?,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = ?
                """,
                (
                    status,
                    pages_indexed,
                    urls_seen,
                    urls_skipped,
                    active_workers,
                    queue_depth,
                    hit_rate,
                    self.stats.session_id,
                ),
            )
            conn.commit()
        except sqlite3.Error as exc:
            print(f"[session stats error] session={self.stats.session_id} -> {exc}")

    def _pending_queue_count(self, conn: sqlite3.Connection) -> int:
        try:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM crawl_queue
                WHERE session_id = ? AND status = 'pending'
                """,
                (self.stats.session_id,),
            ).fetchone()
            return int(row[0] or 0)
        except sqlite3.Error as exc:
            print(f"[queue count error] session={self.stats.session_id} -> {exc}")
            return 0

    def _watchdog(self) -> None:
        while True:
            time.sleep(0.5)

            mem_qsize = self._q.qsize()

            with self._inflight_lock:
                inflight = self._inflight

            conn = get_connection(self.db_path)
            try:
                db_pending = self._pending_queue_count(conn)
                db_pages = storage.count_pages_for_session(
                    self.db_path,
                    self.stats.session_id,
                )

                should_complete = False

                with self._stats_lock:
                    self.stats.active_workers = inflight
                    self.stats.pages_indexed = db_pages
                    self.stats.queue_depth = max(mem_qsize, db_pending)

                    reached_limit = self.stats.urls_seen >= self.stats.max_urls
                    truly_done = (
                        mem_qsize == 0
                        and inflight == 0
                        and self.stats.urls_seen > 0
                    )

                    if reached_limit or truly_done:
                        self.stats.status = "completed"
                        self.stats.active_workers = 0
                        self.stats.queue_depth = 0
                        self.stats.update_hit_rate()
                        should_complete = True
                    elif self.stats.status != "error":
                        self.stats.status = "running"

                if should_complete:
                    self._clear_pending_queue(conn)
                    self._update_session_stats(conn)
                    return

                self._update_session_stats(conn)
            finally:
                conn.close()