from __future__ import annotations

import logging

from domain.observability import OperationalSignal, StructuredLogSink


def test_structured_operational_signal_has_closed_content_free_shape(caplog) -> None:  # type: ignore[no-untyped-def]
    with caplog.at_level(logging.INFO, logger="safe-test"):
        StructuredLogSink(logging.getLogger("safe-test")).emit(
            OperationalSignal("job.queue_age", "trace-1", "observed", count=3)
        )
    assert '"name":"job.queue_age"' in caplog.text
    assert "transcript" not in caplog.text
    assert "token" not in caplog.text
