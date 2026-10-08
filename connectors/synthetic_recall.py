"""Credential-free Recall capture lifecycle simulator; never performs network I/O."""

from __future__ import annotations

import hmac
import json
from dataclasses import dataclass, field
from hashlib import sha256

from domain.providers import CaptureEvent, CaptureGrant, ObjectStorage, StoredCapture

from .fakes import FakeProviderError


@dataclass
class SyntheticRecallAdapter:
    audio_bytes: bytes
    duration_ms: int
    signing_key: bytes = b"fictional-recall-signing-key"
    gap_count: int = 0
    fault: str | None = None
    _operations: dict[str, tuple[str, CaptureGrant]] = field(default_factory=dict)
    _captures: dict[str, str] = field(default_factory=dict)
    _events: set[str] = field(default_factory=set)
    _copies: dict[str, StoredCapture] = field(default_factory=dict)
    _deleted: set[str] = field(default_factory=set)

    def create_session(self, capture_session_id: str, operation_key: str) -> CaptureGrant:
        prior = self._operations.get(operation_key)
        if prior is not None:
            if prior[0] != capture_session_id:
                raise FakeProviderError("provider_invalid_input")
            return prior[1]
        grant = CaptureGrant(f"synthetic-recall-{len(self._captures) + 1}", "recording")
        self._operations[operation_key] = (capture_session_id, grant)
        self._captures[grant.capture_ref] = capture_session_id
        return grant

    def notification(self, capture_ref: str, event_id: str) -> tuple[bytes, str]:
        body = json.dumps(
            {
                "event": "sdk_upload.complete",
                "event_id": event_id,
                "data": {"recording": {"id": capture_ref}},
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return body, hmac.new(self.signing_key, body, sha256).hexdigest()

    def verify_notification(self, raw_body: bytes, signature: str) -> CaptureEvent:
        expected = hmac.new(self.signing_key, raw_body, sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise FakeProviderError("provider_permission")
        try:
            value = json.loads(raw_body)
            capture_ref = value["data"]["recording"]["id"]
            event_id = value["event_id"]
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise FakeProviderError("provider_invalid_response") from error
        if value.get("event") != "sdk_upload.complete" or capture_ref not in self._captures:
            raise FakeProviderError("provider_invalid_response")
        state = "duplicate" if event_id in self._events else "completed"
        self._events.add(event_id)
        return CaptureEvent(event_id, capture_ref, state)

    def copy_original(
        self, capture_ref: str, storage: ObjectStorage, operation_key: str
    ) -> StoredCapture:
        if capture_ref not in self._captures or capture_ref in self._deleted:
            raise FakeProviderError("provider_not_found")
        if self.fault == "media_delayed":
            raise FakeProviderError("provider_unavailable")
        if self.fault == "missing_audio":
            raise FakeProviderError("provider_invalid_response")
        digest = sha256(self.audio_bytes).hexdigest()
        expected = "0" * 64 if self.fault == "wrong_hash" else digest
        stored = storage.put_immutable(self.audio_bytes, expected, operation_key)
        result = StoredCapture(capture_ref, stored, self.duration_ms, self.gap_count)
        prior = self._copies.setdefault(operation_key, result)
        if prior.capture_ref != capture_ref:
            raise FakeProviderError("provider_invalid_input")
        return prior

    def delete_capture(self, capture_ref: str, operation_key: str) -> str:
        del operation_key
        if capture_ref not in self._captures:
            raise FakeProviderError("provider_not_found")
        if self.fault == "delete_failed":
            raise FakeProviderError("provider_unavailable")
        self._deleted.add(capture_ref)
        return "deleted"
