# =============================================================================
# FILE: web/dashboard.py
# AURA Web Dashboard — localhost:5000
#
# A full web UI for AURA accessible from any device on your network.
# Mirrors the desktop GUI: chat, history, skills panel, scheduler, settings.
#
# Features:
#   - Real-time streaming responses via Server-Sent Events (SSE)
#   - Full chat history with search
#   - Skills panel (list / enable / disable)
#   - Scheduler panel (add / list / delete jobs)
#   - System status (CPU, RAM, GPU, Ollama health)
#   - Mobile-responsive dark UI
#   - REST + SSE API so you can build your own clients
#
# Usage:
#   from web.dashboard import start_dashboard
#   start_dashboard(aura_respond_fn, port=5000)   # runs in background thread
#
# Requirements:
#   pip install flask flask-cors
# =============================================================================

import os
import sys
import json
import time
import queue
import logging
import threading
from typing import Callable, Optional, Generator
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from flask import Flask, request, Response, jsonify, send_from_directory
    from flask_cors import CORS
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    logger.warning("Flask not installed. Run: pip install flask flask-cors")

DASHBOARD_DIR = Path(__file__).parent
STATIC_DIR    = DASHBOARD_DIR / "static"
TEMPLATE_DIR  = DASHBOARD_DIR / "templates"


# =============================================================================
# APP FACTORY
# =============================================================================

