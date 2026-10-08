from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from hashlib import sha256

import httpx
import pytest
from svix.webhooks import Webhook

from connectors.assemblyai import AssemblyAIAdapter
from connectors.backblaze_b2 import BackblazeB2Storage
from connectors.fakes import FakeObjectStorage, FakeProviderError
from connectors.recall import RecallDesktopAdapter


class _Body:
    def __init__(self, value: bytes) -> None:
        self._value = value

    def read(self) -> bytes:
        return self._value


class _S3:
    def __init__(self) -> None:
        self.parts: dict[int, bytes] = {}
        self.value = b""
        self.metadata: dict[str, str] = {}

    def create_multipart_upload(self, **kwargs):  # type: ignore[no-untyped-def]
        self.metadata = kwargs["Metadata"]
        return {"UploadId": "upload-1"}

    def list_parts(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return {
            "Parts": [
                {"PartNumber": number, "ETag": f"etag-{number}"} for number in sorted(self.parts)
            ]
        }

    def upload_part(self, **kwargs):  # type: ignore[no-untyped-def]
        self.parts[kwargs["PartNumber"]] = kwargs["Body"]
        return {"ETag": f"etag-{kwargs['PartNumber']}"}

    def complete_multipart_upload(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        self.value = b"".join(self.parts[number] for number in sorted(self.parts))
        return {"VersionId": "version-1"}

    def get_object(self, **kwargs):  # type: ignore[no-untyped-def]
        value = self.value
        if "Range" in kwargs:
            start, end = kwargs["Range"].removeprefix("bytes=").split("-")
            value = value[int(start) : int(end) + 1]
        return {"Body": _Body(value)}

    def head_object(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return {"ContentLength": len(self.value), "Metadata": self.metadata}


def test_assemblyai_pins_model_is_idempotent_and_stores_raw(tmp_path) -> None:  # type: ignore[no-untyped-def]
    submitted: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"upload_url": "https://upload.invalid/audio"})
        if request.url.path == "/v2/transcript" and request.method == "POST":
            submitted.append(json.loads(request.content))
            return httpx.Response(200, json={"id": "transcript-1", "status": "queued"})
        if request.url.path == "/v2/transcript/transcript-1":
            return httpx.Response(
                200,
                json={
                    "id": "transcript-1",
                    "status": "completed",
                    "utterances": [
                        {"speaker": "A", "text": "Fictional one.", "start": 0, "end": 500},
                        {"speaker": "B", "text": "Fictional two.", "start": 500, "end": 900},
                    ],
                },
            )
        raise AssertionError(request.url)

    storage = FakeObjectStorage()
    audio = storage.put_immutable(b"audio", sha256(b"audio").hexdigest(), "audio")
    client = httpx.Client(
        base_url="https://api.assemblyai.com",
        transport=httpx.MockTransport(handler),
    )
    adapter = AssemblyAIAdapter(
        api_key="test",
        base_url="https://api.assemblyai.com",
        storage=storage,
        state_path=tmp_path / "state.sqlite3",
        client=client,
    )
    first = adapter.transcribe(audio.object_ref, "operation-1")
    second = adapter.transcribe(audio.object_ref, "operation-1")
    assert first.submission_ref == second.submission_ref
    assert len(submitted) == 1
    assert submitted[0]["speech_models"] == ["universal-3-5-pro"]
    assert submitted[0]["speaker_labels"] is True
    result = adapter.fetch_result(first.submission_ref)
    assert [item.speaker_label for item in result.segments] == ["A", "B"]
    assert storage.read_version(result.raw_artifact_ref)


def test_assemblyai_rejects_operation_rebinding(tmp_path) -> None:  # type: ignore[no-untyped-def]
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/upload":
            return httpx.Response(200, json={"upload_url": "https://upload.invalid/audio"})
        return httpx.Response(200, json={"id": "transcript-1", "status": "queued"})

    storage = FakeObjectStorage()
    one = storage.put_immutable(b"one", sha256(b"one").hexdigest(), "one")
    two = storage.put_immutable(b"two", sha256(b"two").hexdigest(), "two")
    adapter = AssemblyAIAdapter(
        api_key="test",
        base_url="https://api.assemblyai.com",
        storage=storage,
        state_path=tmp_path / "state.sqlite3",
        client=httpx.Client(
            base_url="https://api.assemblyai.com", transport=httpx.MockTransport(handler)
        ),
    )
    adapter.transcribe(one.object_ref, "same")
    with pytest.raises(FakeProviderError, match="provider_invalid_input"):
        adapter.transcribe(two.object_ref, "same")


def test_recall_create_is_audio_only_and_webhook_is_verified() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(201, json={"id": "upload-1", "upload_token": "scoped-token"})

    secret = "whsec_" + base64.b64encode(b"01234567890123456789012345678901").decode()
    client = httpx.Client(
        base_url="https://us-west-2.recall.ai",
        transport=httpx.MockTransport(handler),
    )
    adapter = RecallDesktopAdapter(
        api_base_url="https://us-west-2.recall.ai",
        api_key="server-key",
        webhook_secret=secret,
        client=client,
    )
    grant = adapter.create_upload("capture-1", "operation-1")
    assert grant.upload_token == "scoped-token"
    assert captured["recording_config"] == {
        "audio_mixed_mp3": {},
        "video_mixed_mp4": None,
    }
    body = json.dumps(
        {
            "event": "sdk_upload.complete",
            "data": {
                "sdk_upload": {"id": "upload-1"},
                "recording": {"id": "recording-1"},
            },
        },
        separators=(",", ":"),
    )
    timestamp = datetime.now(UTC)
    signature = Webhook(secret).sign("event-1", timestamp, body)
    event = adapter.verify_webhook(
        body.encode(),
        {
            "webhook-id": "event-1",
            "webhook-timestamp": str(int(timestamp.timestamp())),
            "webhook-signature": signature,
        },
    )
    assert event.recording_id == "recording-1"
    with pytest.raises(FakeProviderError, match="provider_permission"):
        adapter.verify_webhook(body.encode(), {"webhook-id": "event-1"})
    legacy_event = adapter.verify_webhook(
        body.encode(),
        {
            "svix-id": "event-1",
            "svix-timestamp": str(int(timestamp.timestamp())),
            "svix-signature": signature,
        },
    )
    assert legacy_event.event_id == "event-1"


def test_b2_multipart_resumes_and_reads_pinned_version(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _S3()
    monkeypatch.setattr("connectors.backblaze_b2.boto3.client", lambda *args, **kwargs: client)
    state = tmp_path / "b2.sqlite3"
    data = b"x" * (9 * 1024 * 1024)
    digest = sha256(data).hexdigest()

    def interrupt(part: int) -> None:
        if part == 1:
            raise RuntimeError("interrupt")

    first = BackblazeB2Storage(
        endpoint_url="https://s3.example.invalid",
        region="test",
        bucket="bucket",
        key_prefix="smoke/",
        access_key_id="id",
        secret_access_key="secret",
        operation_store=state,
        multipart_checkpoint_hook=interrupt,
    )
    with pytest.raises(RuntimeError, match="interrupt"):
        first.put_immutable(data, digest, "operation")
    resumed = BackblazeB2Storage(
        endpoint_url="https://s3.example.invalid",
        region="test",
        bucket="bucket",
        key_prefix="smoke/",
        access_key_id="id",
        secret_access_key="secret",
        operation_store=state,
    )
    stored = resumed.put_immutable(data, digest, "operation")
    assert resumed.read_version(stored.object_ref) == data
    assert resumed.read_version(stored.object_ref, (1, 3)) == b"xx"
