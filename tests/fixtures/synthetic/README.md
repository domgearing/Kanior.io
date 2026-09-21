# Canonical synthetic corpus

This deterministic, fictional corpus is the shared input for future unit,
integration, end-to-end, and evaluation tests. `manifest.json` is the index: it
defines tenant/workspace/project/document IDs, fixture principals, visibility
expectations, content coverage, and SHA-256 hashes for the UTF-8 transcript
files.

The corpus deliberately includes two tenants, three projects, shared fictional
names, repeated wording, numbers, negation, Unicode, emoji, multiple speakers,
unsupported questions, prompt-like content, and repeated/ambiguous snippets.
The repeated phrase across projects is an authorization sentinel: a search for it
must never use a result from a project that the current principal cannot read.

All IDs and text are fictional. Do not replace them with real identities,
transcripts, credentials, provider responses, or production identifiers. Keep
transcripts as UTF-8 with LF line endings. If content changes, update its
metadata entry and SHA-256 in the manifest, then run:

```bash
uv run pytest tests/integration/test_synthetic_corpus.py
```

The fixture contract test verifies artifact integrity and references. It does
not test RLS; database authorization tests belong in `tests/integration/` after
the relevant Phase 1 service and migration path exist.
