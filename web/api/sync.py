import os
import subprocess
import sys
import threading

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

sync_bp = Blueprint("sync", __name__)

_VALID_MODES = {"new", "delta", "force", "test"}


# ---------------------------------------------------------------------------
# Sync session — keeps the subprocess alive independently of any SSE
# connection. New connections replay the buffered log then tail live.
# ---------------------------------------------------------------------------

class SyncSession:
    """Manages a single running sync subprocess and its output buffer."""

    def __init__(self, mode: str, cmd: list, cwd: str, env: dict):
        self.mode = mode
        self.lines: list[str] = []
        self.exit_code: int | None = None
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

    @property
    def running(self) -> bool:
        return self.exit_code is None

    def kill(self):
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    def tail(self, from_line: int = 0):
        """Yield (line_index, line) starting from from_line, blocking until
        new lines arrive or the process finishes."""
        idx = from_line
        while True:
            with self._cond:
                while idx < len(self.lines):
                    yield idx, self.lines[idx]
                    idx += 1
                if self.exit_code is not None and idx >= len(self.lines):
                    return
                self._cond.wait(timeout=1.0)


# Global session — only one sync runs at a time
_session: SyncSession | None = None
_session_lock = threading.Lock()


def get_or_start_session(mode: str, cmd: list, cwd: str, env: dict) -> SyncSession:
    """Return the running session if it matches mode, otherwise start a new one."""
    global _session
    with _session_lock:
        if _session is not None and _session.running and _session.mode == mode:
            return _session
        if _session is not None:
            _session.kill()
        _session = SyncSession(mode, cmd, cwd, env)
        return _session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_cmd(mode: str, main_py: str, data_dir: str, workers: int = 20, test_limit: int = 10000) -> list:
    base = [sys.executable, main_py, "sync", "--data-dir", data_dir, "--workers", str(workers)]
    if mode == "new":
        # Fetch only messages newer than the last synced timestamp
        return base + ["--delta"]
    elif mode == "delta":
        # All missing messages + updates on existing (default full sync via history API)
        return base
    elif mode == "force":
        # Re-download and replace everything
        return base + ["--force"]
    elif mode == "test":
        # Force re-download of a limited number of messages
        return base + ["--force", "--test", str(test_limit)]
    return base


def _resolve_paths(db_path: str):
    abs_db = os.path.abspath(db_path)
    data_dir = os.path.dirname(abs_db)
    workspace_root = os.path.dirname(data_dir)
    main_py = os.path.join(workspace_root, "main.py")
    return main_py, data_dir, workspace_root


# ---------------------------------------------------------------------------
# POST /api/sync/stop
# ---------------------------------------------------------------------------

@sync_bp.route("/sync/stop", methods=["POST"])
def stop_sync():
    """Kill the running sync process if one is active."""
    with _session_lock:
        if _session is not None and _session.running:
            _session.kill()
            return jsonify({"ok": True, "message": "Sync process stopped."})
    return jsonify({"ok": False, "message": "No sync is currently running."})

@sync_bp.route("/sync/status")
def sync_status():
    """Return whether a sync is currently running."""
    with _session_lock:
        if _session is not None and _session.running:
            progress_label = None
            sync_total = 0
            sync_done = 0
            with _session._lock:
                for line in _session.lines:
                    import re
                    m = re.search(r"Found (\d+) messages? to sync\.", line)
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


# ---------------------------------------------------------------------------
# POST /api/sync
# ---------------------------------------------------------------------------

@sync_bp.route("/sync", methods=["POST"])
def run_sync():
    """Non-streaming sync — runs to completion and returns output."""
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

    try:
        test_limit = int(body.get("test_limit", 10000))
        if test_limit < 1:
            return jsonify({"error": "'test_limit' must be >= 1"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "'test_limit' must be an integer"}), 400

    db_path = current_app.config["DB_PATH"]
    main_py, data_dir, workspace_root = _resolve_paths(db_path)

    if not os.path.isfile(main_py):
        return jsonify({"error": f"main.py not found at {main_py}"}), 500

    cmd = _build_cmd(mode, main_py, data_dir, workers, test_limit)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    try:
        result = subprocess.run(
            cmd,
            cwd=workspace_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Sync timed out after 5 minutes"}), 504
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        return jsonify({"error": "Sync failed", "output": output}), 500
    return jsonify({"ok": True, "output": output})


# ---------------------------------------------------------------------------
# GET /api/sync/stream
# ---------------------------------------------------------------------------

@sync_bp.route("/sync/stream")
def stream_sync():
    """Stream sync output as SSE.

    If a sync for this mode is already running, replays buffered output from
    line ?from=<n> (default 0) then tails live — no new process is spawned.
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

    try:
        test_limit = int(request.args.get("test_limit", 10000))
        if test_limit < 1:
            test_limit = 10000
    except (ValueError, TypeError):
        test_limit = 10000

    db_path = current_app.config["DB_PATH"]
    main_py, data_dir, workspace_root = _resolve_paths(db_path)

    if not os.path.isfile(main_py):
        def _err():
            yield f"event: error\ndata: main.py not found at {main_py}\n\n"
        return Response(stream_with_context(_err()), mimetype="text/event-stream")

    cmd = _build_cmd(mode, main_py, data_dir, workers, test_limit)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}

    session = get_or_start_session(mode, cmd, workspace_root, env)

    def generate():
        for idx, line in session.tail(from_line=from_line):
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
