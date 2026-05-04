import os
import subprocess
import sys

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

sync_bp = Blueprint("sync", __name__)

_VALID_MODES = {"delta", "force", "missing"}


def _build_cmd(mode: str, main_py: str, data_dir: str) -> list:
    if mode == "delta":
        return [sys.executable, main_py, "sync", "--delta", "--data-dir", data_dir]
    elif mode == "force":
        return [sys.executable, main_py, "sync", "--force", "--data-dir", data_dir]
    else:  # "missing"
        return [sys.executable, main_py, "sync", "--data-dir", data_dir]


def _resolve_paths(db_path: str):
    """Return (main_py, data_dir, workspace_root) from the configured DB path."""
    abs_db = os.path.abspath(db_path)
    data_dir = os.path.dirname(abs_db)
    workspace_root = os.path.dirname(data_dir)
    main_py = os.path.join(workspace_root, "main.py")
    return main_py, data_dir, workspace_root


@sync_bp.route("/sync", methods=["POST"])
def run_sync():
    """POST /api/sync — run sync and return all output at once (legacy / non-streaming).

    Accepts an optional JSON body with a ``mode`` field:
      - ``"delta"``   → ``main.py sync --delta --data-dir <data_dir>``
      - ``"force"``   → ``main.py sync --force --data-dir <data_dir>``
      - ``"missing"`` (or absent) → ``main.py sync --data-dir <data_dir>``

    Any other value returns HTTP 400.
    """
    body = request.get_json(silent=True, force=True) or {}
    mode = body.get("mode", "missing")

    if mode not in _VALID_MODES:
        return (
            jsonify(
                {
                    "error": (
                        f"Invalid mode {mode!r}. Must be one of: delta, force, missing."
                    )
                }
            ),
            400,
        )

    db_path = current_app.config["DB_PATH"]
    main_py, data_dir, workspace_root = _resolve_paths(db_path)

    if not os.path.isfile(main_py):
        return jsonify({"error": f"main.py not found at {main_py}"}), 500

    cmd = _build_cmd(mode, main_py, data_dir)

    try:
        result = subprocess.run(
            cmd,
            cwd=workspace_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Sync timed out after 5 minutes"}), 504
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        return jsonify({"error": "Sync failed", "output": output}), 500

    output = (result.stdout + result.stderr).strip()
    return jsonify({"ok": True, "output": output})


@sync_bp.route("/sync/stream")
def stream_sync():
    """GET /api/sync/stream?mode=<mode> — stream sync output as Server-Sent Events.

    Each line of stdout/stderr is sent as an SSE ``data:`` event.
    A final ``event: done`` event carries the exit code.
    """
    mode = request.args.get("mode", "missing")

    if mode not in _VALID_MODES:
        # SSE can't return a 400 easily once streaming starts, so send an error event
        def _err():
            yield f"event: error\ndata: Invalid mode {mode!r}. Must be one of: delta, force, missing.\n\n"
        return Response(stream_with_context(_err()), mimetype="text/event-stream")

    db_path = current_app.config["DB_PATH"]
    main_py, data_dir, workspace_root = _resolve_paths(db_path)

    if not os.path.isfile(main_py):
        def _err():
            yield f"event: error\ndata: main.py not found at {main_py}\n\n"
        return Response(stream_with_context(_err()), mimetype="text/event-stream")

    cmd = _build_cmd(mode, main_py, data_dir)

    def generate():
        proc = subprocess.Popen(
            cmd,
            cwd=workspace_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # merge stderr into stdout
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        try:
            for line in proc.stdout:
                # Strip trailing newline; SSE adds its own
                yield f"data: {line.rstrip()}\n\n"
            proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

        yield f"event: done\ndata: {proc.returncode}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if behind a proxy
        },
    )
