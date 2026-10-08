# verelo.io

Verelo is an internal transcript creation, processing, and query application. It records or imports expert calls and internal meetings, preserves their sources securely, and lets authorized users retrieve verifiable quotes from approved transcript versions.

The repository currently provides a runnable synthetic Phase 0–2 scaffold: an authorized FastAPI
application, PostgreSQL 17 with pgvector and forced RLS, durable jobs/outbox persistence, immutable
local object storage, deterministic transcript ingestion/publication, and web/Electron product shells.
It is for synthetic local development only. Live identity/provider feasibility checks and the open
company-policy decisions still block confidential traffic.

Local development includes an explicit-allowlist magic-link login behind a provider-neutral identity
interface. It contacts neither Microsoft nor an email service. Production identity remains Microsoft
Entra; replacing the development adapter does not change users, sessions, authorization, RLS,
projects, or transcript data.

## Source of truth

Read [ARCHITECTURE.md](ARCHITECTURE.md) before implementation. It controls module boundaries, security rules, build order, and acceptance gates. The first implementation slice also depends on:

- [Data model](docs/DATA_MODEL.md)
- [API and service contracts](docs/API_CONTRACTS.md)
- [Security contract](docs/SECURITY.md)
- [Provider integration guides and feasibility gates](docs/INTEGRATIONS.md)
- [Schema generation and validation](schemas/README.md)

## Supported development environment

Windows development is supported through **Git Bash**, with Docker Desktop using Linux containers. Run every `./scripts/*.sh` command below from Git Bash at the repository root. PowerShell and WSL are not supported script environments for this foundation. CI runs the same Bash entry points on Ubuntu. `.gitattributes` forces LF endings for shell scripts.

Install these prerequisites:

- Git for Windows, including Git Bash
- Python 3.13
- Node.js 24 with Corepack
- Docker Desktop with Docker Compose v2, WSL 2, and hardware virtualization enabled

## First-time setup

From Git Bash:

```bash
./scripts/setup.sh
./scripts/services.sh up
./scripts/migrate.sh
python scripts/provision-local-employee.py --email you@example.invalid --display-name "Local Employee" --allow-project-creation
```

After provisioning, request a link on the web sign-in page. The synthetic delivery adapter writes
the latest link to `.artifacts/dev-mailbox/latest.json`. Open that link in the same browser. Requests
for unknown or disabled addresses return the same message and produce no mail. Links expire after ten
minutes and can be used once. Never enable this adapter for confidential, staging, or production use.

An opt-in Microsoft Graph mail adapter is available for an isolated development/test tenant. Follow
[the Graph Mail setup guide](docs/integrations/microsoft-graph-mail.md), then select
`VERELO_MAGIC_LINK_DELIVERY=microsoft_graph`. This changes delivery only: the account allowlist,
single-use token, session, RLS and project authorization remain inside Verelo. The current approved
architecture still requires Entra SSO—not email magic links—for confidential production use.

`setup.sh` copies `.env.example` to the ignored `.env` file if needed, installs `uv` when absent, and installs the locked Python and pnpm dependencies. The environment template contains synthetic local defaults and secret names only. Keep API keys and real tenant/account identifiers out of repository files.

The local database initializes separate `verelo_migrator`, `verelo_api`, and `verelo_worker` roles. The Docker bootstrap administrator is only used by the image entrypoint. Deployed environments must supply distinct managed credentials rather than the synthetic passwords in `.env.example`.

Verify PostgreSQL is healthy:

```bash
./scripts/services.sh status
```

## Run the applications

Open a separate Git Bash terminal for each process you need:

```bash
./scripts/dev.sh api
./scripts/dev.sh worker
./scripts/dev.sh web
./scripts/dev.sh desktop
```

The API defaults to `http://127.0.0.1:8000`. Use its health endpoint to verify startup:

```bash
curl --fail http://127.0.0.1:8000/health
```

The web application now uses the local authenticated API after sign-in. Each provisioned employee
has a personal home/profile view and sees only projects allowed by their current database membership.
Project owners can add another already-provisioned employee by exact email and assign reader,
contributor, or owner access. Email is a lookup/login address, never the permanent identity key and
never a domain-wide access grant. Start it with `./scripts/dev.sh web` and open the Vite URL printed
in the terminal (normally `http://127.0.0.1:5173`). Provider-backed content remains synthetic until
the relevant external integration gate is approved.

