from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from connectors.microsoft_entra import verified_id_token
from domain.errors import DomainError

TENANT = "00000000-0000-4000-8000-000000000011"
CLIENT = "00000000-0000-4000-8000-000000000012"
OID = "00000000-0000-4000-8000-000000000014"
NONCE = "fictional-flow-nonce"


class FixedSigningKeys:
    def __init__(self, key: Any) -> None:
        self.key = key

    def get_signing_key_from_jwt(self, _token: str) -> Any:
        return type("SigningKey", (), {"key": self.key})()


def signed_token(key: Any, **changes: object) -> str:
    now = datetime.now(UTC)
    payload = {
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "aud": CLIENT,
        "tid": TENANT,
        "oid": OID,
        "nonce": sha256(NONCE.encode("ascii")).hexdigest(),
        "iat": now,
        "exp": now + timedelta(minutes=5),
        **changes,
    }
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "fictional-key"})


def test_id_token_requires_valid_signature_time_audience_and_nonce() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = FixedSigningKeys(key.public_key())
    token = signed_token(key)
    assert (
        verified_id_token(
            token,
            tenant=TENANT,
            client=CLIENT,
            nonce=NONCE,
            keys=verifier,  # type: ignore[arg-type]
        )["oid"]
        == OID
    )

    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    invalid = (
        signed_token(other),
        signed_token(key, aud="wrong-client"),
        signed_token(key, exp=datetime.now(UTC) - timedelta(minutes=1)),
        signed_token(key, nonce="wrong-nonce"),
    )
    for candidate in invalid:
        with pytest.raises(DomainError) as error:
            verified_id_token(
                candidate,
                tenant=TENANT,
                client=CLIENT,
                nonce=NONCE,
                keys=verifier,  # type: ignore[arg-type]
            )
        assert error.value.status_code == 401
