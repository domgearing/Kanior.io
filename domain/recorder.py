"""Pure recording-session state machine used by Electron and recovery tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RecorderState = Literal[
    "idle", "recording", "paused", "interrupted", "finalizing", "uploading", "complete", "failed"
]


class RecorderTransitionError(ValueError):
    pass


@dataclass(frozen=True)
class RecordingGap:
    start_ms: int
    end_ms: int | None
    reason: str


@dataclass(frozen=True)
class RecordingSession:
    state: RecorderState = "idle"
    acknowledged_chunks: int = 0
    gaps: tuple[RecordingGap, ...] = ()

    def transition(
        self, event: str, *, at_ms: int = 0, reason: str = "device_interruption"
    ) -> RecordingSession:
        transitions: dict[tuple[RecorderState, str], RecorderState] = {
            ("idle", "start"): "recording",
            ("recording", "pause"): "paused",
            ("paused", "resume"): "recording",
            ("recording", "interrupt"): "interrupted",
            ("paused", "interrupt"): "interrupted",
            ("interrupted", "recover"): "recording",
            ("recording", "stop"): "finalizing",
            ("paused", "stop"): "finalizing",
            ("interrupted", "stop"): "finalizing",
            ("finalizing", "upload"): "uploading",
            ("uploading", "complete"): "complete",
        }
        target = transitions.get((self.state, event))
        if target is None:
            if event == "fail" and self.state not in {"idle", "complete", "failed"}:
                target = "failed"
            else:
                raise RecorderTransitionError("invalid_recorder_transition")
        gaps = self.gaps
        if event == "interrupt":
            gaps += (RecordingGap(at_ms, None, reason),)
        elif event == "recover":
            if not gaps or gaps[-1].end_ms is not None or at_ms < gaps[-1].start_ms:
                raise RecorderTransitionError("invalid_gap_recovery")
            gaps = gaps[:-1] + (RecordingGap(gaps[-1].start_ms, at_ms, gaps[-1].reason),)
        return RecordingSession(target, self.acknowledged_chunks, gaps)

    def acknowledge_chunk(self, sequence: int) -> RecordingSession:
        if self.state not in {"recording", "paused", "interrupted", "finalizing", "uploading"}:
            raise RecorderTransitionError("chunk_not_accepted")
        if sequence <= self.acknowledged_chunks:
            return self
        if sequence != self.acknowledged_chunks + 1:
            raise RecorderTransitionError("chunk_sequence_gap")
        return RecordingSession(self.state, sequence, self.gaps)
