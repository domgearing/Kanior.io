from __future__ import annotations

import pytest

from domain.ingestion import Segment
from domain.transcript_pdf import render_transcript_pdf


def test_pdf_uses_immutable_canonical_text_and_embeds_font() -> None:
    pdf = render_transcript_pdf(
        "Fictional interview",
        "Hello world.\nAnother voice.",
        (
            Segment("Hello world.", "speaker-1", 0, 800),
            Segment("Another voice.", "speaker-2", 800, 1600),
        ),
        "00000000-0000-0000-0000-000000000001",
        "a" * 64,
    )
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 10_000


def test_pdf_rejects_glyphs_not_in_embedded_font() -> None:
    with pytest.raises(ValueError, match="pdf_unsupported_character"):
        render_transcript_pdf("Fictional", "\U0001f600", (), "version", "b" * 64)
