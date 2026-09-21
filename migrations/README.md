# Migrations

Alembic migrations are reviewed SQL for the canonical schema in
`docs/DATA_MODEL.md`. Apply them using the distinct migrator identity; API and
worker identities must never own tables or run DDL.
