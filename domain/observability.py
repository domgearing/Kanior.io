"""Content-free operational signals shared by API and worker processes."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass(frozen=True)
class OperationalSignal:
    name: str
    trace_id: str
    outcome: str
    duration_ms: int | None = None
    count: int | None = None
    safe_code: str | None = None


class SignalSink(Protocol):
    def emit(self, signal: OperationalSignal) -> None: ...


class StructuredLogSink:
    """Emit allowlisted metadata only; callers cannot attach content fields."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("verelo.operations")

    def emit(self, signal: OperationalSignal) -> None:
        self._logger.info(json.dumps(asdict(signal), sort_keys=True, separators=(",", ":")))


class InMemorySignalSink:
    """Deterministic test/local sink."""

    def __init__(self) -> None:
        self.signals: list[OperationalSignal] = []

    def emit(self, signal: OperationalSignal) -> None:
        self.signals.append(signal)
