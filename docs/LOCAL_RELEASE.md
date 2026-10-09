# Single-user Windows local release

This is an attended, single-user **local/test** runtime, not approval for confidential company
traffic or team deployment. `ARCHITECTURE.md` §20 and §38 still require Entra and company policy
decisions for confidential use. The development launcher remains available separately.

## First-time update

From Git Bash at the repository root, with Docker Desktop available:

```bash
./scripts/local-release-update.sh
```

This installs locked dependencies, starts PostgreSQL, applies reviewed migrations, provisions
local worker grants, builds `web/dist` plus `desktop/dist`, and registers the per-user
`verelo-recorder://open` Windows link. It does **not** reset the database or start the application.
Run it intentionally after pulling a new version, ideally with the
local-release task stopped. Never put provider credentials in a `VITE_*` variable; the web build
subprocess receives only `VITE_API_BASE_URL`.

## Tunnel routes

The API and built web assets share local port 8000. In the existing Cloudflare named tunnel, set:

```text
dev.verelo.io      -> http://127.0.0.1:8000
dev-api.verelo.io  -> http://127.0.0.1:8000
```

Keep Recall's signed webhook URL at
`https://dev-api.verelo.io/api/v1/webhooks/recall`. Do not put Cloudflare Access in front of the
Recall webhook without a verified path-specific bypass. `VITE_API_BASE_URL` must remain
`https://dev-api.verelo.io` before rebuilding the web assets. Neither the built UI nor Electron
contains B2, Recall, or AssemblyAI keys.

## Start now or at sign-in

For an attended test from Git Bash:

```bash
./scripts/local-release-run.sh
```

The release runner does not build or migrate at startup. It waits for Compose PostgreSQL,
validates the local live configuration, then supervises a no-reload API and the existing
project-scoped worker supervisor. Its metadata-only status file is ignored by Git. If you
already have the development API on port 8000, stop that launcher first.

To register sign-in tasks for the current Windows user, run once in PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\install-local-startup.ps1"
```

Run that command from the repository root. The process-scoped execution-policy bypass does not
change the machine's policy. If the two tasks already exist, do not rerun the installer.

The two tasks are **Verelo Local Release** and **Verelo Desktop**. The backend task launches
Docker Desktop if needed, waits for its engine, then starts the release runner. The desktop task
waits for the local API and public web route, then opens the built Electron app in your interactive
session. If the public web route is still pointed at Vite, the desktop task exits safely and can
be started again after changing the tunnel route. The tasks
start at **sign-in**, not before login; Docker Desktop's per-user engine and Electron require that
session. The separately installed `cloudflared` service should remain Automatic.

After changing the tunnel route, stop any development launcher using port 8000 and start the tasks
without signing out:

```powershell
Start-ScheduledTask -TaskName 'Verelo Local Release'
Start-ScheduledTask -TaskName 'Verelo Desktop'
```

The web meeting panel also has **Open desktop recorder**. On this Windows computer, that link
opens the built Electron app (or focuses its existing window). The browser may ask permission to
open the external link. If you built the release before this link was added, register it once from
PowerShell in the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\install-desktop-link.ps1"
```

The handler is installed only for the current Windows user. It accepts only the fixed open link;
meeting selection and recording still require authenticated API commands and explicit consent.
It does not remotely launch Electron on another computer, install Electron, or start the backend.

## Health and troubleshooting

In local mode, enter your approved email on the web sign-in page, choose **Get one-time password**,
then copy the `password` field from the ignored `.artifacts/dev-mailbox/latest.json` into the
password field and choose **Sign in**. The password is single-use and expires after ten minutes;
request a new one for a later sign-in. Desktop sign-in opens the same web form in its sign-in
window; after signing in there, choose **Continue after signing in** in the recorder window.
Do not commit or share the mailbox file. This is only for local/test use.

From the repository root:

```bash
uv run python scripts/local_release_status.py
```

It checks the restricted database connection, local and public API/web paths, supervisor/API/worker
liveness, and TLS reachability to Recall, AssemblyAI, and B2. TLS reachability is **not** proof that
credentials or a paid transcription job work. A public-web failure immediately after switching
launchers usually means `dev.verelo.io` still points to the old Vite port 5173. A worker process
can be alive but have no project yet; create a project and the local worker supervisor provisions
its scope. The backend supervisor restarts child processes after unexpected exit, while Windows
Task Scheduler retries the top-level task if it fails.

