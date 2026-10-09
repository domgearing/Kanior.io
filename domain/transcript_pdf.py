"""Readable PDF rendering of an already authorized, immutable transcript."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer
from reportlab.platypus.doctemplate import BaseDocTemplate

from domain.ingestion import Segment, transcript_speaker, transcript_timestamp

_FONT_NAME = "VereloVera"


def _font() -> TTFont:
    if _FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
        pdfmetrics.registerFont(TTFont(_FONT_NAME, str(path)))
    font = pdfmetrics.getFont(_FONT_NAME)
    assert isinstance(font, TTFont)
    return font


def _supported(text: str, font: TTFont) -> bool:
    glyphs = font.face.charToGlyph
    return all(character in "\n\r\t" or ord(character) in glyphs for character in text)


def render_transcript_pdf(
    title: str,
    canonical_text: str,
    segments: tuple[Segment, ...],
    version_id: str,
    content_sha256: str,
) -> bytes:
    """Never substitute unapproved segment wording for canonical text."""

    font = _font()
    values = (title, canonical_text, version_id, content_sha256)
    if not all(_supported(value, font) for value in values):
        raise ValueError("pdf_unsupported_character")
    organized = bool(segments) and "\n".join(item.text for item in segments) == canonical_text
    stream = BytesIO()
    document = SimpleDocTemplate(
        stream,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=62,
        bottomMargin=58,
        title=title,
        author="Verelo",
    )
    heading = ParagraphStyle(
        "heading",
        fontName=_FONT_NAME,
        fontSize=17,
        leading=22,
        textColor=colors.HexColor("#172235"),
    )
    metadata = ParagraphStyle(
        "metadata",
        fontName=_FONT_NAME,
        fontSize=8,
        leading=12,
        textColor=colors.HexColor("#526173"),
        spaceAfter=4,
    )
    speaker = ParagraphStyle(
        "speaker",
        fontName=_FONT_NAME,
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#27465E"),
        spaceBefore=13,
        spaceAfter=4,
        keepWithNext=True,
    )
    body = ParagraphStyle(
        "body",
        fontName=_FONT_NAME,
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#172235"),
        spaceAfter=10,
        splitLongWords=True,
    )
    story: list[Flowable] = [
        Paragraph(escape(title), heading),
        Spacer(1, 10),
        Paragraph(f"Transcript version: {escape(version_id)}", metadata),
        Paragraph(f"Content SHA-256: {escape(content_sha256)}", metadata),
        Spacer(1, 15),
    ]
    if organized:
        for item in segments:
            label = transcript_speaker(item.speaker_label) or "Speaker"
            time = transcript_timestamp(item.start_ms)
            header = f"{label} - {time}" if time else label
            if not _supported(header, font):
                raise ValueError("pdf_unsupported_character")
            story.append(Paragraph(escape(header), speaker))
            story.append(Paragraph(escape(item.text).replace("\n", "<br/>"), body))
    else:
        for line in canonical_text.split("\n"):
            story.append(Paragraph(escape(line) or "&#160;", body))

    def footer(canvas: Canvas, doc: BaseDocTemplate) -> None:
        canvas.saveState()
        canvas.setFont(_FONT_NAME, 8)
        canvas.setFillColor(colors.HexColor("#526173"))
        canvas.drawRightString(letter[0] - 54, 34, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
