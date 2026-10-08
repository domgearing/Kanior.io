"""Live AssemblyAI async transcription adapter with durable submission reconciliation."""

from __future__ import annotations

import json
import sqlite3
import time
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Any, cast

import httpx

from connectors.fakes import FakeProviderError
from domain.providers import (
    ObjectStorage,
    RawTranscriptResult,
    Submission,
    TranscriptSegmentResult,
)


class AssemblyAIAdapter:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        storage: ObjectStorage,
        state_path: Path,
        model_id: str = "universal-3-5-pro",
        timeout_seconds: float = 30,
        client: httpx.Client | None = None,
    ) -> None:
        if model_id != "universal-3-5-pro":
            raise ValueError("AssemblyAI model must be pinned to universal-3-5-pro")
        self._storage = storage
        self._model = model_id
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": api_key},
            timeout=timeout_seconds,
        )
        state_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(state_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = Lock()
        with self._db:
            self._db.execute(
                """CREATE TABLE IF NOT EXISTS assemblyai_operations (
                operation_key TEXT PRIMARY KEY, audio_handle TEXT NOT NULL, upload_url TEXT NULL,
                transcript_id TEXT NULL, raw_artifact_ref TEXT NULL,
                deleted INTEGER NOT NULL DEFAULT 0)"""
            )

    def transcribe(self, audio_handle: str, operation_key: str) -> Submission:
        with self._lock, self._db:
            self._db.execute(
                """INSERT OR IGNORE INTO assemblyai_operations(operation_key,audio_handle)
                VALUES (?,?)""",
                (operation_key, audio_handle),
            )
        row = self._row_for_operation(operation_key)
        if row["audio_handle"] != audio_handle:
            raise FakeProviderError("provider_invalid_input")
        if row["transcript_id"]:
            return Submission(row["transcript_id"], self.get_status(row["transcript_id"]))
        upload_url = row["upload_url"]
        if upload_url is None:
            audio = self._storage.read_version(audio_handle)
            response = self._request("POST", "/v2/upload", content=audio)
            upload_url = self._required_string(response, "upload_url")
            with self._db:
                self._db.execute(
                    "UPDATE assemblyai_operations SET upload_url=? WHERE operation_key=?",
                    (upload_url, operation_key),
                )
        response = self._request(
            "POST",
            "/v2/transcript",
            json={
                "audio_url": upload_url,
                "speech_models": [self._model],
                "speaker_labels": True,
                "speakers_expected": 2,
            },
        )
        transcript_id = self._required_string(response, "id")
        with self._db:
            self._db.execute(
                "UPDATE assemblyai_operations SET transcript_id=? WHERE operation_key=?",
                (transcript_id, operation_key),
            )
        return Submission(transcript_id, str(response.get("status", "queued")))

    def get_status(self, submission_ref: str) -> str:
        response = self._request("GET", f"/v2/transcript/{submission_ref}")
        status = self._required_string(response, "status")
        return "failed" if status == "error" else status

    def wait(self, submission_ref: str, *, deadline_seconds: int = 1800) -> str:
        started = time.monotonic()
        delay = 5
        while True:
            status = self.get_status(submission_ref)
            if status in {"completed", "failed"}:
                return status
            if time.monotonic() - started >= deadline_seconds:
                raise FakeProviderError("provider_unavailable")
            time.sleep(delay)
            delay = min(delay + 5, 30)

    def fetch_result(self, submission_ref: str) -> RawTranscriptResult:
        row = self._row_for_submission(submission_ref)
        if row["raw_artifact_ref"]:
            raw = self._storage.read_version(row["raw_artifact_ref"])
            return self._parse(raw, row["raw_artifact_ref"])
        response = self._request("GET", f"/v2/transcript/{submission_ref}")
        if response.get("status") != "completed":
            raise FakeProviderError("provider_unavailable")
        raw = json.dumps(
            response, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        digest = sha256(raw).hexdigest()
        stored = self._storage.put_immutable(raw, digest, f"assemblyai-raw:{submission_ref}")
        reread = self._storage.read_version(stored.object_ref)
        if sha256(reread).hexdigest() != digest:
            raise FakeProviderError("integrity_failure")
        with self._db:
            self._db.execute(
                "UPDATE assemblyai_operations SET raw_artifact_ref=? WHERE transcript_id=?",
                (stored.object_ref, submission_ref),
            )
        return self._parse(raw, stored.object_ref)

    def delete_result(self, submission_ref: str, operation_key: str) -> str:
        del operation_key
        row = self._row_for_submission(submission_ref)
        if row["raw_artifact_ref"] is None:
            raise FakeProviderError("provider_invalid_input")
        self._request("DELETE", f"/v2/transcript/{submission_ref}")
        with self._db:
            self._db.execute(
                "UPDATE assemblyai_operations SET deleted=1 WHERE transcript_id=?",
                (submission_ref,),
            )
        try:
            value = self._request("GET", f"/v2/transcript/{submission_ref}")
        except FakeProviderError as error:
            if str(error) == "provider_not_found":
                return "deleted"
            raise
        if value.get("status") == "deleted" or value.get("text") is None:
            return "deleted"
        raise FakeProviderError("provider_invalid_response")

    def _parse(self, raw: bytes, raw_artifact_ref: str) -> RawTranscriptResult:
        try:
            value = json.loads(raw)
            utterances = value.get("utterances") or []
            segments = tuple(
                TranscriptSegmentResult(
                    text=str(item["text"]),
                    speaker_label=str(item["speaker"]) if item.get("speaker") is not None else None,
                    start_ms=int(item["start"]) if item.get("start") is not None else None,
                    end_ms=int(item["end"]) if item.get("end") is not None else None,
                )
                for item in utterances
            )
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as error:
            raise FakeProviderError("provider_invalid_response") from error
        if not segments:
            raise FakeProviderError("provider_invalid_response")
        return RawTranscriptResult("completed", segments, self._model, raw_artifact_ref)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise FakeProviderError("provider_unavailable") from error
        if response.status_code in {401, 403}:
            raise FakeProviderError("provider_auth")
        if response.status_code == 404:
            raise FakeProviderError("provider_not_found")
        if response.status_code == 429:
            raise FakeProviderError("provider_throttled")
        if response.status_code >= 500:
            raise FakeProviderError("provider_unavailable")
        if response.status_code >= 400:
            raise FakeProviderError("provider_invalid_input")
        if not response.content:
            return {}
        try:
            result = response.json()
        except ValueError as error:
            raise FakeProviderError("provider_invalid_response") from error
        if not isinstance(result, dict):
            raise FakeProviderError("provider_invalid_response")
        return result

    def _row_for_operation(self, operation_key: str) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT * FROM assemblyai_operations WHERE operation_key=?", (operation_key,)
        ).fetchone()
        if row is None:
            raise FakeProviderError("provider_not_found")
        return cast(sqlite3.Row, row)

    def _row_for_submission(self, submission_ref: str) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT * FROM assemblyai_operations WHERE transcript_id=?", (submission_ref,)
        ).fetchone()
        if row is None:
            raise FakeProviderError("provider_not_found")
        return cast(sqlite3.Row, row)

    @staticmethod
    def _required_string(value: dict[str, Any], key: str) -> str:
        result = value.get(key)
        if not isinstance(result, str) or not result:
            raise FakeProviderError("provider_invalid_response")
        return result
