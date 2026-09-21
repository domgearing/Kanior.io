"""Validate the repository's fictional test corpus; this is not an RLS test."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CORPUS_ROOT = ROOT / "tests" / "fixtures" / "synthetic"
MANIFEST_PATH = CORPUS_ROOT / "manifest.json"


def _manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _projects(manifest: dict[str, Any]) -> set[str]:
    return {
        project["project_id"] for tenant in manifest["tenants"] for project in tenant["projects"]
    }


def test_synthetic_corpus_is_fictional_deterministic_and_multi_tenant() -> None:
    manifest = _manifest()

    assert manifest["fictional_only"] is True
    assert manifest["encoding"] == "UTF-8"
    assert manifest["line_endings"] == "LF"
    assert len(manifest["tenants"]) >= 2
    assert len(_projects(manifest)) >= 3
    assert all(manifest["coverage"].values())

    corpus_text = "\n".join(path.read_text(encoding="utf-8") for path in CORPUS_ROOT.rglob("*.txt"))
    for category, markers in manifest["coverage_markers"].items():
        assert manifest["coverage"][category] is True
        assert all(marker in corpus_text for marker in markers)


def test_manifest_integrity_references_and_authorization_cases_are_consistent() -> None:
    manifest = _manifest()
    project_ids = _projects(manifest)
    document_ids: set[str] = set()

    for tenant in manifest["tenants"]:
        for project in tenant["projects"]:
            for document in project["documents"]:
                transcript_path = CORPUS_ROOT / document["path"]
                metadata_path = CORPUS_ROOT / document["metadata_path"]
                assert transcript_path.is_file()
                assert metadata_path.is_file()
                assert "\r" not in transcript_path.read_text(encoding="utf-8")
                actual_sha256 = hashlib.sha256(transcript_path.read_bytes()).hexdigest()
                assert actual_sha256 == document["sha256"]

                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                assert metadata["fixture_document_id"] == document["document_id"]
                assert metadata["fixture_transcript_id"] == document["transcript_id"]
                assert document["document_id"] not in document_ids
                document_ids.add(document["document_id"])

    for principal in manifest["principals"]:
        readable = set(principal["readable_project_ids"])
        denied = set(principal["denied_project_ids"])
        assert readable <= project_ids
        assert denied <= project_ids
        assert readable.isdisjoint(denied)

    for assertion in manifest["future_assertions"]:
        named_principals = {principal["fixture_name"] for principal in manifest["principals"]}
        assert assertion["principal"] in named_principals
        if "must_include_project_ids" in assertion:
            assert set(assertion["must_include_project_ids"]) <= project_ids
            assert set(assertion["must_exclude_project_ids"]) <= project_ids
