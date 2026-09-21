# Kanior.io

Kanior is an internal transcript creation, processing, and query application. It records or imports expert calls and internal meetings, preserves their sources securely, and lets authorized users retrieve verifiable quotes from approved transcript versions.

The repository currently provides the initial runnable Phase 1 scaffold: a FastAPI application and worker, PostgreSQL 17 with pgvector, Alembic migrations, deterministic synthetic provider adapters, and minimal web and desktop shells. It is for synthetic local development only; the remaining Phase 1 security gates, provider feasibility checks, and company-policy decisions still block confidential traffic.

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
```

`setup.sh` copies `.env.example` to the ignored `.env` file if needed, installs `uv` when absent, and installs the locked Python and pnpm dependencies. The environment template contains synthetic local defaults and secret names only. Keep API keys and real tenant/account identifiers out of repository files.

The local database initializes separate `kanior_migrator`, `kanior_api`, and `kanior_worker` roles. The Docker bootstrap administrator is only used by the image entrypoint. Deployed environments must supply distinct managed credentials rather than the synthetic passwords in `.env.example`.

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

Stop local services without deleting the database volume:

```bash
./scripts/services.sh down
```

## Standard commands

| Task | Command |
| --- | --- |
| Install locked dependencies | `./scripts/setup.sh` |
| Start local PostgreSQL + pgvector | `./scripts/services.sh up` |
| Show service status | `./scripts/services.sh status` |
| Tail PostgreSQL logs | `./scripts/services.sh logs` |
| Stop local services | `./scripts/services.sh down` |
| Apply migrations | `./scripts/migrate.sh` |
| Run API/worker/web/desktop | `./scripts/dev.sh <target>` |
| Run format, lint, type, test, and build checks | `./scripts/check.sh` |
| Run secret and dependency scans | `./scripts/security-check.sh all` |
| Validate migrations against a clean database | `./scripts/check-migrations.sh` |
| Run the complete local PR gate | `./scripts/pr-ready.sh` |

Focused toolchain commands remain available through `python -m uv run ...` and `corepack pnpm ...`; the repository scripts are the shared local and CI entry points. These forms work even when Windows has not added package-manager shims to `PATH`. The secret scan requires either a local `gitleaks` executable or Docker; CI runs the pinned container automatically.

## Configuration and integrations

Application settings use the `KANIOR_` prefix and are validated at startup. Local development must keep `KANIOR_INTEGRATIONS_MODE=fake`. Provider variables in `.env.example` are commented names, not credentials or proof of a working integration.

Before a live connector is enabled, follow [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) and its provider guide. Recall's R1 audio handoff and Microsoft Graph's G1 destination/permission arrangement require recorded live feasibility evidence. No confidential data may be used until the approvals and gates in `ARCHITECTURE.md` are complete.
