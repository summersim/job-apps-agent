"""Persistence layer: SQLite schema, the Store, and document ids."""

from .store import (
    DOC_CANDIDATE_NAME,
    DOC_CV,
    DOC_CV_FILENAME,
    DOC_TEMPLATE,
    Store,
    open_store,
)

__all__ = [
    "DOC_CANDIDATE_NAME",
    "DOC_CV",
    "DOC_CV_FILENAME",
    "DOC_TEMPLATE",
    "Store",
    "open_store",
]
