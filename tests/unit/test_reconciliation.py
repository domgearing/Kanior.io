from __future__ import annotations

import pytest

from domain.providers import TranscriptSegmentResult
from domain.reconciliation import ReconciliationError, reconcile_provider_segments


def test_reconciliation_assigns_stable_speakers_and_preserves_overlap() -> None:
    segments = (
        TranscriptSegmentResult("One", "Guest", 1000, 2000),
        TranscriptSegmentResult("Two", "Host", 1800, 2200),
        TranscriptSegmentResult("Three", "Guest", 2300, 2600),
    )
    result = reconcile_provider_segments(segments)
    assert [item.speaker_label for item in result.transcript.segments] == [
        "speaker-1",
        "speaker-2",
        "speaker-1",
    ]
    assert result.transcript.segments[1].start_ms == 1800
    assert result.warning_codes == ("overlapping_timing_preserved",)


def test_reconciliation_exposes_missing_and_non_monotonic_metadata_without_guessing() -> None:
    segments = (
        TranscriptSegmentResult("One", None, 1000, 2000),
        TranscriptSegmentResult("Two", "  ", None, 2100),
        TranscriptSegmentResult("Three", "A", 500, 700),
    )
    result = reconcile_provider_segments(segments)
    assert result.transcript.segments[0].speaker_label is None
    assert result.transcript.segments[1].start_ms is None
    assert result.transcript.segments[1].end_ms is None
    assert set(result.warning_codes) == {
        "speaker_unavailable",
        "incomplete_timing_removed",
        "timing_unavailable",
        "non_monotonic_timing_preserved",
        "overlapping_timing_preserved",
    }


@pytest.mark.parametrize(
    "segment",
    [
        TranscriptSegmentResult("", "A", 0, 1),
        TranscriptSegmentResult("x", "A", -1, 1),
        TranscriptSegmentResult("x", "A", 2, 1),
    ],
)
def test_reconciliation_rejects_invalid_provider_segments(segment: TranscriptSegmentResult) -> None:
    with pytest.raises(ReconciliationError):
        reconcile_provider_segments((segment,))


def test_reconciliation_does_not_merge_adversarial_confusable_labels() -> None:
    result = reconcile_provider_segments(
        (
            TranscriptSegmentResult("One", "A", 0, 1),
            TranscriptSegmentResult("Two", "А", 1, 2),  # Cyrillic A
            TranscriptSegmentResult("Three", "a", 2, 3),
        )
    )
    assert [item.speaker_label for item in result.transcript.segments] == [
        "speaker-1",
        "speaker-2",
        "speaker-3",
    ]
