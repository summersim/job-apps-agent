"""Minimal .env loader — no python-dotenv dependency.

Reads KEY=VALUE lines from a .env file into os.environ without overriding
anything already set in the real environment. Handles comments, blank lines,
an optional leading ``export``, and single/double-quoted values. Anything it
can't parse is skipped silently.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> None:
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)