The status command does not print secret values, transcripts, or signed URLs. Application stdout
is discarded by the background runner to avoid accidental confidential logs; for attended
diagnosis, stop the task and use `./scripts/live-test-run.sh` with fictional data.

## Local backups and failure diagnostics

### Web recorder-control smoke check

After applying migration `0015_recorder_remote_control` and restarting the API/web/desktop,
sign in to the web and desktop apps as the **same employee**. Keep the desktop window open with
`VERELO_DESKTOP_CAPTURE_PROVIDER=recall_desktop`. In the web app, open a writable project and
meeting. Its recorder panel should show the desktop as online within about 15 seconds. Confirm
recording consent, then click Start. Wait for **completed** and **recording**, then use Pause,
Resume, and Stop from the web page. Verify the desktop's visible state and the meeting's ingestion
history; command acknowledgement alone does not prove Recall uploaded audio. If the desktop is
closed or signed out, the panel shows offline and disables controls. The **Open desktop recorder**
link works only after its per-user Windows handler is registered on that computer. This is
local/test functionality, not a confidential staging approval.

The isolated `backup-restore-smoke.sh` uses synthetic data only. The real local-release backup
uses the separate B2 backup bucket configured in `.env` and the local PostgreSQL administrator
role. Keep the backup bucket private, in a separate failure domain, and grant its key only the
permissions needed for backup upload and verification. The backup bucket must not be the runtime
bucket. Use full-disk encryption on this Windows machine because database and object bytes are
briefly staged in temporary files during backup and verification. This is still a local/test
workflow; company retention, residency, and confidentiality decisions remain open.

From Git Bash at the repository root, run the first backup manually:

```bash
./scripts/local-release-backup.sh
```

The command exports one consistent PostgreSQL snapshot, copies every database-referenced,
version-pinned B2 object to the backup bucket, writes a manifest last, reads the copies back and
checks SHA-256 hashes, then restores the dump into an isolated temporary PostgreSQL container.
It does not replace the running database, delete backups, or make a restored system live. A
failed run leaves its incomplete backup prefix without a manifest; clean it up only after
reviewing the failure and retention policy. A full disaster recovery still requires reviewing
deletion/tombstone state, remapping restored B2 version references, reconciling in-flight jobs,
and authorizing service reopening under architecture §35.

After the manual backup passes, register a daily 03:00 task from PowerShell in the repository:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\install-local-backup.ps1"
```

The task is **Verelo Local Backup**. It runs in the signed-in user's session and starts Docker
Desktop if needed; missed runs start when the task becomes available. Check its last result with
`Get-ScheduledTaskInfo -TaskName 'Verelo Local Backup'`. The status command reports `backup:
DOWN` after a failed run or when no verified backup has completed in 48 hours. It prints a safe
failure code, not provider error text. While the signed-in backend task is running, the supervisor
checks every minute and attempts a Windows notification after two consecutive critical failures,
including a stale/failed backup. Windows may suppress notifications; the status command and Task
Scheduler result remain authoritative.
Restart **Verelo Local Release** when idle to activate supervisor changes after an update.

Metadata-only process and health transitions are recorded in
`.artifacts/local-release/events.jsonl` (bounded to roughly 1 MiB plus one rotated file).
Backup state is in `.artifacts/local-release/backup-status.json`. Neither file contains
credentials, object references, transcript text, or signed URLs. Child process output remains
discarded in background mode; use an attended fictional-data run for deeper diagnosis.

After a reboot/sign-in, verify both tasks are Running, the tunnel service is Running, the status
command succeeds, and a fictional recording reaches a published transcript. Then test recovery by
stopping a worker process and confirming the supervisor restarts it and the durable job resumes.

For the expected impact and safe recovery checks when the worker, tunnel/DNS, or a provider goes
down, use [the local outage runbook](../runbooks/local-release-outages.md). Its process and TLS
checks are diagnostic only; they do not turn this single-user signed-in runtime into an always-on
team service. The current release must still pass `./scripts/pr-ready.sh` and an isolated
backup/restore exercise before it is considered repeatable.
