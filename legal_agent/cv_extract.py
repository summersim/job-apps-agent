"""Turn an uploaded CV file into plain text for the drafting prompt.

Accepts .docx and .pdf. The file's magic bytes decide how to read it (a PDF
starts with %PDF, a .docx is a zip and starts with PK), so a
mislabelled-but-valid file still works; the extension is only a fallback for
bytes we can't recognise.
"""

from __future__ import annotations

from .docx_text import DocxError
from .docx_text import extract_text as _docx_text
from .pdf_text import PdfError
from .pdf_text import extract_text as _pdf_text

ALLOWED = ("docx", "pdf")


class CvExtractError(ValueError):
    """The upload wasn't a readable .docx or .pdf."""


def _ext(filename: str) -> str:
    return filename.lower().rsplit(".", 1)[-1] if "." in filename else ""


def extract_cv_text(filename: str, data: bytes) -> str:
    if data[:4] == b"%PDF":
        kind = "pdf"
    elif data[:2] == b"PK":
        kind = "docx"
    elif _ext(filename) in ALLOWED:
        kind = _ext(filename)
    else:
        raise CvExtractError("Only .docx and .pdf files are supported.")

    try:
        return _pdf_text(data) if kind == "pdf" else _docx_text(data)
    except (DocxError, PdfError) as e:
        raise CvExtractError(str(e)) from e
