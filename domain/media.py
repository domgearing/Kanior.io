"""Bounded FFmpeg-backed audio container validation."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import av

_MAX_DURATION_MS = 4 * 60 * 60 * 1000
_MIME_BY_SUFFIX = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".webm": "audio/webm",
}


class MediaValidationError(ValueError):
    """A content-free validation error safe to map at the API boundary."""


@dataclass(frozen=True)
class AudioMetadata:
    media_type: str
    duration_ms: int
    sample_rate: int | None
    channels: int | None


def validate_audio(filename: str, data: bytes) -> AudioMetadata:
    suffix = Path(filename).suffix.lower()
    media_type = _MIME_BY_SUFFIX.get(suffix)
    if media_type is None:
        raise MediaValidationError("unsupported_audio_format")
    try:
        with av.open(BytesIO(data), mode="r") as container:
            streams = list(container.streams.audio)
            if not streams:
                raise MediaValidationError("missing_audio_stream")
            stream = streams[0]
            sample_rate = stream.codec_context.sample_rate
            channels = stream.codec_context.channels
            duration_ms = 0
            for frame in container.decode(audio=0):
                rate = frame.sample_rate or sample_rate
                if not rate or rate <= 0:
                    raise MediaValidationError("invalid_audio_rate")
                duration_ms += round(frame.samples * 1000 / rate)
                if duration_ms > _MAX_DURATION_MS:
                    raise MediaValidationError("audio_duration_exceeded")
            if duration_ms == 0 and container.duration is not None:
                duration_ms = round(container.duration / 1000)
            if duration_ms > _MAX_DURATION_MS:
                raise MediaValidationError("audio_duration_exceeded")
            return AudioMetadata(media_type, duration_ms, sample_rate, channels)
    except MediaValidationError:
        raise
    except (av.error.FFmpegError, EOFError, ValueError) as error:
        raise MediaValidationError("invalid_audio") from error
