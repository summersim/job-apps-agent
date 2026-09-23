"""HTTP plumbing: route table, request parsing, response serialisation.

Two pages:

  /            job review queue — fetch, filter, shortlist/reject, and run
               the review-and-approve workflow below
  /documents   Profile page — candidate name, CV (uploaded as .docx or .pdf,
               text extracted), cover-letter template, and the scoring
               profile, stored once and reused for every draft

Review workflow: "Prepare application" drafts a letter tailored to that
posting (see letters/) and sets it to "drafted". A human reads it, edits it,
and clicks "Approve". Only once a posting is "approved" can it be marked
"submitted" — api.py rejects any attempt to skip that step. Nothing in this
tool ever submits anything itself; "submitted" just records that a human did
so elsewhere, so it stops resurfacing in the queue.

Stdlib only (http.server) beyond what fetch/queue/stats already need.
Drafting additionally needs GEMINI_API_KEY set in the environment.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from ..profile import load_profile
from ..storage import DOC_CANDIDATE_NAME, open_store
from . import api, pages

#: path -> endpoint, per method. Adding an endpoint means one entry here and
#: one function in api.py.
GET_ROUTES = {
    "/api/stats": api.get_stats,
    "/api/queue": api.get_queue,
    "/api/documents": api.get_documents,
    "/api/profile": api.get_profile,
    "/api/cv/file": api.get_cv_file,
}

POST_ROUTES = {
    "/api/fetch": api.post_fetch,
    "/api/status": api.post_status,
    "/api/draft": api.post_draft,
    "/api/redraft": api.post_redraft,
    "/api/letter": api.post_letter,
    "/api/cv": api.post_cv,
    "/api/documents": api.post_documents,
    "/api/profile": api.post_profile,
    "/api/profile/reset": api.post_profile_reset,
}


class Handler(BaseHTTPRequestHandler):
    #: Postgres connection string override; None uses DATABASE_URL from the
    #: environment, resolved lazily by Store on each request.
    db: str | None = None

    def log_message(self, fmt, *args) -> None:  # quiet the default access log
        pass

    # -- responses --------------------------------------------------------

    def _send(self, body: bytes, content_type: str, status: int = 200,
              extra_headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_result(self, result) -> None:
        """Serialise whatever an endpoint returned."""
        if isinstance(result, api.File):
            self._send(
                result.data, result.content_type,
                extra_headers={
                    "Content-Disposition":
                        f'attachment; filename="{result.filename}"',
                },
            )
        else:
            self._send(json.dumps(result.body).encode(),
                       "application/json", result.status)

    def _send_html(self, html: str) -> None:
        self._send(html.encode(), "text/html; charset=utf-8")

    def _not_found(self) -> None:
        self._send(json.dumps({"error": "not found"}).encode(),
                   "application/json", 404)

    # -- routing ----------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            with open_store(self.db) as store:
                name = store.get_document(DOC_CANDIDATE_NAME).strip()
                if not name:
                    name = load_profile(store).name
            self._send_html(pages.queue_page(name))
            return

        if path == "/documents":
            self._send_html(pages.documents_page())
            return

        if path.startswith("/static/"):
            asset = pages.static_asset(path[len("/static/"):])
            if asset is None:
                self._not_found()
                return
            body, content_type = asset
            self._send(body, content_type)
            return

        endpoint = GET_ROUTES.get(path)
        if endpoint is None:
            self._not_found()
            return
        request = api.Request(query=parse_qs(parsed.query))
        with open_store(self.db) as store:
            self._send_result(endpoint(store, request))

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        endpoint = POST_ROUTES.get(path)
        if endpoint is None:
            self._not_found()
            return

        request = api.Request(payload=self._read_json())
        with open_store(self.db) as store:
            self._send_result(endpoint(store, request))

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
