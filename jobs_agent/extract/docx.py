"""Extract plain text from a .docx file, standard library only.

A .docx is a zip archive; the body is word/document.xml in WordprocessingML.
We take the text out of <w:t> runs, break lines on paragraphs and <w:br>,
and turn <w:tab> into tabs. Styles, images, and table structure are dropped
— the output is meant to be fed to a model, not rendered. The old binary
.doc format is not supported.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from xml.etree import ElementTree

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DocxError(ValueError):
    """The bytes given were not a readable .docx file."""


def extract_text(data: bytes) -> str:
    try:
        zf = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as e:
        raise DocxError("not a .docx file (not a zip archive)") from e

    try:
        xml = zf.read("word/document.xml")
    except KeyError as e:
        raise DocxError("not a .docx file (no word/document.xml)") from e

    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as e:
        raise DocxError(f"malformed .docx: {e}") from e

    lines: list[str] = []
    for para in root.iter(f"{_W}p"):
        parts: list[str] = []
        for node in para.iter():
            if node.tag == f"{_W}t":
                parts.append(node.text or "")
            elif node.tag == f"{_W}tab":
                parts.append("\t")
            elif node.tag in (f"{_W}br", f"{_W}cr"):
                parts.append("\n")
        lines.append("".join(parts))

    text = "\n".join(lines)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()
