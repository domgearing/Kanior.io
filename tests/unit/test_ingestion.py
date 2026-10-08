from uuid import uuid4

import pytest

from domain.ingestion import (
    IngestionError,
    InMemoryIngestionService,
    Segment,
    construct_passages,
    controlled_cleanup,
    format_segmented_transcript,
    parse_transcript,
    validate_cleanup,
)


def test_formats_diarized_segments_for_text_and_markdown() -> None:
    segments = (
        Segment("Welcome everyone.", "speaker-1", 0, 900),
        Segment("Thanks for having me.", "speaker-2", 65_000, 67_000),
    )
    assert format_segmented_transcript(segments) == (
        "[00:00] Speaker 1: Welcome everyone.\n\n"
        "[01:05] Speaker 2: Thanks for having me."
    )
    assert format_segmented_transcript(segments, markdown=True) == (
        "**Speaker 1 · 00:00**\n\nWelcome everyone.\n\n"
        "**Speaker 2 · 01:05**\n\nThanks for having me."
    )


def test_segment_format_falls_back_to_plain_text_without_metadata() -> None:
    assert format_segmented_transcript((Segment("First"), Segment("Second"))) == "First\nSecond"


def test_parses_txt_vtt_srt_and_json() -> None:
    txt = parse_transcript("call.txt", "Hello 🌍".encode())
    vtt = parse_transcript("call.vtt", b"WEBVTT\n\n00:00:00.000 --> 00:00:01.250\nHello\n")
    srt = parse_transcript("call.srt", b"1\n00:00:00,000 --> 00:00:01,250\nHello\n")
    raw_json = (
        b'{"schema_version":1,"language":"en","segments":'
        b'[{"text":"Hello","speaker_label":"A","start_ms":0,"end_ms":1250}]}'
    )
    parsed_json = parse_transcript("call.json", raw_json)
    assert txt.canonical_text == "Hello 🌍"
    assert vtt.segments[0].end_ms == srt.segments[0].end_ms == 1250
    assert parsed_json.segments[0].speaker_label == "A"


@pytest.mark.parametrize(
    ("name", "data", "code"),
    [
        ("call.pdf", b"text", "unsupported_transcript_format"),
        ("call.txt", b"\xff", "invalid_utf8"),
        ("call.vtt", b"not vtt", "invalid_vtt_header"),
        ("call.json", b"{}", "invalid_transcript_schema"),
    ],
)
def test_rejects_invalid_imports_without_echoing_content(name: str, data: bytes, code: str) -> None:
    with pytest.raises(IngestionError, match=f"^{code}$"):
        parse_transcript(name, data)


def test_cleanup_validator_rejects_wording_and_punctuation_changes() -> None:
    assert validate_cleanup("Hello,  world!\n", "Hello, world!")
    assert not validate_cleanup("fifteen", "fifty")
    assert not validate_cleanup("Hello, world", "Hello world")


def test_controlled_cleanup_accepts_only_versioned_filler_and_stutter_rules() -> None:
    original = "Um I I think the value is fifteen, not fifty."
    cleaned, manifest = controlled_cleanup(original)
    assert cleaned == "I think the value is fifteen, not fifty."
    assert [edit.rule for edit in manifest] == ["filler_removal", "stutter_deduplication"]
    assert validate_cleanup(original, cleaned)
    assert not validate_cleanup(original, "I think the value is 15, not 50.")
    assert not validate_cleanup(original, "I think the value is fifty, not fifteen.")
    assert not validate_cleanup(original, "I think the value is fifteen.")


def test_controlled_cleanup_protects_emphasis_names_numbers_and_modality() -> None:
    for original, proposal in (
        ("Very very important", "Very important"),
        ("Alex Alex replied", "Alex replied"),
        ("It must ship", "It should ship"),
        ("There are 15", "There are fifteen"),
    ):
        assert not validate_cleanup(original, proposal)


def test_publication_is_immutable_idempotent_and_reproducible() -> None:
    service = InMemoryIngestionService()
    document_id = uuid4()
    first = service.publish_import(
        document_id=document_id, filename="call.txt", data=b"alpha  \r\n\r\nbeta"
    )
    second = service.publish_import(
        document_id=document_id, filename="call.txt", data=b"alpha  \r\n\r\nbeta"
    )
    assert first == second
    assert service.reproduce_canonical_text(first) == "alpha\n\nbeta"
    assert first.approval.content_sha256 == first.canonical_artifact.sha256
    assert len({job.operation_key for job in first.index_jobs}) == len(first.passages)


def test_invalid_cleanup_falls_back_to_unchanged_parsed_text() -> None:
    service = InMemoryIngestionService()
    published = service.publish_import(
        document_id=uuid4(), filename="call.txt", data=b"fifteen", cleanup_proposal="fifty"
    )
    assert service.reproduce_canonical_text(published) == "fifteen"


def test_integrity_failure_blocks_reproduction() -> None:
    service = InMemoryIngestionService()
    published = service.publish_import(document_id=uuid4(), filename="call.txt", data=b"truth")
    service.corrupt_for_test(published.canonical_artifact.artifact_id, b"changed")
    with pytest.raises(IngestionError, match="^integrity_failure$"):
        service.reproduce_canonical_text(published)


def test_passage_offsets_reconstruct_exact_utf8_bytes() -> None:
    text = ("Cafe\u0301 🌍 line\n" * 20).strip()
    passages = construct_passages(uuid4(), text, max_bytes=64)
    source = text.encode("utf-8")
    assert b"".join(source[p.start_byte : p.end_byte] for p in passages) == source
    assert all(source[p.start_byte : p.end_byte].decode("utf-8") == p.text for p in passages)
