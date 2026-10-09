from __future__ import annotations

from array import array
from io import BytesIO
from math import pi, sin

import av
import pytest

from domain.media import MediaValidationError
from domain.waveform import audio_waveform


def _two_part_recording() -> bytes:
    output = BytesIO()
    with av.open(output, "w", format="wav") as container:
        stream = container.add_stream("pcm_s16le", rate=8_000)
        stream.layout = "mono"
        samples = array("h", [0] * 4_000)
        samples.extend(int(12_000 * sin(2 * pi * 440 * index / 8_000)) for index in range(4_000))
        frame = av.AudioFrame(format="s16", layout="mono", samples=len(samples))
        frame.sample_rate = 8_000
        frame.planes[0].update(samples.tobytes())
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return output.getvalue()


def test_waveform_follows_original_audio_amplitude() -> None:
    peaks = audio_waveform(_two_part_recording(), 1_000)
    assert len(peaks) == 320
    assert all(0 <= peak <= 1 for peak in peaks)
    assert max(peaks[:100]) == 0
    assert max(peaks[220:]) > 0.9


def test_waveform_rejects_invalid_audio_and_duration() -> None:
    with pytest.raises(MediaValidationError):
        audio_waveform(b"not audio", 1_000)
    with pytest.raises(MediaValidationError):
        audio_waveform(_two_part_recording(), 0)
