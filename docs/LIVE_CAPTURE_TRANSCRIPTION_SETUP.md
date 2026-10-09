# Live capture and transcript-generation setup

Verified against official provider documentation: **2026-09-25**.

This is the operator guide for moving Verelo's Phase 2 path from local synthetic capture/storage/
transcription to:

```text
Electron + Recall Desktop Recording SDK
    -> Recall audio artifact
    -> independent Backblaze B2 original
    -> AssemblyAI pre-recorded transcription
    -> Verelo cleanup, approval, publication, and downloads
```

## Read this first: current repository boundary

External account setup and credentials are necessary, but they are not sufficient today. The
repository currently contains:

- a connected Electron recorder using Electron's native capture path;
- a synthetic Recall adapter;
- local immutable object storage;
- a synthetic AssemblyAI adapter;
- the complete internal ingestion, approval, and publication workflow.

The live Recall SDK adapter, Recall webhook route, Backblaze S3 adapter, and live AssemblyAI adapter
have not yet been implemented. Their R1/storage/STT smoke gates intentionally block activation.
Adding the variables below now will not make those adapters live. Keep
`VERELO_INTEGRATIONS_MODE=fake` until the implementation and cutover checklist at the end passes.

Do not use confidential meetings during setup. Use a fictional scripted two-speaker meeting.

## 1. Decide and record one regional layout

Before creating resources, select regions that your company permits. Record:

```text
Recall workspace region:
Backblaze account/bucket region:
AssemblyAI API region:
Verelo API hosting region:
Approved test-data classification: fictional only
```

Recall region and API URL must match:

| Recall workspace | API/SDK base URL |
|---|---|
| US pay-as-you-go | `https://us-west-2.recall.ai` |
| US monthly | `https://us-east-1.recall.ai` |
| EU | `https://eu-central-1.recall.ai` |
| Japan | `https://ap-northeast-1.recall.ai` |

AssemblyAI's documented pre-recorded endpoints are:

| Residency | API base URL |
|---|---|
| US/default | `https://api.assemblyai.com` |
| EU | `https://api.eu.assemblyai.com` |

Do not assume that choosing similarly named regions makes the complete processing chain compliant.
Company/security approval of every processor and data transfer is still required.

## 2. Secret placement rules

For an isolated local smoke test, the only environment file used by the repository scripts is:

```text
verelo.io/.env
```

The `.env` files in the parent directory, `docs/`, or `.venv/` are not used. `verelo.io/.env` is
ignored by git; verify before adding secrets:

```bash
git check-ignore -v .env
```

That command must print an ignore rule. Also run:

```bash
git status --ignored --short .env
```

For deployed staging/production, do not use a file. Put each secret in the hosting platform's secret
manager and inject it only into the API/worker process. Never put provider secrets in:

- `desktop/package.json`, Electron source, preload, renderer, or a packaged application;
- `web/` source or `VITE_*` variables;
- committed `.env.example` values;
- screenshots, chat messages, issue trackers, fixtures, or ordinary logs.

The Recall API key stays server-side. Electron receives only the short-lived/scoped Recall
`upload_token` returned for one SDK upload. B2 and AssemblyAI credentials also stay server-side.

## 3. Create Backblaze B2 storage

### 3.1 Create the account and private runtime bucket

1. Sign in to the Backblaze web console and enable **B2 Cloud Storage**.
2. Confirm the account region before continuing. A B2 account is tied to a region and its S3 endpoint
   must match that region.
3. Open **B2 Cloud Storage > Buckets > Create a Bucket**.
4. Use a globally unique, non-sensitive name such as:

   ```text
   verelo-dev-source-<random-suffix>
   ```

   Do not include a client, employee, project, or meeting name in the bucket name.
5. Select **Private**. Do not select public access.
6. Leave lifecycle deletion disabled for the initial test. Do not enable irreversible Object Lock
   until retention/hold policy has been approved.
7. Create the bucket and record:

   ```text
   bucket name
   bucket ID
   region (for example us-west-004)
   S3 endpoint (for example s3.us-west-004.backblazeb2.com)
   ```

Backblaze documents bucket creation and shows the endpoint on the bucket screen:
<https://www.backblaze.com/docs/en/cloud-storage-get-started-with-a-backblaze-integration>.

