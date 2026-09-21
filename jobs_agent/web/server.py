"""Local review server."""

from __future__ import annotations

import webbrowser
from http.server import ThreadingHTTPServer

from ..config import default_db_path
from .handler import Handler


def serve(db_path: str | None = None, port: int = 8765,
          open_browser: bool = True) -> None:
    db_path = db_path or default_db_path()
    Handler.db_path = db_path
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Serving the job queue UI on {url}  (Ctrl+C to stop)", flush=True)
    print(f"Database: {db_path}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
