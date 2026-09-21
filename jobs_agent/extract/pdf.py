"""Extract plain text from a PDF, via pypdf.

Works on PDFs with a real text layer — anything produced by Word, LaTeX,
Google Docs, or a "print to PDF". A scanned or image-only CV has no text to
pull and raises PdfError; that needs OCR, which is out of scope here.
"""

from __future__ import annotations

import logging
from io import BytesIO

# pypdf logs recoverable oddities (missing EOF marker, etc.) at WARNING to
# stderr; we surface real failures as PdfError, so keep its noise out of the
# server console.
logging.getLogger("pypdf").setLevel(logging.ERROR)


class PdfError(ValueError):
    """The bytes given were not a readable PDF (or had no extractable text)."""


def extract_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover - dependency is declared
        raise PdfError("the 'pypdf' package is not installed") from e

    try:
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted:
            # Many PDFs are "encrypted" only with an empty owner password.
            if reader.decrypt("") == 0:
                raise PdfError("the PDF is password-protected")
        pages = [page.extract_text() or "" for page in reader.pages]
    except PdfError:
        raise
    except Exception as e:  # pypdf raises assorted low-level errors on junk
        raise PdfError(f"could not read the PDF: {e}") from e

    text = "\n".join(pages)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()