### 3.2 Create the independent backup bucket

Create a second private bucket, preferably under a separately administered account/boundary:

```text
verelo-dev-backup-<random-suffix>
```

The normal runtime identity must not be able to delete from this bucket. Do not use the runtime
bucket as its own backup.

### 3.3 Create the runtime application key

1. Open **B2 Cloud Storage > Application Keys**.
2. Select **Add a New Application Key**.
3. Name it `verelo-dev-runtime`.
4. Restrict **Allow Access to Bucket(s)** to the runtime bucket only.
5. Choose the narrowest read/write access that permits object upload, multipart upload, exact object
   read, and required listing.
6. Do not enable **Allow List All Bucket Names** unless the selected S3 client demonstrably requires
   the account-level `ListBuckets` operation. Verelo should address its configured bucket directly.
7. Add an object-name prefix such as `verelo-dev/` if used consistently by the adapter.
8. For a temporary feasibility key, set an expiry appropriate for the test window.
9. Select **Create New Key** and immediately store both values:

   ```text
   keyID          -> S3 access-key ID
   applicationKey -> S3 secret-access key (displayed only once)
   ```

Never use the master application key. Backblaze's official key guide explains bucket/prefix scoping
and the one-time display of `applicationKey`:
<https://www.backblaze.com/docs/cloud-storage-application-keys>.

The production runtime key must not have permanent purge authority. If the web-console preset grants
deletion, create a custom capability key through the supported B2 key API with only the operations
proved necessary by the pinned S3 client. Maintain a separate, controlled purge identity.

### 3.4 Create separate purge and backup credentials

- `verelo-dev-purge`: runtime bucket only; version listing and deletion capabilities; never injected
  into the normal API/worker process.
- `verelo-dev-backup`: backup bucket only; write/read required for the backup process. Ordinary
  runtime credentials must not control it.

Backblaze lists individual capabilities such as `listFiles`, `readFiles`, `writeFiles`, and
`deleteFiles` here:
<https://www.backblaze.com/docs/cloud-storage-application-key-capabilities>.

### 3.5 Local configuration names

Keep `VERELO_INTEGRATIONS_MODE=fake` for now. Prepare these values in `verelo.io/.env`; the entries
marked **secret** must contain the actual credential only in this ignored local file:

```dotenv
# Reserved for the live B2 adapter; not active until the cutover implementation passes.
VERELO_STORAGE_PROVIDER=backblaze_b2
VERELO_B2_S3_ENDPOINT=https://s3.<region>.backblazeb2.com
VERELO_B2_REGION=<exact-b2-region>
VERELO_B2_BUCKET_NAME=<private-runtime-bucket>
VERELO_B2_KEY_PREFIX=verelo-dev/
VERELO_B2_APPLICATION_KEY_ID=<runtime-key-id>
VERELO_B2_APPLICATION_KEY=<runtime-application-key-secret>
VERELO_B2_BACKUP_BUCKET_NAME=<private-backup-bucket>
VERELO_B2_PURGE_CREDENTIAL_REF=<secret-manager-reference-not-the-secret>
VERELO_B2_BACKUP_CREDENTIAL_REF=<secret-manager-reference-not-the-secret>
```

Do not place purge or backup secret values in the normal runtime `.env`. Use their reference names
only; exercise them through separately authorized operational commands.

## 4. Create the AssemblyAI transcription project and key

### 4.1 Create a dedicated project

1. Sign in to the AssemblyAI dashboard.
2. Create or select a project dedicated to Verelo development, such as `verelo-dev`.
3. Open **API Keys**.
4. Select **Create New API Key**.
5. Name it `Verelo development worker` and select **Create**.
6. Copy the key into the local secret location. Do not put it in Electron or the browser.

AssemblyAI keys are project-scoped; one project's key cannot access another project's uploaded files
or transcripts. Current dashboard steps are documented here:
<https://www.assemblyai.com/docs/faq/how-to-get-your-api-key>.

### 4.2 Confirm account controls

Before live testing, record the actual account values for:

- US or EU endpoint availability;
- data retention and deletion behavior for uploaded audio and transcript results;
- model-training opt-out status;
- pre-recorded transcription concurrency;
- spending/billing alert and hard operational ceiling;
- access to the chosen exact speech model.