The connected web product can create projects and meeting documents; upload WAV, MP3, M4A, WebM,
TXT, VTT, SRT, or canonical transcript JSON; inspect the immutable cleanup draft; save a corrected
draft; approve/publish as a project owner; and download deterministic TXT, Markdown, or JSON output.
Audio is decoded with the pinned FFmpeg-backed media library before the synthetic AssemblyAI adapter
produces a fictional diarized transcript. Publication creates immutable passages and durable index
jobs and updates the active version plus outbox event atomically. Recall and AssemblyAI credentials
are intentionally neither required nor read in fake mode.

The credential-free Phase 1–2 runtime also includes persistent capture recovery, ordered immutable
audio chunks, four-format audio quarantine, synthetic Recall and AssemblyAI adapters, deterministic
speaker/timestamp reconciliation, scoped durable worker/outbox execution, session lifecycle checks,
and content-free operational signals. Run `./scripts/backup-restore-smoke.sh` to exercise an isolated
database plus authoritative-object backup and hash-verified restore.

The Electron application now captures microphone plus desktop audio into WebM and can persist chunks,
recover its active capture session after restart, finalize the independent original, and create a
processed ingestion. With no desktop connection variables it remains in safe synthetic preview mode.
For an isolated local connected run, sign in and create a document in the web app, then export the
browser's `verelo_session` cookie and `/api/v1/me` CSRF value into the four ignored
`VERELO_DESKTOP_*` variables documented in `.env.example` before running `./scripts/dev.sh desktop`.
These opaque values are temporary local credentials: never commit, log, or place them in a packaged
application. Recall replaces this development capture transport only after R1 passes.

The durable worker requires explicit service grants rather than discovering projects globally. After
creating a project, provision its local worker scope and copy the printed values into ignored `.env`:

```bash
python scripts/provision-local-worker.py --project-id <project-uuid>
./scripts/dev.sh worker
```

Stop local services without deleting the database volume:

```bash
./scripts/services.sh down
```

## Standard commands

| Task                                           | Command                           |
| ---------------------------------------------- | --------------------------------- |
| Install locked dependencies                    | `./scripts/setup.sh`              |
| Start local PostgreSQL + pgvector              | `./scripts/services.sh up`        |
| Show service status                            | `./scripts/services.sh status`    |
| Tail PostgreSQL logs                           | `./scripts/services.sh logs`      |
| Stop local services                            | `./scripts/services.sh down`      |
| Apply migrations                               | `./scripts/migrate.sh`            |
| Run API/worker/web/desktop                     | `./scripts/dev.sh <target>`       |
| Launch a complete attended Recall test         | `./scripts/live-test-run.sh`      |
| Run format, lint, type, test, and build checks | `./scripts/check.sh`              |
| Run secret and dependency scans                | `./scripts/security-check.sh all` |
| Validate migrations against a clean database   | `./scripts/check-migrations.sh`   |
| Exercise isolated database/object restore      | `./scripts/backup-restore-smoke.sh` |
| Run the complete local PR gate                 | `./scripts/pr-ready.sh`           |

Focused toolchain commands remain available through `python -m uv run ...` and `corepack pnpm ...`; the repository scripts are the shared local and CI entry points. These forms work even when Windows has not added package-manager shims to `PATH`. The secret scan requires either a local `gitleaks` executable or Docker; CI runs the pinned container automatically.

## Configuration and integrations

Application settings use the `VERELO_` prefix and are validated at startup. Local development must keep `VERELO_INTEGRATIONS_MODE=fake`. Provider variables in `.env.example` are commented names, not credentials or proof of a working integration.

Before a live connector is enabled, follow the
[full MVP provider setup runbook](docs/FULL_MVP_PROVIDER_SETUP.md),
[live capture/transcription setup guide](docs/LIVE_CAPTURE_TRANSCRIPTION_SETUP.md),
[docs/INTEGRATIONS.md](docs/INTEGRATIONS.md), and its provider guide. Recall's R1 audio handoff and
Microsoft Graph's G1 destination/permission arrangement require recorded live feasibility evidence.
No confidential data may be used until the approvals and gates in `ARCHITECTURE.md` are complete.
