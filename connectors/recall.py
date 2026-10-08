"""Server-only Recall Desktop SDK API and signed webhook adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from urllib.parse import urlparse

import httpx
from svix.webhooks import Webhook, WebhookVerificationError

from connectors.fakes import FakeProviderError
from domain.media import MediaValidationError, validate_audio
from domain.providers import ObjectStorage, StoredCapture


@dataclass(frozen=True)
class RecallUploadGrant:
    sdk_upload_id: str
    upload_token: str


@dataclass(frozen=True)
class RecallWebhookEvent:
    event_id: str
    event_type: str
    sdk_upload_id: str
    recording_id: str | None
    body_sha256: str


class RecallDesktopAdapter:
    def __init__(
        self,
        *,
        api_base_url: str,
        api_key: str,
        webhook_secret: str,
        timeout_seconds: float = 30,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = api_base_url.rstrip("/")
        self._api_host = urlparse(self._base_url).hostname
        self._client = client or httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Token {api_key}", "Accept": "application/json"},
            timeout=timeout_seconds,
        )
        self._webhook = Webhook(webhook_secret)

    def create_upload(self, capture_session_id: str, operation_key: str) -> RecallUploadGrant:
        response = self._request(
            "POST",
            "/api/v1/sdk_upload/",
            json={
                "recording_config": {
                    "audio_mixed_mp3": {},
                    "video_mixed_mp4": None,
                },
                "metadata": {
                    "verelo_capture_session_id": capture_session_id,
                    "verelo_operation_key_sha256": sha256(operation_key.encode()).hexdigest(),
                },
            },
        )
        sdk_upload_id = self._required_string(response, "id")
        upload_token = self._required_string(response, "upload_token")
        return RecallUploadGrant(sdk_upload_id, upload_token)

    def verify_webhook(self, raw_body: bytes, headers: dict[str, str]) -> RecallWebhookEvent:
        verification_headers = dict(headers)
        for name in ("id", "timestamp", "signature"):
            if f"svix-{name}" not in verification_headers:
                value = verification_headers.get(f"webhook-{name}")
                if value is not None:
                    verification_headers[f"svix-{name}"] = value
        try:
            self._webhook.verify(raw_body, verification_headers)
        except WebhookVerificationError as error:
            raise FakeProviderError("provider_permission") from error
        try:
            value = json.loads(raw_body)
        except json.JSONDecodeError as error:
            raise FakeProviderError("provider_invalid_response") from error
        if not isinstance(value, dict):
            raise FakeProviderError("provider_invalid_response")
        try:
            event_type = str(value["event"])
            data = value["data"]
            sdk_upload_id = str(data["sdk_upload"]["id"])
            recording = data.get("recording")
            recording_id = str(recording["id"]) if recording and recording.get("id") else None
        except (KeyError, TypeError) as error:
            raise FakeProviderError("provider_invalid_response") from error
        if event_type not in {
            "sdk_upload.complete",
            "sdk_upload.failed",
            "sdk_upload.uploading",
        }:
            raise FakeProviderError("provider_invalid_response")
        event_id = (
            headers.get("webhook-id")
            or headers.get("Webhook-Id")
            or headers.get("svix-id")
            or headers.get("Svix-Id")
        )
        if not event_id:
            raise FakeProviderError("provider_invalid_response")
        return RecallWebhookEvent(
            event_id, event_type, sdk_upload_id, recording_id, sha256(raw_body).hexdigest()
        )

    def copy_original(
        self,
        recording_id: str,
        storage: ObjectStorage,
        operation_key: str,
    ) -> StoredCapture:
        recording = self._request("GET", f"/api/v1/recording/{recording_id}/")
        try:
            audio = recording["media_shortcuts"]["audio_mixed"]
            if audio["status"]["code"] != "done":
                raise FakeProviderError("provider_unavailable")
            download_url = str(audio["data"]["download_url"])
        except (KeyError, TypeError) as error:
            raise FakeProviderError("provider_invalid_response") from error
        parsed = urlparse(download_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise FakeProviderError("provider_invalid_response")
        # Signed media URLs receive no Recall API Authorization header.
        try:
            response = httpx.get(download_url, timeout=self._client.timeout, follow_redirects=False)
        except httpx.HTTPError as error:
            raise FakeProviderError("provider_unavailable") from error
        if response.status_code != 200:
            raise FakeProviderError("provider_unavailable")
        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        extension = ".mp3" if content_type == "audio/mpeg" else ".bin"
        try:
            metadata = validate_audio(f"recall-original{extension}", response.content)
        except MediaValidationError as error:
            raise FakeProviderError("provider_invalid_response") from error
        digest = sha256(response.content).hexdigest()
        stored = storage.put_immutable(response.content, digest, operation_key)
        if sha256(storage.read_version(stored.object_ref)).hexdigest() != digest:
            raise FakeProviderError("integrity_failure")
        return StoredCapture(recording_id, stored, metadata.duration_ms, 0)

    def delete_capture(self, recording_id: str, operation_key: str) -> str:
        del operation_key
        try:
            response = self._client.delete(f"/api/v1/recording/{recording_id}/")
        except httpx.HTTPError as error:
            raise FakeProviderError("provider_unavailable") from error
        if response.status_code not in {200, 204, 404}:
            raise FakeProviderError("provider_unavailable")
        try:
            self._request("GET", f"/api/v1/recording/{recording_id}/")
        except FakeProviderError as error:
            if str(error) == "provider_not_found":
                return "deleted"
            raise
        raise FakeProviderError("provider_invalid_response")

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise FakeProviderError("provider_unavailable") from error
        if response.status_code in {401, 403}:
            raise FakeProviderError("provider_auth")
        if response.status_code == 404:
            raise FakeProviderError("provider_not_found")
        if response.status_code == 429 or response.status_code >= 500:
            raise FakeProviderError("provider_unavailable")
        if response.status_code >= 400:
            raise FakeProviderError("provider_invalid_input")
        try:
            value = response.json()
        except json.JSONDecodeError as error:
            raise FakeProviderError("provider_invalid_response") from error
        if not isinstance(value, dict):
            raise FakeProviderError("provider_invalid_response")
        return value

    @staticmethod
    def _required_string(value: dict[str, Any], key: str) -> str:
        result = value.get(key)
        if not isinstance(result, str) or not result:
            raise FakeProviderError("provider_invalid_response")
        return result
