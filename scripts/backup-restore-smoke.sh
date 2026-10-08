#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Backup/restore smoke test requires Docker." >&2
  exit 1
fi

container_name="verelo-restore-smoke-$$"
exercise_dir="$(mktemp -d "${TMPDIR:-/tmp}/verelo-restore-smoke.XXXXXX")"
cleanup() {
  docker rm -f "$container_name" >/dev/null 2>&1 || true
  rm -rf -- "$exercise_dir"
}
trap cleanup EXIT

section "Start isolated restore exercise"
docker run -d --rm --name "$container_name" \
  -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=verelo_source \
  -p 127.0.0.1::5432 pgvector/pgvector:0.8.1-pg17 >/dev/null
for _ in $(seq 1 30); do
  if docker exec "$container_name" pg_isready -U postgres -d verelo_source >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker exec "$container_name" pg_isready -U postgres -d verelo_source >/dev/null
docker exec "$container_name" psql -v ON_ERROR_STOP=1 -U postgres -d verelo_source \
  -c "CREATE ROLE verelo_migrator LOGIN; CREATE ROLE verelo_api LOGIN; CREATE ROLE verelo_worker LOGIN; GRANT USAGE, CREATE ON SCHEMA public TO verelo_migrator; GRANT USAGE ON SCHEMA public TO verelo_api, verelo_worker;" >/dev/null
port="$(docker port "$container_name" 5432/tcp | awk -F: '{print $NF}')"
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:${port}/verelo_source"
python -m uv run alembic upgrade head >/dev/null

probe_id="00000000-0000-4000-8000-000000000901"
docker exec "$container_name" psql -v ON_ERROR_STOP=1 -U postgres -d verelo_source \
  -c "INSERT INTO tenants (id,entra_tenant_id,policy_config_ref,region) VALUES ('$probe_id','00000000-0000-4000-8000-000000000902','synthetic-policy','synthetic-region');" >/dev/null

source_objects="$exercise_dir/source-objects"
restored_objects="$exercise_dir/restored-objects"
mkdir -p "$source_objects/aa" "$restored_objects"
printf 'synthetic original audio' >"$source_objects/aa/audio"
printf 'synthetic canonical transcript' >"$source_objects/aa/transcript"
(cd "$source_objects" && find . -type f -print0 | sort -z | xargs -0 sha256sum) \
  >"$exercise_dir/object-manifest.sha256"

section "Back up database and authoritative objects"
docker exec "$container_name" pg_dump -U postgres -d verelo_source -Fc \
  >"$exercise_dir/database.dump"
tar -C "$source_objects" -czf "$exercise_dir/objects.tar.gz" .

section "Restore to an isolated target"
docker exec "$container_name" createdb -U postgres verelo_restored
docker exec -i "$container_name" pg_restore -U postgres -d verelo_restored \
  --no-owner --no-privileges <"$exercise_dir/database.dump"
tar -C "$restored_objects" -xzf "$exercise_dir/objects.tar.gz"

restored_probe="$(docker exec "$container_name" psql -At -U postgres -d verelo_restored \
  -c "SELECT id FROM tenants WHERE id='$probe_id';")"
test "$restored_probe" = "$probe_id"
(cd "$restored_objects" && sha256sum --check "$exercise_dir/object-manifest.sha256")
restored_revision="$(docker exec "$container_name" psql -At -U postgres -d verelo_restored \
  -c "SELECT version_num FROM alembic_version;")"
test -n "$restored_revision"

section "Backup/restore smoke passed"
printf 'Verified database marker, migration revision, and %s object hashes.\n' \
  "$(wc -l <"$exercise_dir/object-manifest.sha256" | tr -d ' ')"
