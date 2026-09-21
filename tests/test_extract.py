"""CV extraction: magic bytes decide the reader, not the file extension."""

import io
import zipfile

import pytest

from jobs_agent.extract import CvExtractError, extract_cv_text
from jobs_agent.extract.docx import DocxError
from jobs_agent.extract.docx import extract_text as docx_text

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def make_docx(paragraphs: list[str]) -> bytes:
    body = "".join(
        f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs
    )
    xml = (
        '<?xml version="1.0"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", xml)
    return buf.getvalue()


def test_docx_paragraphs_become_lines():
    assert docx_text(make_docx(["Jane Smith", "Paralegal"])) == "Jane Smith\nParalegal"


def test_a_mislabelled_docx_is_still_read():
    """Magic bytes win: a .docx named .pdf still extracts."""
    assert extract_cv_text("cv.pdf", make_docx(["Jane Smith"])) == "Jane Smith"


def test_unrecognised_bytes_are_rejected():
    with pytest.raises(CvExtractError):
        extract_cv_text("cv.txt", b"just some text")


def test_junk_claiming_to_be_docx_is_rejected():
    with pytest.raises(CvExtractError):
        extract_cv_text("cv.docx", b"not a zip at all")


def test_a_zip_without_a_document_part_is_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.txt", "hi")
    with pytest.raises(DocxError):
        docx_text(buf.getvalue())
