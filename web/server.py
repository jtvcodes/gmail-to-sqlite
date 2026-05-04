import argparse
import os
import sys

from flask import Flask, send_from_directory

from web.db import close_db, ensure_indexes
from web.api.messages import messages_bp
from web.api.labels import labels_bp
from web.api.sync import sync_bp

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app(db_path: str) -> Flask:
    """Create and configure the Flask application.

    Parameters
    ----------
    db_path:
        Absolute or relative path to the SQLite database file.
    """
    static_folder = os.path.join(os.path.dirname(__file__), "static")
    app = Flask(__name__, static_folder=static_folder, static_url_path="/static")

    # 2.4 — store DB path in config and register teardown
    app.config["DB_PATH"] = db_path
    app.teardown_appcontext(close_db)

    # Create performance indexes on startup (safe no-op if they already exist)
    ensure_indexes(db_path)

    # 2.5 — register blueprints under /api
    app.register_blueprint(messages_bp, url_prefix="/api")
    app.register_blueprint(labels_bp, url_prefix="/api")
    app.register_blueprint(sync_bp, url_prefix="/api")

    # 2.6 — serve index.html at GET /
    @app.route("/")
    def index():
        return send_from_directory(static_folder, "index.html")

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # 2.2 — parse CLI arguments
    parser = argparse.ArgumentParser(description="Gmail Web Viewer — Flask server")
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)",
    )
    parser.add_argument(
        "--db-path",
        default="data/messages.db",
        help="Path to the SQLite database (default: data/messages.db)",
    )
    args = parser.parse_args()

    # If the DB file doesn't exist yet, start anyway — the frontend will
    # prompt the user to run a sync, which creates the file.
    if not os.path.isfile(args.db_path):
        print(
            f"Note: database file not found at {args.db_path!r}. "
            "Starting server anyway — open the app to run an initial sync.",
            file=sys.stderr,
        )

    app = create_app(db_path=args.db_path)

    # 2.7 — start the development server
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
