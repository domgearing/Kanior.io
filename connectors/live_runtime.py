"""Construction of live storage and speech adapters from validated settings."""

from pathlib import Path

from pydantic import SecretStr

from api.config import Settings
from connectors.assemblyai import AssemblyAIAdapter
from connectors.backblaze_b2 import BackblazeB2Storage


def _required(value: object | None, name: str) -> str:
    if value is None:
        raise RuntimeError(f"{name} is required in live integrations mode")
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    result = str(value)
    if not result:
        raise RuntimeError(f"{name} is required in live integrations mode")
    return result


def create_live_storage(settings: Settings) -> BackblazeB2Storage:
    state = Path(".artifacts/live-runtime")
    return BackblazeB2Storage(
        endpoint_url=_required(settings.b2_s3_endpoint, "VERELO_B2_S3_ENDPOINT"),
        region=_required(settings.b2_region, "VERELO_B2_REGION"),
        bucket=_required(settings.b2_bucket_name, "VERELO_B2_BUCKET_NAME"),
        key_prefix=settings.b2_key_prefix,
        access_key_id=_required(settings.b2_application_key_id, "VERELO_B2_APPLICATION_KEY_ID"),
        secret_access_key=_required(settings.b2_application_key, "VERELO_B2_APPLICATION_KEY"),
        operation_store=state / "b2.sqlite3",
    )


def create_live_transcription(settings: Settings, storage: BackblazeB2Storage) -> AssemblyAIAdapter:
    return AssemblyAIAdapter(
        api_key=_required(settings.assemblyai_api_key, "VERELO_ASSEMBLYAI_API_KEY"),
        base_url=str(settings.assemblyai_api_base_url),
        storage=storage,
        state_path=Path(".artifacts/live-runtime/assemblyai.sqlite3"),
        model_id=settings.assemblyai_speech_model,
        timeout_seconds=settings.integration_request_timeout_seconds,
    )
