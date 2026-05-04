import os
import subprocess
import sys
import threading

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from web.db import ensure_indexes, invalidate_count_cache

sync_bp = Blueprint("sync", __name__)

_VALID_MODES = {"delta", "force", "missing", "test"}


# ---------------------------------------------------------------------------
# Server-side sync session — keeps the subprocess alive independently of any
# SSE connection.  New connections replay the buffered log then tail live.
# ---------------------------------------------------------------------------

class SyncSession:
    """Manages a single running sync subprocess and its output buffer."""

    def __init__(self, mode: str, cmd: list, cwd: str, env: dict):
        self.mode = mode
        self.lines: list[str] = []          # full output buffer
        self.exit_code: int | None = None   # None while running
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._proc: subprocess.Popen | None = None
        self._thread = threading.Thread(target=self._run, args=(cmd, cwd, env), daemon=True)
        self._thread.start()

    def _run(self, cmd, cwd, env):
        try:
            self._proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            for line in self._proc.stdout:
                stripped = line.rstrip()
                with self._cond:
                    self.lines.append(stripped)
                    self._cond.notify_all()
            self._proc.wait()
            rc = self._proc.returncode
        except Exception as e:
            rc = 1
            with self._cond:
                self.lines.append(f"ERROR: {e}")
                self._cond.notify_all()
        finally:
            with self._cond:
                self.exit_code = rc
                self._cond.notify_all()
            # Invalidate the count cache and rebuild indexes so the UI
            # shows fresh totals immediately after sync completes.
            try:
                from flask import current_app
                db_path = current_app.config.get("DB_PATH", "")
                if db_path:
                    ensure_indexes(db_path)
            except RuntimeError:
                pass  # No app context outside a request — safe to skip
            invalidate_count_cache()

    @property
    def running(self) -> bool:
        return self.exit_code is None

    def kill(self):
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    def tail(self, from_line: int = 0):
        """Generator: yields (line_index, line) starting from from_line, then
        blocks until new lines arrive or the process finishes."""
        idx = from_line
        while True:
            with self._cond:
                # Yield any buffered lines we haven't sent yet
                while idx < len(self.lines):
                    yield idx, self.lines[idx]
                    idx += 1
                # If process finished and we've sent everything, stop
                if self.exit_code is not None and idx >= len(self.lines):
                    return
                # Wait for more output
                self._cond.wait(timeout=1.0)


# Global session — only one sync runs at a time
_session: SyncSession | None = None
_session_lock = threading.Lock()


def get_or_start_session(mode: str, cmd: list, cwd: str, env: dict) -> SyncSession:
    """Return the running session if it matches mode, otherwise start a new one."""
    global _session
    with _session_lock:
        if _session is not None and _session.running and _session.mode == mode:
            return _session          # reuse existing session
        if _session is not None:
            _session.kill()          # kill stale session
        _session = SyncSession(mode, cmd, cwd, env)
        return _session


def get_active_session(mode: str) -> SyncSession | None:
    """Return the active session for mode if one is running, else None."""
    with _session_lock:
        if _session is not None and _session.mode == mode:
            return _session
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_cmd(mode: str, main_py: str, data_dir: str, workers: int = 20) -> list:
    if mode == "delta":
        return [sys.executable, main_py, "sync", "--delta", "--data-dir", data_dir, "--workers", str(workers)]
    elif mode == "force":
        return [sys.executable, main_py, "sync", "--force", "--data-dir", data_dir, "--workers", str(workers)]
    elif mode == "test":
        return [sys.executable, main_py, "sync", "--test", "10000", "--data-dir", data_dir, "--workers", str(workers)]
    else:  # "missing"
        return [sys.executable, main_py, "sync", "--data-dir", data_dir, "--workers", str(workers)]


def _resolve_paths(db_path: str):
    abs_db = os.path.abspath(db_path)
    data_dir = os.path.dirname(abs_db)
    workspace_root = os.path.dirname(data_dir)
    main_py = os.path.join(workspace_root, "main.py")
    return main_py, data_dir, workspace_root


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@sync_bp.route("/sync/status")
def sync_status():
    """GET /api/sync/status — returns whether a sync is currently running."""
    with _session_lock:
        if _session is not None and _session.running:
            # Scan buffered lines for latest progress
            progress_label = None
            sync_total = 0
            sync_done = 0
            with _session._lock:
                for line in _session.lines:
                    m = __import__("re").search(r"Found (\d+) messages? to sync\.", line)
                    if m:
                        sync_total = int(m.group(1))
                        sync_done = 0
                    if sync_total > 0 and "Successfully synced message" in line:
                        sync_done += 1
            if sync_total > 0:
                progress_label = f"Syncing messages {sync_done} of {sync_total}…"
            return jsonify({
                "running": True,
                "mode": _session.mode,
                "progress_label": progress_label,
            })
    return jsonify({"running": False})


@sync_bp.route("/sync", methods=["POST"])
def run_sync():
    """POST /api/sync — legacy non-streaming endpoint."""
    body = request.get_json(silent=True, force=True) or {}
    mode = body.get("mode", "missing")

    if mode not in _VALID_MODES:
        return jsonify({"error": f"Invalid mode {mode!r}."}), 400

    try:
        workers = int(body.get("workers", 20))
        if not (1 <= workers <= 30):
            return jsonify({"error": "'workers' must be between 1 and 30"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "'workers' must be an integer"}), 400

    db_path = current_app.config["DB_PATH"]
    main_py, data_dir, workspace_root = _resolve_paths(db_path)

    if not os.path.isfile(main_py):
        return jsonify({"error": f"main.py not found at {main_py}"}), 500

    cmd = _build_cmd(mode, main_py, data_dir, workers)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    try:
        result = subprocess.run(
            cmd, cwd=workspace_root, capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=300, env=env,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Sync timed out after 5 minutes"}), 504
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    if result.returncode != 0:
        return jsonify({"error": "Sync failed", "output": (result.stdout + result.stderr).strip()}), 500
    return jsonify({"ok": True, "output": (result.stdout + result.stderr).strip()})


@sync_bp.route("/sync/stream")
def stream_sync():
    """GET /api/sync/stream?mode=<mode>[&from=<line>]

    Streams sync output as SSE.  If a sync for this mode is already running,
    the new connection replays buffered output from line <from> (default 0)
    then tails live — no new process is spawned.

    A final ``event: done`` carries the exit code.
    """
    mode = request.args.get("mode", "missing")

    if mode not in _VALID_MODES:
        def _err():
            yield f"event: error\ndata: Invalid mode {mode!r}.\n\n"
        return Response(stream_with_context(_err()), mimetype="text/event-stream")

    try:
        from_line = int(request.args.get("from", 0))
    except (ValueError, TypeError):
        from_line = 0

    try:
        workers = int(request.args.get("workers", 20))
        if not (1 <= workers <= 30):
            workers = 20
    except (ValueError, TypeError):
        workers = 20

    db_path = current_app.config["DB_PATH"]
    main_py, data_dir, workspace_root = _resolve_paths(db_path)

    if not os.path.isfile(main_py):
        def _err():
            yield f"event: error\ndata: main.py not found at {main_py}\n\n"
        return Response(stream_with_context(_err()), mimetype="text/event-stream")

    cmd = _build_cmd(mode, main_py, data_dir, workers)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    session = get_or_start_session(mode, cmd, workspace_root, env)

    def generate():
        for idx, line in session.tail(from_line=from_line):
            # Send line index as SSE id so client knows where to resume
            yield f"id: {idx}\ndata: {line}\n\n"
        yield f"event: done\ndata: {session.exit_code}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
