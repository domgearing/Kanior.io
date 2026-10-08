#!/usr/bin/env bash
set -euo pipefail

# This runs only when Docker initializes an empty local volume. Values come
# from the synthetic local environment and must never be reused in deployment.
psql \
  --set=ON_ERROR_STOP=1 \
  --set=migrator_password="$VERELO_MIGRATOR_DB_PASSWORD" \
  --set=api_password="$VERELO_API_DB_PASSWORD" \
  --set=worker_password="$VERELO_WORKER_DB_PASSWORD" \
  --set=database_name="$POSTGRES_DB" \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector;

CREATE ROLE verelo_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
  PASSWORD :'migrator_password';
CREATE ROLE verelo_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
  PASSWORD :'api_password';
CREATE ROLE verelo_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
  PASSWORD :'worker_password';

GRANT CONNECT ON DATABASE :"database_name" TO verelo_migrator, verelo_api, verelo_worker;
GRANT USAGE, CREATE ON SCHEMA public TO verelo_migrator;
GRANT USAGE ON SCHEMA public TO verelo_api, verelo_worker;
SQL
