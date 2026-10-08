"""Credential-free transcript ingestion and publication primitives.

This module deliberately has no database, HTTP, SDK, or model dependency.  It
defines the deterministic Phase 2 core that those boundaries can call later.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid5

_ID_NAMESPACE = UUID("2ac6baed-8e57-4c50-9bc9-0ce19a839737")
_TIMESTAMP = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$")


class IngestionError(ValueError):
    """Safe validation failure; messages never include uploaded content."""


@dataclass(frozen=True)
class CleanupEdit:
    rule: Literal["filler_removal", "stutter_deduplication"]
    start_character: int
    end_character: int
    source_text: str
    replacement: str


@dataclass(frozen=True)
class CleanupValidation:
    accepted: bool
    policy_version: str
    edits: tuple[CleanupEdit, ...]


@dataclass(frozen=True)
class Segment:
    text: str
    speaker_label: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None


@dataclass(frozen=True)
class ParsedTranscript:
    format: Literal["txt", "vtt", "srt", "json", "provider"]
    language: str
    segments: tuple[Segment, ...]

    @property
    def canonical_text(self) -> str:
        return "\n".join(segment.text for segment in self.segments)


@dataclass(frozen=True)
class ImmutableArtifact:
    artifact_id: UUID
    kind: Literal["uploaded_source", "raw_provider_output", "canonical_transcript"]
    data: bytes
    sha256: str


@dataclass(frozen=True)
class Approval:
    approval_id: UUID
    content_sha256: str
    method: Literal["controlled_cleanup_policy", "person"]
    policy_version: str


@dataclass(frozen=True)
class Passage:
    passage_id: UUID
    ordinal: int
    text: str
    start_byte: int
    end_byte: int


@dataclass(frozen=True)
class IndexJobIntent:
    operation_key: str
    transcript_version_id: UUID
    passage_id: UUID


@dataclass(frozen=True)
class PublishedTranscript:
    transcript_version_id: UUID
    document_id: UUID
    source_artifact_id: UUID
    canonical_artifact: ImmutableArtifact
    approval: Approval
    passages: tuple[Passage, ...]
    index_jobs: tuple[IndexJobIntent, ...]


def _safe_text(data: bytes) -> str:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise IngestionError("invalid_utf8") from error
    if "\x00" in text:
        raise IngestionError("invalid_text_content")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _time_ms(value: str) -> int:
    match = _TIMESTAMP.fullmatch(value.strip())
    if match is None:
        raise IngestionError("invalid_timestamp")
    hours, minutes, seconds, millis = (int(part) for part in match.groups())
    if minutes >= 60 or seconds >= 60:
        raise IngestionError("invalid_timestamp")
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def _timed_blocks(text: str, *, is_vtt: bool) -> tuple[Segment, ...]:
    lines = text.split("\n")
    if is_vtt:
        if not lines or not lines[0].lstrip("\ufeff").startswith("WEBVTT"):
            raise IngestionError("invalid_vtt_header")
        lines = lines[1:]
    blocks = re.split(r"\n[ \t]*\n", "\n".join(lines).strip())
    segments: list[Segment] = []
    for block in blocks:
        parts = [line.strip() for line in block.split("\n") if line.strip()]
        if not parts:
            continue
        timing_index = next((i for i, line in enumerate(parts) if "-->" in line), -1)
        if timing_index < 0 or timing_index == len(parts) - 1:
            if is_vtt and parts[0].startswith(("NOTE", "STYLE", "REGION")):
                continue
            raise IngestionError("invalid_timed_block")
        timing = parts[timing_index].split("-->")
        if len(timing) != 2:
            raise IngestionError("invalid_timestamp")
        start = _time_ms(timing[0])
        end_token = timing[1].strip().split()[0]
        end = _time_ms(end_token)
        if end < start:
            raise IngestionError("invalid_timestamp_range")
        cue_text = "\n".join(parts[timing_index + 1 :])
        segments.append(Segment(cue_text, start_ms=start, end_ms=end))
    if not segments:
        raise IngestionError("empty_transcript")
    return tuple(segments)


def parse_transcript(
    filename: str, data: bytes, *, default_language: str = "en"
) -> ParsedTranscript:
    """Parse a bounded, already-size-checked transcript upload."""

    suffix = Path(filename).suffix.lower()
    text = _safe_text(data)
    if suffix == ".txt":
        if not text.strip():
            raise IngestionError("empty_transcript")
        return ParsedTranscript("txt", default_language, (Segment(text.strip("\n")),))
    if suffix in {".vtt", ".srt"}:
        timed_format: Literal["vtt", "srt"] = "vtt" if suffix == ".vtt" else "srt"
        return ParsedTranscript(
            timed_format, default_language, _timed_blocks(text, is_vtt=suffix == ".vtt")
        )
    if suffix != ".json":
        raise IngestionError("unsupported_transcript_format")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise IngestionError("invalid_json") from error
    if not isinstance(value, dict) or set(value) != {"schema_version", "language", "segments"}:
        raise IngestionError("invalid_transcript_schema")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise IngestionError("unsupported_schema_version")
    if not isinstance(value["language"], str) or not value["language"].strip():
        raise IngestionError("invalid_language")
    if not isinstance(value["segments"], list) or not value["segments"]:
        raise IngestionError("empty_transcript")
    segments: list[Segment] = []
    allowed = {"text", "speaker_label", "start_ms", "end_ms"}
    for item in value["segments"]:
        if not isinstance(item, dict) or not set(item).issubset(allowed) or "text" not in item:
            raise IngestionError("invalid_transcript_segment")
        segment_text = item["text"]
        speaker = item.get("speaker_label")
        start, end = item.get("start_ms"), item.get("end_ms")
        if not isinstance(segment_text, str) or not segment_text:
            raise IngestionError("invalid_transcript_segment")
        if speaker is not None and not isinstance(speaker, str):
            raise IngestionError("invalid_transcript_segment")
        if (start is None) != (end is None):
            raise IngestionError("invalid_timestamp_range")
        if start is not None and (
            type(start) is not int or type(end) is not int or start < 0 or end < start
        ):
            raise IngestionError("invalid_timestamp_range")
        segments.append(Segment(segment_text, speaker, start, end))
    return ParsedTranscript("json", value["language"], tuple(segments))


def conservative_cleanup(text: str) -> str:
    """Apply only deterministic line-ending/trailing-space/blank-line formatting."""

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned: list[str] = []
    blank = False
    for line in lines:
        current = line.rstrip(" \t")
        if not current:
            if cleaned and not blank:
                cleaned.append("")
            blank = True
        else:
            cleaned.append(current)
            blank = False
    return "\n".join(cleaned).strip("\n")


_FILLERS = frozenset({"um", "uh", "erm", "ah"})
_STUTTER_TOKENS = frozenset({"i", "we", "a", "an", "the", "and", "but", "so", "it", "that", "this"})
_WORD = re.compile(r"\b[^\W\d_]+\b", re.UNICODE)


def controlled_cleanup(text: str) -> tuple[str, tuple[CleanupEdit, ...]]:
    """Return the sole automatically approvable policy-v2 cleanup output."""

    formatted = conservative_cleanup(text)
    matches = list(_WORD.finditer(formatted))
    removals: list[tuple[int, int, CleanupEdit]] = []
    previous_kept: re.Match[str] | None = None
    for match in matches:
        token = match.group(0).casefold()
        if token in _FILLERS:
            start, end = match.span()
            if end < len(formatted) and formatted[end] == " ":
                end += 1
            elif start > 0 and formatted[start - 1] == " ":
                start -= 1
            removals.append(
                (start, end, CleanupEdit("filler_removal", start, end, formatted[start:end], ""))
            )
            continue
        if previous_kept is not None and token in _STUTTER_TOKENS:
            between = formatted[previous_kept.end() : match.start()]
            if previous_kept.group(0).casefold() == token and between.isspace():
                start, end = previous_kept.end(), match.end()
                removals.append(
                    (
                        start,
                        end,
                        CleanupEdit(
                            "stutter_deduplication",
                            start,
                            end,
                            formatted[start:end],
                            "",
                        ),
                    )
                )
                continue
        previous_kept = match
    output = formatted
    for start, end, _edit in reversed(removals):
        output = output[:start] + output[end:]
    return output, tuple(item[2] for item in removals)


def transcript_timestamp(milliseconds: int | None) -> str | None:
    """Render a transcript offset without implying sub-second precision."""

    if milliseconds is None:
        return None
    total_seconds = milliseconds // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def transcript_speaker(label: str | None) -> str | None:
    """Turn stable provider-neutral labels into human-readable speaker names."""

    if label is None or not label.strip():
        return None
    value = label.strip()
    match = re.fullmatch(r"speaker[-_ ]?(\d+)", value, re.IGNORECASE)
    if match:
        return f"Speaker {int(match.group(1))}"
    return value


def format_segmented_transcript(
    segments: tuple[Segment, ...], *, markdown: bool = False
) -> str:
    """Format immutable diarization metadata as readable transcript turns."""

    if not segments:
        return ""
    if not any(segment.speaker_label or segment.start_ms is not None for segment in segments):
        return "\n".join(segment.text for segment in segments)

    rendered: list[str] = []
    for segment in segments:
        speaker = transcript_speaker(segment.speaker_label) or "Speaker"
        timestamp = transcript_timestamp(segment.start_ms)
        heading = f"{speaker} · {timestamp}" if timestamp else speaker
        if markdown:
            rendered.append(f"**{heading}**\n\n{segment.text}")
        elif timestamp:
            rendered.append(f"[{timestamp}] {speaker}: {segment.text}")
        else:
            rendered.append(f"{speaker}: {segment.text}")
    return "\n\n".join(rendered)


def validate_cleanup_with_manifest(original: str, proposal: str) -> CleanupValidation:
    """Accept formatting-only output or the exact deterministic policy-v2 output."""

    if "".join(original.split()) == "".join(proposal.split()):
        return CleanupValidation(True, "controlled-cleanup-v2", ())
    expected, edits = controlled_cleanup(original)
    return CleanupValidation(
        proposal == expected, "controlled-cleanup-v2", edits if proposal == expected else ()
    )


def validate_cleanup(original: str, proposal: str) -> bool:
    """Compatibility predicate for the versioned controlled-cleanup validator."""

    return validate_cleanup_with_manifest(original, proposal).accepted


def _artifact(
    kind: Literal["uploaded_source", "raw_provider_output", "canonical_transcript"], data: bytes
) -> ImmutableArtifact:
    digest = sha256(data).hexdigest()
    return ImmutableArtifact(uuid5(_ID_NAMESPACE, f"{kind}:{digest}"), kind, data, digest)


def construct_passages(
    version_id: UUID, text: str, *, max_bytes: int = 1200
) -> tuple[Passage, ...]:
    if max_bytes < 64:
        raise IngestionError("invalid_passage_limit")
    encoded = text.encode("utf-8")
    passages: list[Passage] = []
    start = 0
    ordinal = 0
    while start < len(encoded):
        end = min(start + max_bytes, len(encoded))
        while end > start:
            try:
                chunk = encoded[start:end].decode("utf-8")
                break
            except UnicodeDecodeError:
                end -= 1
        if end == start:
            raise IngestionError("invalid_utf8_boundary")
        if end < len(encoded):
            split = max(chunk.rfind("\n"), chunk.rfind(" "))
            if split > 0:
                end = start + len(chunk[: split + 1].encode("utf-8"))
                chunk = encoded[start:end].decode("utf-8")
        passage_id = uuid5(_ID_NAMESPACE, f"passage:{version_id}:{ordinal}:{start}:{end}")
        passages.append(Passage(passage_id, ordinal, chunk, start, end))
        ordinal += 1
        start = end
    return tuple(passages)


class InMemoryIngestionService:
    """Idempotent synthetic workflow proving the deterministic publication chain."""

    def __init__(self) -> None:
        self._artifacts: dict[UUID, ImmutableArtifact] = {}
        self._publications: dict[tuple[UUID, str], PublishedTranscript] = {}

    def preserve_upload(self, data: bytes) -> ImmutableArtifact:
        artifact = _artifact("uploaded_source", data)
        self._artifacts.setdefault(artifact.artifact_id, artifact)
        return self._artifacts[artifact.artifact_id]

    def preserve_raw_provider_output(self, data: bytes) -> ImmutableArtifact:
        artifact = _artifact("raw_provider_output", data)
        self._artifacts.setdefault(artifact.artifact_id, artifact)
        return self._artifacts[artifact.artifact_id]

    def publish_import(
        self,
        *,
        document_id: UUID,
        filename: str,
        data: bytes,
        cleanup_proposal: str | None = None,
        approval_method: Literal[
            "controlled_cleanup_policy", "person"
        ] = "controlled_cleanup_policy",
        policy_version: str = "controlled-cleanup-v2",
    ) -> PublishedTranscript:
        source = self.preserve_upload(data)
        parsed = parse_transcript(filename, data)
        original = parsed.canonical_text
        proposed = (
            cleanup_proposal if cleanup_proposal is not None else controlled_cleanup(original)[0]
        )
        canonical = proposed if validate_cleanup(original, proposed) else original
        canonical_bytes = canonical.encode("utf-8")
        canonical_artifact = _artifact("canonical_transcript", canonical_bytes)
        self._artifacts.setdefault(canonical_artifact.artifact_id, canonical_artifact)
        version_id = uuid5(_ID_NAMESPACE, f"version:{document_id}:{canonical_artifact.sha256}")
        key = (document_id, canonical_artifact.sha256)
        if prior := self._publications.get(key):
            return prior
        approval = Approval(
            uuid5(_ID_NAMESPACE, f"approval:{version_id}:{approval_method}:{policy_version}"),
            canonical_artifact.sha256,
            approval_method,
            policy_version,
        )
        passages = construct_passages(version_id, canonical)
        jobs = tuple(
            IndexJobIntent(
                f"index:{version_id}:{passage.passage_id}", version_id, passage.passage_id
            )
            for passage in passages
        )
        publication = PublishedTranscript(
            version_id,
            document_id,
            source.artifact_id,
            canonical_artifact,
            approval,
            passages,
            jobs,
        )
        self._publications[key] = publication
        return publication

    def reproduce_canonical_text(self, publication: PublishedTranscript) -> str:
        stored = self._artifacts.get(publication.canonical_artifact.artifact_id)
        if stored is None or sha256(stored.data).hexdigest() != publication.approval.content_sha256:
            raise IngestionError("integrity_failure")
        return stored.data.decode("utf-8")

    def corrupt_for_test(self, artifact_id: UUID, data: bytes) -> None:
        """Fault-injection hook for synthetic integrity tests only."""

        current = self._artifacts[artifact_id]
        self._artifacts[artifact_id] = replace(current, data=data)