Use a fictional two-speaker recording for the smoke test. Verelo's approved asynchronous path enables
speaker diarization and preserves timed utterances/words; AssemblyAI documents `speaker_labels: true`
here: <https://www.assemblyai.com/docs/pre-recorded-audio/label-speakers>.

The currently approved Verelo model pin is `universal-3-5-pro`. Model identifiers are temporally
unstable; the live adapter implementation must confirm the account accepts that exact identifier
immediately before activation and record the returned `speech_model_used`. Do not silently substitute
an account default or another model.

### 4.3 Local configuration names

```dotenv
# Reserved for the live AssemblyAI adapter; not active until its smoke gate passes.
VERELO_TRANSCRIPTION_PROVIDER=assemblyai
VERELO_ASSEMBLYAI_API_BASE_URL=https://api.assemblyai.com
# Use https://api.eu.assemblyai.com only for an approved EU account/path.
VERELO_ASSEMBLYAI_API_KEY=<assemblyai-project-api-key>
VERELO_ASSEMBLYAI_SPEECH_MODEL=universal-3-5-pro
VERELO_ASSEMBLYAI_MAX_CONCURRENT_JOBS=<verified-account-limit>
```

The API and worker need the key. Electron and the web application do not.

## 5. Create the Recall workspace, API key, and webhook secret

### 5.1 Create/select the workspace and region

1. Create or select a Recall workspace dedicated to Verelo development.
2. Record whether it is US pay-as-you-go, US monthly, EU, or Japan.
3. Use the matching regional dashboard and API base URL from section 1 for every API key, webhook,
   SDK initialization, upload, recording lookup, and cleanup operation.
4. If possible, create a service-account user for the production key rather than tying it to an
   employee who may leave.

Recall states that API keys belong to individual users but have workspace-scoped access and do not
expire automatically; rotation requires explicitly disabling the old key:
<https://docs.recall.ai/reference/authentication>.

### 5.2 Generate the Recall API key

Open the API-key dashboard for the selected region:

```text
https://us-west-2.recall.ai/dashboard/developers/api-keys
https://us-east-1.recall.ai/dashboard/developers/api-keys
https://eu-central-1.recall.ai/dashboard/developers/api-keys
https://ap-northeast-1.recall.ai/dashboard/developers/api-keys
```

Create a key named `verelo-dev-server`, copy it once into the server secret location, and record its
creation date/owner. It is sent in the server-side `Authorization` header. It must never be bundled
with Electron.

### 5.3 Generate the workspace verification secret

On the same regional developer/API-key dashboard, create or reveal the workspace webhook/
verification secret. Store it separately from the API key. Verelo must verify the raw request body,
`webhook-id`, `webhook-timestamp`, and `webhook-signature` before accepting any callback. Recall's
current verification requirements are here:
<https://docs.recall.ai/docs/authenticating-requests-from-recallai>.

### 5.4 Provide a public HTTPS callback

Recall cannot call `127.0.0.1` directly. For development, use a stable HTTPS development tunnel or a
deployed isolated API. The final URL will be:

```text
https://<public-test-api>/api/v1/webhooks/recall
```

Do not configure this yet: that route is not present in the current repository. Configure it only
after the signed webhook implementation exists and rejects invalid/replayed requests.

When the route is implemented:

1. Open the regional Recall **Webhooks** dashboard.
2. Select **Add Endpoint**.
3. Enter the exact HTTPS URL.
4. Subscribe to the Desktop SDK upload/recording lifecycle events required by the implemented
   connector, including successful and failed completion.
5. Save it and send a provider test delivery.
6. Prove an invalid signature and a replayed delivery are rejected before continuing.

Recall documents dashboard webhook setup/retries here:
<https://docs.recall.ai/reference/webhooks-overview>.

### 5.5 Local configuration names

```dotenv
# Reserved for the live Recall adapter; not active until R1 passes.
VERELO_CAPTURE_PROVIDER=recall_desktop
VERELO_RECALL_REGION=<us-west-2|us-east-1|eu-central-1|ap-northeast-1>
VERELO_RECALL_API_BASE_URL=https://<matching-region>.recall.ai
VERELO_RECALL_API_KEY=<recall-server-api-key>
VERELO_RECALL_WORKSPACE_VERIFICATION_SECRET=<recall-workspace-secret>
VERELO_RECALL_WEBHOOK_URL=https://<public-test-api>/api/v1/webhooks/recall
VERELO_RECALL_CAPTURE_MODE=audio_only
```

