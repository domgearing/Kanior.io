import pytest

from domain.recorder import RecorderTransitionError, RecordingSession


def test_recording_recovery_preserves_visible_gap_and_chunk_acknowledgements() -> None:
    session = RecordingSession().transition("start")
    session = session.acknowledge_chunk(1).transition("interrupt", at_ms=1200)
    session = session.acknowledge_chunk(1)  # retry is idempotent
    session = session.transition("recover", at_ms=1800).acknowledge_chunk(2)
    session = session.transition("stop").transition("upload").transition("complete")
    assert session.state == "complete"
    assert session.acknowledged_chunks == 2
    assert session.gaps[0].start_ms == 1200
    assert session.gaps[0].end_ms == 1800


def test_recorder_rejects_silent_chunk_loss_and_invalid_transitions() -> None:
    session = RecordingSession().transition("start")
    with pytest.raises(RecorderTransitionError, match="^chunk_sequence_gap$"):
        session.acknowledge_chunk(2)
    with pytest.raises(RecorderTransitionError, match="^invalid_recorder_transition$"):
        session.transition("complete")
