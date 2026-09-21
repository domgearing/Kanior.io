from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.config import Environment, IntegrationsMode, Settings


def test_defaults_use_fake_integrations_for_local_foundation() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.environment == "local"
    assert settings.integrations_mode == "fake"


def test_production_rejects_fake_integrations() -> None:
    with pytest.raises(ValidationError, match="production cannot use fake integrations"):
        Settings(
            environment=Environment.PRODUCTION,
            integrations_mode=IntegrationsMode.FAKE,
            _env_file=None,  # type: ignore[call-arg]
        )
