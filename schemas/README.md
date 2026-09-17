# Contract artifacts

Editable source: `contracts/models.py` and `contracts/http.py`. Python services import those models. All JSON files here and `contracts/generated/api.d.ts` are generated; do not edit them. `docs/API_CONTRACTS.md`, `docs/DATA_MODEL.md`, and `docs/SECURITY.md` specify contextual invariants schemas cannot enforce.

The initial HTTP schema covers nine foundation operations only. Import, AI and event components reserve already specified boundaries; their presence does not mean product features exist. No placeholders for later HTTP routes are published.

## Install

Use Python 3.12 or 3.13 and Node 24 (the existing CI runtime). From the repository root, create an isolated contract environment; the existing `.artifacts/` ignore rule keeps it out of git:

```powershell
python -m venv .artifacts/contracts-venv
.\.artifacts\contracts-venv\Scripts\python.exe -m pip install -r tools/contracts/requirements.lock
npm.cmd ci --prefix tools/contracts --ignore-scripts
```

On Bash, the interpreter path is `.artifacts/contracts-venv/bin/python` and the npm command is `npm ci --prefix tools/contracts --ignore-scripts`. CI's existing `scripts/setup-ci.sh` installs the same locked tools. No provider credentials, paid APIs, application server or database are needed.

## Generate and verify

```powershell
.\.artifacts\contracts-venv\Scripts\python.exe scripts/generate-contracts.py
.\.artifacts\contracts-venv\Scripts\python.exe scripts/validate-contracts.py
.\.artifacts\contracts-venv\Scripts\python.exe scripts/generate-contracts.py --check
```

Generation runs pinned openapi-typescript through the local Node installation and typechecks its output. `--check` regenerates into a temporary directory and compares exact bytes, including unexpected obsolete artifacts; it never rewrites the checkout. The existing PR gate runs validation and drift checks even without root application manifests.

`tools/contracts/requirements.in` lists direct Python dependencies; `requirements.lock` pins the resolved environment. `tools/contracts/package-lock.json` pins JS dependencies. Update tools intentionally, regenerate artifacts, and rerun checks. Move the tools into the eventual root workspace lockfiles at bootstrap rather than keeping two installations authoritative.

## Validation boundaries

- JSON Schema verifies closed shapes, formats, size bounds, import timing pairing and selection uniqueness.
- Python also verifies increasing timing/span bounds, exact integer schema versions, event aggregate equality and UTC event time.
- Service/database tests must verify identity, sealed candidate membership, authorization, semantic boundaries, reference scope, hashes, idempotency, RLS and transactional behavior. No schema file certifies those properties.
- HTTP handlers must translate validation failures to the safe `Error` shape; never expose raw Pydantic errors containing input values.

When implementing FastAPI, reuse the models/operation IDs/statuses and add runtime OpenAPI conformance tests in that PR. No manually maintained client DTOs or second request-model hierarchy.

Tool behavior follows [Pydantic's schema generation documentation](https://docs.pydantic.dev/latest/concepts/json_schema/) and the [openapi-typescript CLI documentation](https://openapi-ts.dev/cli).
