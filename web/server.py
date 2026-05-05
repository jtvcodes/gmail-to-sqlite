import argparse
import os
import sys

from flask import Flask, send_from_directory

from web.db import close_db
from web.api.messages import messages_bp
from web.api.labels import labels_bp
from web.api.sync import sync_bp


def create_app(db_path: str) -> Flask:
    """Create and configure the Flask application."""
    static_folder = os.path.join(os.path.dirname(__file__), "static")
    app = Flask(__name__, static_folder=static_folder, static_url_path="/static")

    app.config["DB_PATH"] = db_path
    app.teardown_appcontext(close_db)

    app.register_blueprint(messages_bp, url_prefix="/api")
    app.register_blueprint(labels_bp, url_prefix="/api")
    app.register_blueprint(sync_bp, url_prefix="/api")

    @app.route("/")
    def index():
        return send_from_directory(static_folder, "index.html")

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Arkchive — Flask server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db-path", default="data/messages.db")
    args = parser.parse_args()

    if not os.path.isfile(args.db_path):
        print(
            f"Note: database file not found at {args.db_path!r}. "
            "Starting server anyway — open the app to run an initial sync.",
            file=sys.stderr,
        )

    app = create_app(db_path=args.db_path)
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
