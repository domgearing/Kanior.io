"""Small amplitude envelope derived from an authorized original recording."""

from __future__ import annotations

from array import array
from io import BytesIO

import av

from domain.media import MediaValidationError

_RATE = 8_000
_BINS = 320
_SAMPLES_PER_BIN = 96


def audio_waveform(data: bytes, duration_ms: int) -> tuple[float, ...]:
    """Decode to mono PCM and sample bounded points per timeline bin."""
    if duration_ms <= 0:
        raise MediaValidationError("invalid_audio_duration")
    peaks = [0.0] * _BINS
    expected_samples = max(1, round(duration_ms * _RATE / 1000))
    stride = max(1, expected_samples // (_BINS * _SAMPLES_PER_BIN))
    position = 0
    try:
        with av.open(BytesIO(data), mode="r") as container:
            if not container.streams.audio:
                raise MediaValidationError("missing_audio_stream")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=_RATE)
            for frame in container.decode(audio=0):
                for mono in resampler.resample(frame):
                    samples = array("h")
                    samples.frombytes(bytes(mono.planes[0]))
                    for offset in range(0, min(mono.samples, len(samples)), stride):
                        index = min(_BINS - 1, (position + offset) * _BINS // expected_samples)
                        peaks[index] = max(peaks[index], abs(samples[offset]) / 32768)
                    position += mono.samples
            for mono in resampler.resample(None):
                samples = array("h")
                samples.frombytes(bytes(mono.planes[0]))
                for offset in range(0, min(mono.samples, len(samples)), stride):
                    index = min(_BINS - 1, (position + offset) * _BINS // expected_samples)
                    peaks[index] = max(peaks[index], abs(samples[offset]) / 32768)
                position += mono.samples
    except MediaValidationError:
        raise
    except (av.error.FFmpegError, EOFError, ValueError) as error:
        raise MediaValidationError("invalid_audio") from error
    maximum = max(peaks)
    return tuple(round((peak / maximum) ** 0.7, 4) if maximum else 0.0 for peak in peaks)