## 6. Recall Desktop SDK and Electron

Electron does not require an API key. Recall's npm package runs in Electron, while the Verelo backend
uses the Recall API key to create one SDK upload and returns only its `upload_token` to the authorized
desktop process. Recall documents this lifecycle and the `startRecording` call here:
<https://docs.recall.ai/docs/desktop-sdk>.

As of this guide's verification date, npm reports the stable package as
`@recallai/desktop-sdk@2.0.33`. Recheck immediately before the R1 branch:

```bash
npm view @recallai/desktop-sdk version dist-tags engines --json
```

Do not install `@nightly`. After recording the reviewed version in R1, install the exact version:

```bash
corepack pnpm --filter @verelo/desktop add --save-exact @recallai/desktop-sdk@2.0.33
```

The connector implementation must:

1. initialize the SDK with the exact regional Recall API URL;
2. receive `meeting-detected` events for supported Zoom, Teams, and browser clients;
3. request an authorized upload token from Verelo's backend;
4. call `startRecording({windowId, uploadToken})`;
5. support explicit stop/pause/resume and visible interruption states;
6. never expose the Recall API key to Electron;
7. wait for verified asynchronous completion before resolving media;
8. copy the audio bytes independently into B2 and verify SHA-256/duration before transcription;
9. retain restart/idempotency state without creating duplicate paid uploads.

For whole-desktop/in-person audio, Recall documents `prepareDesktopAudioRecording()`:
<https://docs.recall.ai/docs/desktop-recording-sdk-methods>.

On Windows, test managed versions of Zoom, Teams, Chrome/Edge, and the exact Electron build. On macOS,
request microphone, accessibility, and screen-capture permissions and include the required packaged
application usage descriptions. Unsupported OS/client combinations must be displayed as unsupported.

## 7. Required R1 and live-provider tests

### Repository smoke commands

The live commands are deliberately excluded from normal CI. Rotate any credential ever pasted into
chat, a ticket, a log, or a shell command before using them. Keep `VERELO_INTEGRATIONS_MODE=fake`
until the credential preflight is clean; the smoke commands opt into provider traffic explicitly.

Run B2 only:

```powershell
uv run python scripts/live-provider-smoke.py `
  --provider b2 `
  --confirm-fictional-data
```

Run B2 plus AssemblyAI with a fictional, consenting two-speaker recording:

```powershell
uv run python scripts/live-provider-smoke.py `
  --provider all `
  --audio "C:\Users\<user>\Downloads\verelo-fictional-two-speaker.wav" `
  --confirm-fictional-data
```

The command checks private/anonymous access, pinned versions, range reads, multipart completion and
reconciliation, runtime delete denial, independent backup restore, `/v2/upload`, pinned
`speech_models=["universal-3-5-pro"]`, polling, diarization, raw-response persistence, duplicate
operation handling, and transcript deletion. Successful runs write sanitized reports under
`docs/integrations/evidence/`; failed runs do not write PASS reports. The backup smoke object is
retained for reviewer confirmation and must later be removed with the backup identity.

For Recall, expose the application route `/api/v1/webhooks/recall` through a stable HTTPS tunnel or
test deployment. Do not use a Svix Play inbox as the application destination. After an attended
fictional recording produces a verified `sdk_upload.complete` row, obtain the recording ID from a
restricted operator query and run:

```powershell
uv run python scripts/recall-r1-smoke.py `
  --recording-id "<restricted-recording-id>" `
  --client-matrix "Windows 11 build <build>; <meeting client/version>" `
  --confirm-fictional-data `
  --confirm-both-voices-audible `
  --confirm-interruption-restart-tested
```

That command resolves `media_shortcuts.audio_mixed.data.download_url`, downloads without forwarding
the Recall API authorization header, decodes and hashes the original, copies it to version-pinned B2,
submits the verified copy to AssemblyAI, confirms two diarized speakers, deletes the Recall recording,
and proves the independent B2 bytes remain unchanged. Provider identifiers stay out of the report.

