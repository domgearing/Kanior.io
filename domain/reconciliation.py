"""Deterministic reconciliation of anonymous provider speakers and timing."""

from __future__ import annotations

from dataclasses import dataclass

from domain.ingestion import ParsedTranscript, Segment
from domain.providers import TranscriptSegmentResult


class ReconciliationError(ValueError):
    """Safe validation failure with no transcript content in its message."""


@dataclass(frozen=True)
class ReconciledSpeaker:
    speaker_key: str
    provider_label: str


@dataclass(frozen=True)
class ReconciliationResult:
    transcript: ParsedTranscript
    speakers: tuple[ReconciledSpeaker, ...]
    warning_codes: tuple[str, ...]


def reconcile_provider_segments(
    segments: tuple[TranscriptSegmentResult, ...], *, language: str = "en"
) -> ReconciliationResult:
    """Preserve provider text/times while making uncertainty explicit.

    Anonymous labels are deterministically assigned by first appearance. Timing is
    never invented, clipped, reordered, or forced to be non-overlapping.
    """

    if not segments:
        raise ReconciliationError("empty_provider_transcript")
    labels: dict[str, str] = {}
    speakers: list[ReconciledSpeaker] = []
    output: list[Segment] = []
    warnings: list[str] = []
    previous_start: int | None = None
    previous_end: int | None = None
    for item in segments:
        if not item.text:
            raise ReconciliationError("invalid_provider_segment")
        start, end = item.start_ms, item.end_ms
        if (start is None) != (end is None):
            start, end = None, None
            warnings.append("incomplete_timing_removed")
        elif start is not None and (start < 0 or end is None or end < start):
            raise ReconciliationError("invalid_provider_timestamp")
        if start is None:
            warnings.append("timing_unavailable")
        else:
            if previous_start is not None and start < previous_start:
                warnings.append("non_monotonic_timing_preserved")
            if previous_end is not None and start < previous_end:
                warnings.append("overlapping_timing_preserved")
            previous_start, previous_end = start, end

        label = item.speaker_label.strip() if item.speaker_label else ""
        speaker_key: str | None = None
        if label:
            speaker_key = labels.get(label)
            if speaker_key is None:
                speaker_key = f"speaker-{len(labels) + 1}"
                labels[label] = speaker_key
                speakers.append(ReconciledSpeaker(speaker_key, label))
        else:
            warnings.append("speaker_unavailable")
        output.append(Segment(item.text, speaker_key, start, end))
    return ReconciliationResult(
        ParsedTranscript("provider", language, tuple(output)),
        tuple(speakers),
        tuple(dict.fromkeys(warnings)),
    )
