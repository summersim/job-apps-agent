"""Local web UI: pages, API endpoints, and the server that hosts them."""

from .handler import Handler
from .server import serve

__all__ = ["Handler", "serve"]
