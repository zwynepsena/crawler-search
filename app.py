# app.py
import os

from flask import Flask, jsonify, redirect, request, send_from_directory, url_for

import services.crawler_service as crawler_service
import services.search_service as search_service
from services.storage import init_db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "db", "crawler.db")
DEMO_DIR = os.path.join(BASE_DIR, "demo")


def _err(message: str, status: int):
    return jsonify({"error": message}), status


def _get_int(body: dict, key: str, default: int) -> int:
    value = body.get(key, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be an integer.")


def _get_float(body: dict, key: str, default: float) -> float:
    value = body.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a number.")


def _seed_demo_session() -> None:
    """
    Create one default crawler session on startup if the database is empty.
    """
    try:
        sessions = crawler_service.list_sessions(DB_PATH)
        if sessions:
            return

        crawler_service.create_session(
            db_path=DB_PATH,
            origin_url="https://www.wikipedia.org/",
            max_depth=1,
            max_urls=30,
            queue_capacity=50,
            num_workers=2,
            requests_per_sec=1.0,
        )
        print("[app] Seeded default crawler session.")
    except Exception as exc:
        print(f"[app] Could not seed default crawler session: {exc}")


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    init_db(DB_PATH)
    _seed_demo_session()

    # ── UI pages ──────────────────────────────────────────────

    @app.get("/")
    def index():
        return redirect(url_for("crawler_page"))

    @app.get("/crawler")
    def crawler_page():
        return send_from_directory(DEMO_DIR, "crawler.html")

    @app.get("/search")
    def search_page():
        return send_from_directory(DEMO_DIR, "search.html")

    @app.get("/status")
    def status_page():
        return send_from_directory(DEMO_DIR, "status.html")

    @app.get("/status/<int:session_id>")
    def crawler_detail_page(session_id: int):  # noqa: ARG001
        return send_from_directory(DEMO_DIR, "crawler_detail.html")

    # ── Static assets ─────────────────────────────────────────

    @app.get("/demo/css/<path:filename>")
    def demo_css(filename):
        return send_from_directory(os.path.join(DEMO_DIR, "css"), filename)

    @app.get("/demo/js/<path:filename>")
    def demo_js(filename):
        return send_from_directory(os.path.join(DEMO_DIR, "js"), filename)

    # ── Sessions API ──────────────────────────────────────────

    @app.post("/api/sessions")
    def api_create_session():
        body = request.get_json(silent=True) or {}

        origin_url = str(body.get("origin_url", "")).strip()
        if not origin_url:
            return _err("origin_url is required.", 400)

        if "max_depth" not in body:
            return _err("max_depth is required.", 400)

        try:
            max_depth = _get_int(body, "max_depth", 1)
            max_urls = _get_int(body, "max_urls", 100)
            queue_capacity = _get_int(body, "queue_capacity", 200)
            num_workers = _get_int(body, "num_workers", 4)
            requests_per_sec = _get_float(body, "requests_per_sec", 2.0)
        except ValueError as exc:
            return _err(str(exc), 400)

        if max_depth < 0:
            return _err("max_depth must be >= 0.", 400)
        if max_urls <= 0:
            return _err("max_urls must be > 0.", 400)
        if queue_capacity <= 0:
            return _err("queue_capacity must be > 0.", 400)
        if num_workers <= 0:
            return _err("num_workers must be > 0.", 400)
        if requests_per_sec <= 0:
            return _err("requests_per_sec must be > 0.", 400)

        try:
            session = crawler_service.create_session(
                db_path=DB_PATH,
                origin_url=origin_url,
                max_depth=max_depth,
                max_urls=max_urls,
                queue_capacity=queue_capacity,
                num_workers=num_workers,
                requests_per_sec=requests_per_sec,
            )
            return jsonify(session), 201
        except ValueError as exc:
            return _err(str(exc), 400)
        except RuntimeError as exc:
            return _err(str(exc), 500)
        except Exception as exc:
            return _err(f"Unexpected error while creating session: {exc}", 500)

    @app.get("/api/sessions")
    def api_list_sessions():
        return jsonify(crawler_service.list_sessions(DB_PATH)), 200

    @app.get("/api/sessions/<int:session_id>")
    def api_get_session(session_id: int):
        session = crawler_service.get_session_status(DB_PATH, session_id)
        if session is None:
            return _err(f"Session {session_id} not found.", 404)
        return jsonify(session), 200

    # ── Search API ────────────────────────────────────────────

    @app.get("/api/search")
    def api_search():
        query = request.args.get("q", "").strip()
        if not query:
            return _err("Query parameter 'q' is required.", 400)

        session_id = request.args.get("session_id", type=int)
        limit = request.args.get("limit", default=50, type=int)
        limit = max(1, min(limit, 200))

        try:
            results = search_service.search(
                db_path=DB_PATH,
                query=query,
                session_id=session_id,
                limit=limit,
            )
        except Exception as exc:
            return _err(f"Search failed: {exc}", 500)

        return jsonify({
            "query": query,
            "count": len(results),
            "results": results,
        }), 200

    # ── Detail endpoints ──────────────────────────────────────

    @app.get("/api/sessions/<int:session_id>/pages")
    def api_session_pages(session_id: int):
        if crawler_service.get_session_status(DB_PATH, session_id) is None:
            return _err(f"Session {session_id} not found.", 404)

        limit = request.args.get("limit", default=50, type=int)
        limit = max(1, min(limit, 200))

        try:
            pages = search_service.get_session_pages(
                db_path=DB_PATH,
                session_id=session_id,
                limit=limit,
            )
        except Exception as exc:
            return _err(f"Could not load session pages: {exc}", 500)

        return jsonify({
            "session_id": session_id,
            "count": len(pages),
            "pages": pages,
        }), 200

    @app.get("/api/sessions/<int:session_id>/queue")
    def api_session_queue(session_id: int):
        if crawler_service.get_session_status(DB_PATH, session_id) is None:
            return _err(f"Session {session_id} not found.", 404)

        limit = request.args.get("limit", default=50, type=int)
        limit = max(1, min(limit, 200))

        try:
            items = search_service.get_queue_items(
                db_path=DB_PATH,
                session_id=session_id,
                limit=limit,
            )
        except Exception as exc:
            return _err(f"Could not load queue items: {exc}", 500)

        return jsonify({
            "session_id": session_id,
            "count": len(items),
            "items": items,
        }), 200

    @app.get("/api/health")
    def api_health():
        return jsonify({"status": "ok", "db": DB_PATH}), 200

    return app


app = create_app()

if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        threaded=True,
    )