# Integration tests

This directory is reserved for tests that exercise a real disposable PostgreSQL
database, including row-level security (RLS), migrations, transaction boundaries,
and provider adapters. It intentionally contains no fake RLS test: application
code and migrations must exist before a database test can prove tenant, workspace,
or project isolation.

`test_synthetic_corpus.py` is a repository-fixture contract check. It validates
the deterministic corpus used by later integration and evaluation tests; it does
not make any claim about database authorization.

When Phase 1 services are available, add tests here that load the corpus through
the normal migration and service path, run with non-owner application roles, and
assert that each denied case exposes no row, count, score, snippet, or metadata.
Those database tests may skip only when their documented disposable database
prerequisite is unavailable.
