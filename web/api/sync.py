import os
import subprocess
import sys

from flask import Blueprint, current_app, jsonify

sync_bp = Blueprint("sync", __name__)


@sync_bp.route("/sync", methods=["POST"])
def run_sync():
    """POST /api/sync — run `python main.py sync --data-dir ./data` and return output."""
    db_path = current_app.config["DB_PATH"]

    # Derive workspace root: the directory that contains the `data/` folder.
    # db_path is something like /abs/path/to/data/messages.db or data/messages.db.
    abs_db = os.path.abspath(db_path)
    data_dir = os.path.dirname(abs_db)          # .../data
    workspace_root = os.path.dirname(data_dir)  # .../

    main_py = os.path.join(workspace_root, "main.py")
    if not os.path.isfile(main_py):
        return jsonify({"error": f"main.py not found at {main_py}"}), 500

    try:
        result = subprocess.run(
            [sys.executable, main_py, "sync", "--data-dir", data_dir],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,  # 5-minute timeout
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Sync timed out after 5 minutes"}), 504
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        return jsonify({"error": output or "Sync failed"}), 500

    output = (result.stdout + result.stderr).strip()
    return jsonify({"ok": True, "output": output})
