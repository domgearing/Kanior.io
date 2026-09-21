# Local infrastructure

KaniorAI uses Docker Compose for local PostgreSQL 17 with pgvector. Application processes run from the checkout. On Windows, run the repository `.sh` commands in Git Bash.

## Configuration

`infra/local/compose.yaml` reads safe local defaults from `.env.example`; `./scripts/setup.sh` copies that file to ignored `.env` when needed. Keep local overrides in `.env` and never put live provider credentials or production identifiers there.

The PostgreSQL service binds only to `127.0.0.1:${KANIOR_POSTGRES_PORT:-5432}`. The named `postgres-data` volume persists the database. On the first initialization of an empty volume, `infra/local/init/001-roles.sh` installs pgvector and creates distinct local roles:

- `kanior_migrator` owns/applies reviewed schema changes;
- `kanior_api` is the restricted API runtime role;
- `kanior_worker` is the restricted worker role;
- `kanior_admin` is the local container bootstrap administrator only.

The example passwords are disposable local values. Staging and production must inject separate secret-managed credentials and must never give the API or worker the migrator role.

## Start and inspect

From the repository root:

```bash
./scripts/services.sh up
./scripts/services.sh status
./scripts/services.sh logs
```

Compose waits for `pg_isready` against the configured database. The health check runs every five seconds, times out after five seconds, and allows ten retries after a five-second start period.

Apply all migrations with the dedicated local migrator URL from `.env`:

```bash
./scripts/migrate.sh
```

Check current containers without the wrapper when diagnosing Compose itself:

```bash
docker compose --env-file .env -f infra/local/compose.yaml ps
```

## Stop and reset

Stop containers while preserving the database volume:

```bash
./scripts/services.sh down
```

To delete all local KaniorAI database state and recreate it from zero, run:

```bash
docker compose --env-file .env -f infra/local/compose.yaml down --volumes
./scripts/services.sh up
./scripts/migrate.sh
```

The reset command is destructive only to the local Compose volume. The role-init script runs only when PostgreSQL initializes the new empty volume; changing local role passwords in `.env` does not update an existing volume. Reset the volume after changing those local values.

## Migration verification

The PR migration gate starts a disposable pgvector database when Docker is available, migrates it from zero, and removes the container afterward:

```bash
./scripts/check-migrations.sh
```

CI may provide `PR_GATE_DATABASE_URL` instead. The gate maps that URL to Alembic's migrator connection setting and does not require provider credentials. Runtime RLS/integration tests must connect as the restricted API and worker roles; a passing migration as an administrator or migrator does not prove runtime isolation.

## Troubleshooting

- If port 5432 is occupied, set `KANIOR_POSTGRES_PORT` in `.env` and update the three local database URLs to the same port.
- If role initialization did not run, confirm the volume was empty; then use the reset procedure above.
- If Docker is missing, install Docker Desktop with Compose v2. Unit and contract checks can still run, but migration and RLS integration gates remain incomplete.
- If the container is unhealthy, run `./scripts/services.sh logs` and verify the values in `.env` are synthetic local configuration.
