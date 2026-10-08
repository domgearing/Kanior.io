from uuid import UUID

import pytest

from connectors.microsoft_entra import admitted_employee
from domain.errors import DomainError

TENANT = "00000000-0000-4000-8000-000000000011"
CLIENT = "00000000-0000-4000-8000-000000000012"
GROUP = "00000000-0000-4000-8000-000000000013"
OID = "00000000-0000-4000-8000-000000000014"


def claims() -> dict[str, object]:
    return {
        "ver": "2.0",
        "tid": TENANT,
        "oid": OID,
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "aud": CLIENT,
        "acct": 0,
        "groups": [GROUP],
    }


def test_only_assigned_tenant_member_is_admitted() -> None:
    assert admitted_employee(claims(), TENANT, CLIENT, GROUP) == UUID(OID)


@pytest.mark.parametrize(
    ("changed", "value"),
    [
        ("tid", "00000000-0000-4000-8000-000000000099"),
        ("iss", "https://login.microsoftonline.com/common/v2.0"),
        ("aud", "other-client"),
        ("acct", 1),
        ("groups", []),
        ("groups", None),
        ("oid", "not-a-uuid"),
    ],
)
def test_rejects_other_tenant_guest_unassigned_or_malformed_identity(
    changed: str, value: object
) -> None:
    candidate = claims()
    candidate[changed] = value
    with pytest.raises(DomainError) as error:
        admitted_employee(candidate, TENANT, CLIENT, GROUP)
    assert error.value.status_code == 401
