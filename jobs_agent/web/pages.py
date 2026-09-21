"""HTML pages and static assets.

The markup, styles, and scripts live in ``static/`` as real files rather than
as Python string literals, so an editor can highlight and lint them. Pages
are read from disk on each request: they're a few kilobytes, and editing the
UI without restarting the server is worth more than the saved syscall.
"""

from __future__ import annotations

from html import escape
from pathlib import Path

STATIC_DIR = Path(__file__).parent / "static"

CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".html": "text/html; charset=utf-8",
}

#: Site navigation, as (path, label, page key).
NAV_ITEMS = (
    ("/", "Job Queue", "queue"),
    ("/documents", "Profile", "documents"),
)


def nav(active: str) -> str:
    links = []
    for path, label, key in NAV_ITEMS:
        cls = ' class="active"' if key == active else ""
        links.append(f'<a href="{path}"{cls}>{label}</a>')
    return ('<nav class="topnav"><span class="brand">Jobs Agent</span>'
            + "".join(links) + "</nav>")


def render(name: str, **fields: str) -> str:
    """Read ``static/<name>`` and substitute ``{placeholder}`` tokens.

    Plain replacement rather than ``str.format`` so that braces in the markup
    — or in any script that later moves inline — aren't interpreted.
    """
    html = (STATIC_DIR / name).read_text()
    for key, value in fields.items():
        html = html.replace("{" + key + "}", value)
    return html


def queue_page(candidate_name: str) -> str:
    return render("queue.html", nav=nav("queue"),
                  candidate_name=escape(candidate_name))


def documents_page() -> str:
    return render("documents.html", nav=nav("documents"))


def static_asset(name: str) -> tuple[bytes, str] | None:
    """Bytes and content type for ``/static/<name>``, or None if it's not a
    servable asset.

    Only plain filenames of a known type resolve, so a crafted path can't
    walk out of ``static/``.
    """
    path = STATIC_DIR / name
    if "/" in name or "\\" in name or name.startswith("."):
        return None
    content_type = CONTENT_TYPES.get(path.suffix)
    if content_type is None or not path.is_file():
        return None
    return path.read_bytes(), content_type
