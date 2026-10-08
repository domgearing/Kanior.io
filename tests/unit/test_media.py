from __future__ import annotations

from io import BytesIO
from typing import Any

import av
import pytest

from domain.media import MediaValidationError, validate_audio


def _audio(format_name: str, codec: str, rate: int) -> bytes:
    output = BytesIO()
    with av.open(output, "w", format=format_name) as container:
        stream: Any = container.add_stream(codec, rate=rate)
        stream.layout = "mono"
        samples = stream.codec_context.frame_size or 960
        frame = av.AudioFrame(format="s16", layout="mono", samples=samples)
        frame.sample_rate = rate
        frame.planes[0].update(bytes(samples * 2))
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return output.getvalue()


@pytest.mark.parametrize(
    ("filename", "format_name", "codec", "rate", "media_type"),
    [
        ("meeting.wav", "wav", "pcm_s16le", 8_000, "audio/wav"),
        ("meeting.mp3", "mp3", "mp3", 8_000, "audio/mpeg"),
        ("meeting.m4a", "ipod", "aac", 48_000, "audio/mp4"),
        ("meeting.webm", "webm", "libopus", 48_000, "audio/webm"),
    ],
)
def test_supported_audio_is_decoded(
    filename: str, format_name: str, codec: str, rate: int, media_type: str
) -> None:
    metadata = validate_audio(filename, _audio(format_name, codec, rate))

    assert metadata.media_type == media_type
    assert metadata.duration_ms >= 0
    assert metadata.sample_rate == rate
    assert metadata.channels == 1


def test_extension_or_signature_without_decodable_audio_is_rejected() -> None:
    with pytest.raises(MediaValidationError, match="invalid_audio"):
        validate_audio("meeting.mp3", b"ID3not-a-real-audio-stream")


def test_unapproved_container_is_rejected() -> None:
    with pytest.raises(MediaValidationError, match="unsupported_audio_format"):
        validate_audio("meeting.flac", b"fLaC")
