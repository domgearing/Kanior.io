# Local release outage and recovery drill

Scope: one signed-in Windows user's **local/test** release. This is not an always-on team
deployment, a confidential-data approval, or a production availability promise. The PC, Docker
Desktop, PostgreSQL, the API/worker processes, and `cloudflared` must all be available. Scheduled
tasks start at user sign-in, not while the computer is off or before that user signs in.

## Baseline and safe diagnostics

From the repository root, run `uv run python scripts/local_release_status.py`. Check the two
scheduled tasks with `Get-ScheduledTaskInfo -TaskName 'Verelo Local Release'` and
`Get-ScheduledTaskInfo -TaskName 'Verelo Desktop'`, and inspect the tunnel service with
`Get-Service cloudflared` in PowerShell. The safe, metadata-only transition log is
`.artifacts/local-release/events.jsonl`; the supervisor status is
`.artifacts/local-release/status.json`. Do not paste `.env`, the development mailbox, raw audio,
provider responses, or signed URLs into tickets or ordinary logs.

The status checker tests local/public HTTP 200 responses and TLS reachability to provider hosts.
It does **not** test provider credentials, quotas, paid transcription success, delivery of a Recall
webhook, a project's worker grant, or whether the job queue is draining. An `OK` process is not
proof that every project worker or recording is healthy. Health is sampled by the supervisor
roughly every minute; a Windows notification is attempted after two matching bad samples, but
Windows may suppress it. The status command and actual recording history are authoritative.

| Failure | What continues / what stops | Recovery and verification |
| --- | --- | --- |
| Worker process exits | Local API/web and signed Recall webhook ingress may remain available. New events and jobs persist, but copying audio, transcription, and later processing stop. The top-level supervisor checks child processes about every five seconds and restarts a failed worker supervisor. A leased job can be reclaimed after its 60-second lease expires; failed handlers retry with bounded backoff and can reach dead letter. | Check `worker_process`, recent metadata events, and the recording's stage. If the supervisor is stopped, restart **Verelo Local Release** only when no capture is active. Confirm the worker returns and an existing fictional queued recording advances; an alive process alone is insufficient. Do not manually resubmit a provider job while its external outcome is unknown. |
| Tunnel or DNS route down | Local `http://127.0.0.1:8000/` may still work, but `dev.verelo.io`/`dev-api.verelo.io` may not. Recall cannot deliver a webhook through a broken public route. Audio already uploaded to Recall may therefore lack a stored completion event; worker restart alone cannot invent that missing event. | Compare `local_api`/`local_web` with `public_api`/`public_web`; check `Get-Service cloudflared`, Cloudflare routes, and DNS. Both hostnames must forward to local port 8000, and `/ready` must return 200 publicly. Restore the service/route without restarting a healthy API. For any recording stopped during the outage, verify its Recall completion event and meeting ingestion; reconcile a missing event using the recorded `recording_id` and the documented R1 workflow, never by blindly repeating a recording or provider submission. |
| Recall, AssemblyAI, or B2 unavailable | A reachable TLS endpoint can still reject credentials, throttle requests, or fail a job. Recall grant failure returns a retryable service error; AssemblyAI or B2 failures can delay audio copy/transcription, playback, or backup. Durable job retries use bounded backoff (up to five minutes) and eventually dead-letter after their configured attempt limit. The web may keep showing a processing stage until the underlying job is reconciled; do not treat “process alive” as transcript ready. | Check the relevant provider's own status/account/quota and the ingestion's safe error/stage. Restore credentials or service only through the approved secret path. Confirm backup freshness separately. Once healthy, observe the existing job advance; if dead-lettered or an external operation has an uncertain outcome, inspect provider state and reconcile before an authorized retry. Use a fictional recording for end-to-end verification. |

If local API and public routes both fail, first check PostgreSQL, Docker Desktop, and the
**Verelo Local Release** task. Do not change tunnel DNS to point directly at a development Vite
server. A public route being up does not make the backend always-on when this Windows computer
is off.

## Backup/restore evidence and limits

Run `./scripts/backup-restore-smoke.sh` from Git Bash for an isolated synthetic drill. It migrates
a disposable database, backs up that database and two fictional objects, restores to an isolated
database/object tree, and verifies the migration revision, marker, and object hashes. It does not
touch the live database or B2 bucket. `./scripts/local-release-backup.sh` is the separate real
local snapshot procedure: it copies version-pinned objects to the independent backup bucket,
writes a manifest last, verifies copied hashes, and restores the database into a temporary
container. Neither drill reopens a recovered application. Full disaster recovery still requires
the authorization, deletion/hold, job/provider reconciliation, and reopening checks in
[database-object-restore.md](database-object-restore.md) and `ARCHITECTURE.md` §35.

After any outage, run the status command, confirm the most recent backup is verified, and take
one fictional recording through upload, transcription, review, and publication before declaring
the local test release recovered. Escalate missing source bytes, hash mismatches, unauthorized
reads, or uncertain provider submissions rather than forcing the workflow forward.

## Validation record — 2026-10-09

- `./scripts/pr-ready.sh` passed: unit/architecture/contract tests, web and desktop checks/builds,
  11 integration tests, a disposable migration through `0016_auth_request_rate_limit`, and the PR
  evaluation suite.
- `./scripts/backup-restore-smoke.sh` passed: isolated database marker and migration revision
  restored, with both fictional object hashes verified.
- `./scripts/local-release-backup.sh` passed: 15 version-pinned objects were verified in the
  independent backup bucket and the database dump restored in an isolated container. The live
  database was not replaced.
- At the end of the drill, local/public API and web, database, worker/API process checks, and
  backup were `OK`; `cloudflared` was Running and Automatic. Provider checks were TLS-only.

Worker, tunnel, and provider outages were **not deliberately injected into the live local
release** during this drill. The failure behavior above is based on the supervisor, durable-job,
webhook, and status implementations and their tests. A future controlled outage drill must use
fictional data, confirm no capture is active, and reconcile any uncertain provider operation.
