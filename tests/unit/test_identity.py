from domain.identity import normalize_email


def test_normalize_email_is_deterministic() -> None:
    assert normalize_email("  Employee@Example.INVALID ") == "employee@example.invalid"