After R1 has passed and the application is running in `live` integrations mode, normal captures no
longer require the smoke command. The API persists the authorized SDK-upload-to-capture mapping and
the signed webhook envelope. The durable worker reconciles each `sdk_upload.complete` event into one
project-scoped `recall_ingest` job, copies and verifies `audio_mixed` in B2, creates the source asset
and ingestion, and submits the independently stored object to AssemblyAI. Start the worker with the
same project scopes provisioned by `scripts/provision-local-worker.py`; retries reuse the event,
copy, and transcription operation keys. The smoke command remains the attended feasibility and
provider-cleanup check, not the production ingestion mechanism.

For an attended local test after filling the ignored `.env` values, launch the complete runtime from
Git Bash with:

```bash
./scripts/live-test-run.sh
```

The launcher starts PostgreSQL, applies migrations, validates live Recall/B2/AssemblyAI settings,
provisions local worker grants, and starts the API, worker supervisor, web app, and
Electron recorder. Sign in within Electron, then select or create a project and meeting there. For local
mailbox delivery, request a one-time password in Electron's web sign-in window and copy the
`password` field from `.artifacts/dev-mailbox/latest.json`. The worker supervisor adds new local
projects while the launcher runs. The public Recall tunnel remains an operator prerequisite.

Complete the detailed procedure in [integrations/recall.md](integrations/recall.md) with fictional
audio. At minimum, prove:

- local and remote voices are both present in the captured audio;
- no Recall bot, video, or Recall transcription was silently enabled;
- the SDK upload token is scoped and the server API key never reaches Electron;
- completion/failure callbacks are signed, timestamp-checked, and replay-resistant;
- duplicate/out-of-order events create one source asset;
- the Recall artifact is copied into B2, decoded, and hash-verified;
- provider deletion does not delete the independent B2 original;
- disconnect, SDK/app restart, and interrupted recording produce visible recovery/gap states;
- B2 anonymous/unrelated-bucket reads fail and the runtime cannot purge;
- AssemblyAI receives the verified stored audio, returns diarized/timed results, and its exact raw
  response is stored before parsing;
- AssemblyAI completion does not automatically publish a transcript;
- approval, publication, passage/index intent, and TXT/Markdown/JSON download still use the same
  Verelo workflow.

Record only sanitized evidence using [integrations/EVIDENCE_TEMPLATE.md](integrations/EVIDENCE_TEMPLATE.md).

## 8. Cutover checklist

Do not switch live mode until every box below is true:

```text
[ ] Backblaze account/region approved
[ ] Private runtime and independent backup buckets created
[ ] Runtime, purge, and backup keys separated and least-privilege tested
[ ] B2 live adapter implemented with version-pinned reads and multipart recovery
[ ] AssemblyAI project/key/account controls approved
[ ] AssemblyAI live adapter implemented with upload/submit/poll/raw-store/delete behavior
[ ] Recall workspace/API key/verification secret created in one region
[ ] Public signed Recall webhook route implemented and negative-tested
[ ] Exact stable Recall Desktop SDK version pinned
[ ] R1 client/OS matrix passed with fictional audio
[ ] End-to-end live fictional meeting passed
[ ] Provider retention/deletion and cost controls recorded
[ ] No provider secret appears in web/Electron bundles, git, logs, or generated artifacts
```

Only then change the server/worker environment to:

```dotenv
VERELO_INTEGRATIONS_MODE=live
VERELO_STORAGE_PROVIDER=backblaze_b2
VERELO_TRANSCRIPTION_PROVIDER=assemblyai
VERELO_CAPTURE_PROVIDER=recall_desktop
```

Startup must fail closed if any selected live adapter or required value is absent. It must never fall
back silently to a fake adapter in live mode.

## 9. What to provide for the implementation step

Do **not** send API keys or secret values in chat. After completing the provider dashboards, provide
only:

```text
Recall region and API base URL (not the key)
Recall workspace creation date (for webhook-verification behavior)
Public test webhook hostname/path (not its secret)
Backblaze region, S3 endpoint, runtime bucket name, backup bucket name (not keys)
AssemblyAI US/EU base URL and approved exact model name (not the key)
Target Windows/macOS versions and Zoom/Teams/browser versions for R1
Confirmation that all secrets were placed in verelo.io/.env or the deployment secret manager
```

At that point, the remaining work is connector implementation and live smoke testing—not additional
account setup.