def create_app(aura_respond_fn: Callable) -> "Flask":
    """
    Build the Flask app with all routes wired to aura_respond_fn.
    aura_respond_fn(text: str, context: str = "") -> str
    """
    app = Flask(
        __name__,
        static_folder=str(STATIC_DIR),
        template_folder=str(TEMPLATE_DIR)
    )
    CORS(app)

    # ── SSE event queue (one per connected client) ────────────────────────────
    _clients: list[queue.Queue] = []
    _clients_lock = threading.Lock()

    def _broadcast(event: str, data: dict):
        """Push an event to all connected SSE clients."""
        msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        with _clients_lock:
            dead = []
            for q in _clients:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    dead.append(q)
            for q in dead:
                _clients.remove(q)

    # =========================================================================
    # ROUTES — Static / UI
    # =========================================================================

    @app.route("/")
    def index():
        return send_from_directory(str(TEMPLATE_DIR), "index.html")

    @app.route("/static/<path:filename>")
    def static_files(filename):
        return send_from_directory(str(STATIC_DIR), filename)

    # =========================================================================
    # ROUTES — Chat
    # =========================================================================

    @app.route("/api/chat", methods=["POST"])
    def chat():
        """
        POST /api/chat  { "message": "...", "context": "..." }
        Returns the full response as JSON (non-streaming).
        """
        data    = request.get_json(force=True) or {}
        message = data.get("message", "").strip()
        context = data.get("context", "")

        if not message:
            return jsonify({"error": "empty message"}), 400

        try:
            response = aura_respond_fn(message, context)
            _broadcast("message", {"role": "assistant", "content": response})
            return jsonify({"response": response})
        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/chat/stream", methods=["POST"])
    def chat_stream():
        """
        POST /api/chat/stream  { "message": "..." }
        Returns a streaming response via SSE.
        """
        data    = request.get_json(force=True) or {}
        message = data.get("message", "").strip()
        context = data.get("context", "")

        if not message:
            return jsonify({"error": "empty message"}), 400

        def _generate() -> Generator[str, None, None]:
            yield f"data: {json.dumps({'type': 'start'})}\n\n"
            try:
                # Run in thread so we don't block the event loop
                result_q: queue.Queue = queue.Queue()

                def _worker():
                    try:
                        resp = aura_respond_fn(message, context)
                        result_q.put(("ok", resp))
                    except Exception as exc:
                        result_q.put(("err", str(exc)))

                t = threading.Thread(target=_worker, daemon=True)
                t.start()

                # Poll — yield heartbeats while waiting
                while t.is_alive():
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                    time.sleep(0.4)

                status, value = result_q.get(timeout=5)
                if status == "ok":
                    # Stream word-by-word for a typewriter effect
                    words = value.split(" ")
                    chunk = ""
                    for word in words:
                        chunk += word + " "
                        if len(chunk) >= 20:
                            yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"
                            chunk = ""
                    if chunk:
                        yield f"data: {json.dumps({'type': 'token', 'text': chunk})}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'full': value})}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'error', 'message': value})}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return Response(_generate(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache",
                                 "X-Accel-Buffering": "no"})

    # =========================================================================
    # ROUTES — History
    # =========================================================================

    @app.route("/api/history")
    def history():
        """GET /api/history?q=query&date=2024-01-15&limit=20"""
        q     = request.args.get("q")
        date  = request.args.get("date")
        topic = request.args.get("topic")
        limit = int(request.args.get("limit", 20))
        try:
            from core.memory_enhanced import search_history
            results = search_history(query=q, date=date, topic=topic, limit=limit)
            return jsonify({"results": results, "count": len(results)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/history/recall", methods=["POST"])
    def recall():
        """POST /api/history/recall  { "query": "..." }"""
        query = (request.get_json(force=True) or {}).get("query", "")
        try:
            from core.memory_enhanced import recall_formatted
            context = recall_formatted(query)
            return jsonify({"context": context})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # =========================================================================
    # ROUTES — Skills
    # =========================================================================

    @app.route("/api/skills")
    def skills_list():
        try:
            from skills.skill_loader import get_registry
            skills = [
                {
                    "name":        s.name,
                    "description": s.description,
                    "icon":        s.icon,
                    "version":     s.version,
                    "author":      s.author,
                    "keywords":    s.keywords,
                    "enabled":     s.enabled,
                }
                for s in get_registry().list_skills()
            ]
            return jsonify({"skills": skills})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/skills/<name>/toggle", methods=["POST"])
    def skill_toggle(name: str):
        enabled = (request.get_json(force=True) or {}).get("enabled", True)
        try:
            from skills.skill_loader import get_registry
            get_registry().enable(name, enabled)
            return jsonify({"ok": True, "name": name, "enabled": enabled})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/skills/reload", methods=["POST"])
    def skills_reload():
        try:
            from skills.skill_loader import get_registry
            get_registry().reload()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # =========================================================================
    # ROUTES — Scheduler
    # =========================================================================

    @app.route("/api/scheduler/jobs")
    def scheduler_jobs():
        try:
            from scheduler import get_scheduler
            return jsonify({"jobs": get_scheduler().list_jobs()})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/scheduler/add", methods=["POST"])
    def scheduler_add():
        data  = request.get_json(force=True) or {}
        name  = data.get("name", "")
        task  = data.get("task", "")
        sched = data.get("schedule", "")
        if not all([name, task, sched]):
            return jsonify({"error": "name, task, schedule required"}), 400
        try:
            from scheduler import get_scheduler
            job = get_scheduler().add_job(name=name, task=task, schedule=sched)
            return jsonify({"ok": True, "job": job.to_dict()})
        except Exception as e:
            return jsonify({"error": str(e)}), 400

    @app.route("/api/scheduler/jobs/<job_id>", methods=["DELETE"])
    def scheduler_delete(job_id: str):
        try:
            from scheduler import get_scheduler
            ok = get_scheduler().remove_job(job_id)
            return jsonify({"ok": ok})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # =========================================================================
    # ROUTES — Memory / Knowledge
    # =========================================================================

    @app.route("/api/memory")
    def memory_list():
        try:
            from core.memory import list_knowledge, memory_stats
            return jsonify({
                "facts": list_knowledge(),
                "stats": memory_stats()
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/memory/learn", methods=["POST"])
    def memory_learn():
        fact = (request.get_json(force=True) or {}).get("fact", "")
        if not fact:
            return jsonify({"error": "fact required"}), 400
        try:
            from core.memory import learn
            added = learn(fact, source="web_dashboard")
            return jsonify({"ok": True, "added": added})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/memory/forget", methods=["POST"])
    def memory_forget():
        text = (request.get_json(force=True) or {}).get("text", "")
        try:
            from core.memory import forget
            ok = forget(text)
            return jsonify({"ok": ok})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # =========================================================================
    # ROUTES — Status
    # =========================================================================

    @app.route("/api/status")
    def status():
        import platform
        info = {
            "platform": platform.system(),
            "python":   platform.python_version(),
            "ollama":   _check_ollama(),
        }
        try:
            import psutil
            info["cpu_percent"] = psutil.cpu_percent(interval=0.3)
            mem = psutil.virtual_memory()
            info["ram_percent"] = mem.percent
            info["ram_used_gb"] = round(mem.used / 1024**3, 1)
            info["ram_total_gb"] = round(mem.total / 1024**3, 1)
        except Exception:
            pass
        try:
            import torch
            info["gpu_available"] = torch.cuda.is_available()
            if info["gpu_available"]:
                info["gpu_name"]    = torch.cuda.get_device_name(0)
                info["gpu_vram_gb"] = round(
                    torch.cuda.get_device_properties(0).total_memory / 1024**3, 1
                )
        except Exception:
            info["gpu_available"] = False
        return jsonify(info)

    @app.route("/api/status/sse")
    def status_sse():
        """SSE stream for real-time status updates."""
        q: queue.Queue = queue.Queue(maxsize=50)
        with _clients_lock:
            _clients.append(q)

        def _stream():
            try:
                while True:
                    try:
                        msg = q.get(timeout=30)
                        yield msg
                    except queue.Empty:
                        yield f"data: {json.dumps({'type': 'ping'})}\n\n"
            finally:
                with _clients_lock:
                    if q in _clients:
                        _clients.remove(q)

        return Response(_stream(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache",
                                 "X-Accel-Buffering": "no"})

    # =========================================================================
    # ROUTES — Config
    # =========================================================================

    @app.route("/api/config")
    def config_get():
        try:
            from config import load_config
            return jsonify(load_config())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/config", methods=["POST"])
    def config_set():
        data = request.get_json(force=True) or {}
        try:
            from config import load_config, save_config
            cfg = load_config()
            cfg.update(data)
            save_config(cfg)
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app


# =============================================================================
# HELPERS
# =============================================================================

def _check_ollama() -> bool:
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


# =============================================================================
# RUNNER
# =============================================================================

class AuraDashboard:
    """Manages the Flask dashboard lifecycle in a background thread."""

    def __init__(self, aura_respond_fn: Callable, host: str = "0.0.0.0", port: int = 5000):
        self._fn   = aura_respond_fn
        self._host = host
        self._port = port
        self._thread: Optional[threading.Thread] = None
        self._app = None

    def start(self) -> bool:
        if not FLASK_AVAILABLE:
            logger.error("Flask not installed. Run: pip install flask flask-cors")
            return False

        self._app = create_app(self._fn)

        def _run():
            import logging as _log
            _log.getLogger("werkzeug").setLevel(_log.WARNING)
            self._app.run(
                host=self._host,
                port=self._port,
                debug=False,
                use_reloader=False,
                threaded=True,
            )

        self._thread = threading.Thread(target=_run, daemon=True, name="AuraDashboard")
        self._thread.start()
        logger.info(
            f"🌐 AURA Web Dashboard: http://localhost:{self._port}  "
            f"(LAN: http://<your-ip>:{self._port})"
        )
        return True

    def stop(self):
        pass  # daemon thread stops automatically


def start_dashboard(aura_respond_fn: Callable, port: int = 5000) -> bool:
    """One-line convenience starter. Returns True on success."""
    db = AuraDashboard(aura_respond_fn, port=port)
    return db.start()
