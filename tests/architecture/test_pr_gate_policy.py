from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def test_pr_suite_is_non_empty_and_blocking() -> None:
    with (ROOT / "evals" / "manifest.toml").open("rb") as fh:
        manifest = tomllib.load(fh)

    names = manifest["suites"]["pr"]["evals"]
    assert names, "PR eval suite must never be empty"

    for name in names:
        cfg = manifest["evals"][name]
        assert cfg["blocking"] is True, f"PR eval {name} must be blocking"
        assert "threshold" in cfg
        assert cfg["comparison"] in {"gte", "gt", "lte", "lt", "eq"}


def test_full_suite_contains_every_pr_eval() -> None:
    with (ROOT / "evals" / "manifest.toml").open("rb") as fh:
        manifest = tomllib.load(fh)

    pr = set(manifest["suites"]["pr"]["evals"])
    full = set(manifest["suites"]["full"]["evals"])
    assert pr <= full, "full eval suite must contain every PR eval"
