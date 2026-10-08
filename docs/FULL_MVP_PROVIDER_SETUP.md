# Full MVP provider setup and activation

Status: operator runbook; no live credentials are required or stored in the repository.

For the exact Backblaze B2, AssemblyAI, Recall Desktop SDK, Electron, secret-placement, and cutover
procedure, use [LIVE_CAPTURE_TRANSCRIPTION_SETUP.md](LIVE_CAPTURE_TRANSCRIPTION_SETUP.md). That guide
also identifies the live adapters/webhook code that remains required; credentials alone do not switch
the current synthetic implementation to live providers.

This runbook describes the external setup needed to move the Phase 0-2 MVP from deterministic
synthetic providers to the production-shaped provider adapters. It does not approve a provider,
publish a public API contract, or mark a feasibility gate as passed. Complete the Phase 2 contract
checkpoint in [plans/active/005-phase-2-contract-checkpoint.md](plans/active/005-phase-2-contract-checkpoint.md)
before implementing or exposing the proposed ingestion routes.

## What each provider does

| Capability | Provider | Required for synthetic MVP | Required for live MVP |
|---|---|---:|---:|
| Employee sign-in | Microsoft Entra ID | No; magic-link test identity is available | Yes under the current production security decision |
| Development magic-link email | Microsoft Graph Mail | No; local outbox is available | Optional for non-production testing only |
| Desktop meeting/system-audio capture | Recall Desktop SDK | No; synthetic capture is available | Yes, after the R1 gate passes |
| Speech-to-text and diarization | AssemblyAI | No; deterministic synthetic results are available | Yes |
| Immutable governed object storage | Backblaze B2 | No; local object storage is available | Yes |

Recall Desktop capture is the single planned capture path for supported Zoom, Microsoft Teams,
browser meetings, microphone audio, and computer audio. It does not require separate Zoom or Teams
bot/API credentials. Exported meeting recordings and ordinary audio files enter through the upload
path. The approved Phase 2 proposal accepts WAV, MP3, M4A, and WebM audio, and TXT, VTT, SRT, and
JSON transcript input. Other containers/codecs must be rejected with a clear error until a decoder
test fixture and acceptance criterion are added; “any audio format” is not a safe or testable contract.

## Where configuration belongs

Never put a real credential in source control, a frontend environment variable, an Electron bundle,
documentation, a fixture, a support ticket, or a command-line argument.

- Local isolated smoke test: create an ignored `verelo.io/.env` from `.env.example` and add only test
  credentials. Confirm `git status --ignored` reports it as ignored before adding a value.
- Deployed environment: store secrets in the hosting platform's secret manager and inject them into
  the API/worker processes as environment variables. The web and Electron processes receive no
  provider secrets.
- Configuration IDs such as tenant/client IDs may be environment configuration, but use synthetic
  values in committed files.
- Keep separate identities for runtime storage, purge, backup, Graph mail, Entra login, and future
  OneDrive export. Do not reuse one application registration or master key.

The names documented below are the stable deployment interface. Some are reserved until the
corresponding live adapter is implemented after its gate; startup must reject `live` mode when a
selected adapter is unavailable or incomplete.

## 1. Microsoft Entra employee login

Use a development tenant or an isolated test app registration first. The application must be
single-tenant and user assignment must be required; tenant membership alone never grants Verelo
access. Verelo still maps the verified Entra subject to an enabled internal employee UUID and obtains
all project permissions from its own database.

Administrator setup:

1. In **Microsoft Entra admin center > Identity > Applications > App registrations**, select
   **New registration**. Use **Accounts in this organizational directory only**.
2. In **Authentication**, add a **Web** redirect URI matching the deployed callback exactly. Use an
   HTTPS URI such as `https://verelo-test.example/auth/entra/callback`; permit localhost only for an
   isolated developer registration.
3. Record the Directory (tenant) ID and Application (client) ID.
4. Create a short-lived client secret only for the initial test. Prefer an approved certificate or
   workload identity for deployed production. Copy a new secret directly to the secret manager; its
   value is shown only once.
5. In **Enterprise applications**, open the service principal, set **Properties > Assignment
   required?** to **Yes**, then assign only the test employees or a dedicated security group under
   **Users and groups**. Grant tenant-wide admin consent when required by the assignment model.
6. Do not add Microsoft Graph mail, directory, or file permissions to this login registration. OIDC
   scopes are `openid profile` and, only if needed for display, `email`.
7. Create each employee in Verelo separately and bind the immutable internal UUID to the verified
   tenant and subject identifiers. Never infer access from the email domain.

Server configuration (reserved until the Entra adapter is implemented):

```text
VERELO_ENVIRONMENT=production
VERELO_INTEGRATIONS_MODE=live
VERELO_IDENTITY_PROVIDER=entra
ENTRA_TENANT_ID=<directory-tenant-guid>
ENTRA_CLIENT_ID=<application-client-guid>
ENTRA_REDIRECT_URI=https://verelo.example/auth/entra/callback
ENTRA_CLIENT_CREDENTIAL_REF=<secret-manager-reference>
ENTRA_REQUIRED_EMPLOYEE_ROLE=<approved-role-if-used>
ENTRA_EMPLOYEE_GROUP_ID=<approved-group-if-used>
SESSION_SECRET_REF=<different-secret-manager-reference>
```

Activation evidence: assigned enabled employee succeeds; unassigned, guest, wrong-tenant, disabled,
expired-token, replayed-state, and invalid-CSRF cases fail; logout removes the server session; employee
disable immediately invalidates all sessions. Microsoft's documentation explains exact redirect URI
registration and why requiring assignment prevents unassigned users from signing in:
[redirect URIs](https://learn.microsoft.com/en-us/entra/identity-platform/how-to-add-redirect-uri) and
[application access assignment](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/what-is-access-management).

## 2. Microsoft Graph Mail for development magic links

This adapter is already implemented for local/test environments. It is not the production identity
provider under the current security decision.

1. Create a dedicated sender mailbox such as `verelo-login@company.example`.
2. Create a separate single-tenant app registration.
3. Add Microsoft Graph **application** permission `Mail.Send` and grant administrator consent.
4. In Exchange Online, use Application RBAC to grant `Application Mail.Send` only over that mailbox.
   An unrestricted tenant-wide mail app is not acceptable as the finished configuration.
5. Store the secret and configure the server exactly as shown in
   [integrations/microsoft-graph-mail.md](integrations/microsoft-graph-mail.md).
6. Prove the configured mailbox can send and a second mailbox cannot. A Graph `202 Accepted` means
   the request was accepted, not that delivery is guaranteed.

## 3. Backblaze B2 private storage

Create separate test and production buckets. Keep them private and enable versioning behavior needed
to address immutable object versions; do not configure a lifecycle rule that can silently delete
canonical evidence.

1. In Backblaze, create a private application-data bucket in the approved region.
2. Create a restricted runtime application key for that bucket/prefix. Start with only the capabilities
   needed for read, write, multipart operations, and required listing. The runtime identity must not
   have permanent purge authority.
3. Create a separate purge identity for controlled, audited version deletion.
4. Create a separately administered backup bucket and credentials that the runtime identity cannot
   delete or overwrite.
5. Record the bucket's S3-compatible endpoint and region. For S3-compatible clients, the application
   key ID is the access-key ID and the application key is the secret.

Server/worker configuration (reserved until the B2 adapter is implemented):

```text
B2_S3_ENDPOINT=https://s3.<region>.backblazeb2.com
B2_REGION=<provisioned-region>
B2_BUCKET_NAME=<private-runtime-bucket>
B2_APPLICATION_KEY_ID=<runtime-key-id>
B2_APPLICATION_KEY=<runtime-secret>
B2_PURGE_CREDENTIAL_REF=<separate-secret-reference>
B2_BACKUP_BUCKET_NAME=<independent-backup-bucket>
B2_BACKUP_CREDENTIAL_REF=<independent-backup-secret-reference>
```

Before activation, prove anonymous reads fail, unrelated prefixes fail, exact bytes and SHA-256 survive
single and multipart upload/readback, pinned versions remain stable, the runtime cannot purge, and a
backup can be restored with matching hashes. Use the official
[S3-compatible application-key guidance](https://www.backblaze.com/docs/cloud-storage-s3-compatible-app-keys).

## 4. AssemblyAI transcription

Use an isolated AssemblyAI account/project until retention, processing region, training controls,
quotas, and deletion behavior are approved. Verelo uploads verified original bytes from private
storage; it does not make the B2 bucket public.

1. Create the approved account/project in the AssemblyAI dashboard and generate a server-side API key.
2. Confirm the selected region supports the pinned speech model and speaker diarization.
3. Confirm account-specific data retention, training opt-out, upload/result deletion, spend limits,
   and concurrency limits with the administrator.
4. Put the key only in the API/worker secret store.

Server/worker configuration (reserved until the live adapter is implemented):

```text
ASSEMBLYAI_API_KEY=<secret>
ASSEMBLYAI_API_BASE_URL=https://api.assemblyai.com
ASSEMBLYAI_SPEECH_MODEL=universal-3-5-pro
ASSEMBLYAI_MAX_CONCURRENT_JOBS=<verified-account-limit>
```

The live test must upload a short fictional two-speaker file, request diarization, persist the complete
raw provider response as immutable bytes, reconcile word/utterance timing, preserve anonymous speaker
labels, and prove that provider completion does not auto-publish. AssemblyAI documents that
`speaker_labels=true` produces timed utterances and word data in its
[speaker-diarization guide](https://www.assemblyai.com/docs/pre-recorded-audio/label-speakers).

## 5. Recall Desktop SDK capture

Recall is gated by R1 because desktop/system-audio behavior varies by operating system, SDK version,
meeting client, device permissions, and provider artifact behavior. Do not add the live dependency or
ship the connector until the R1 evidence is reviewed.

1. Create an isolated Recall workspace in the approved region.
2. Generate a server API key and a webhook signing secret. These remain on the Verelo server.
3. Configure an HTTPS webhook for SDK upload completion/failure. The server creates an SDK upload and
   returns only its scoped desktop upload credential to the authorized Electron process.
4. Pin an exact Electron, Recall Desktop SDK, Windows/macOS, and meeting-client compatibility matrix.
5. Request audio-only recording; do not enable Recall transcription, bot recording, or video as a
   silent fallback.

Server configuration (reserved until R1 passes and the connector is implemented):

```text
RECALL_API_BASE_URL=<workspace-region-api-base>
RECALL_API_KEY=<server-secret>
RECALL_WEBHOOK_SECRET=<server-secret>
RECALL_WEBHOOK_URL=https://verelo.example/webhooks/recall
RECALL_CAPTURE_MODE=audio_only
```

Run the full R1 procedure in [integrations/recall.md](integrations/recall.md). It must demonstrate
local and remote speech from Zoom, Teams, and at least one browser meeting on each supported OS/client
combination; signed and replay-resistant callbacks; independent playable/hash-verified storage; a
visible interruption/gap state; restart recovery; duplicate-event idempotency; and provider cleanup
without deleting the independent original. Unsupported combinations must be stated in the product,
not silently treated as supported.

## 6. File and transcript format qualification

The contract checkpoint proposes these exact inputs:

| Type | Accepted inputs | Required validation |
|---|---|---|
| Audio | `.wav`, `.mp3`, `.m4a`, `.webm` | MIME sniff, container/codec decode, duration, channel/sample metadata, size/duration limits, malware/quarantine policy, SHA-256 |
| Transcript | `.txt`, `.vtt`, `.srt`, `.json` | strict parser, encoding, timestamps where present, schema/size limits, untrusted text handling |

Extension alone is never sufficient. A file must decode through the pinned server-side media stack.
To add AAC, FLAC, OGG, MP4, or another format later, add real and adversarial fixtures, document the
accepted codec/container combinations, and pass the same hash/duration/quarantine workflow before
adding it to the public contract.

The publication/export proposal provides:

- UTF-8 plain text canonical transcript;
- Markdown transcript with speaker/timestamp structure;
- JSON transcript containing canonical text, segments, provenance, source/version identifiers, and
  integrity hashes.

These are deterministic renderings of one immutable published version. Downloading a different
format must not create or mutate a transcript version.

## 7. Deployment activation order

1. Keep `VERELO_INTEGRATIONS_MODE=fake`; run migrations, unit/integration tests, restricted-role/RLS
   tests, the synthetic Electron capture flow, publication/reproduction tests, and backup/restore.
2. Obtain product-owner approval of the Phase 2 contract checkpoint. Generate contracts/migrations
   and implement the unified durable workflow only after approval.
3. Activate B2 in an isolated environment and pass storage/restore controls.
4. Activate AssemblyAI with fictional audio and pass raw-output/deletion/idempotency controls.
5. Run R1 and, only if it passes, implement and activate Recall Desktop capture.
6. Activate Entra with assigned test employees and all negative identity/session tests.
7. Run one end-to-end fictional meeting: capture or upload, independently store original, transcribe,
   reconcile, clean conservatively, approve, publish atomically, build passages, enqueue indexing, and
   download all three transcript formats.
8. Review logs, metrics, traces, audit records, dead-letter/retry controls, cost limits, retention,
   consent, incident response, and support runbooks. Only then authorize confidential material.

Each live test result uses [integrations/EVIDENCE_TEMPLATE.md](integrations/EVIDENCE_TEMPLATE.md).
Store raw evidence outside git and commit only sanitized status, versions, hashes, timings, negative
controls, and unresolved risks.

## Current implementation boundary

Today the repository provides a credential-free scaffold and synthetic adapters. Microsoft Graph mail
is the only implemented live network adapter described here. Entra, B2, AssemblyAI, and Recall remain
documented interfaces/gates until their contract or feasibility prerequisites are satisfied. Setting
the reserved environment variables does not make an unimplemented connector live; startup must fail
closed rather than substitute a fake provider in a production environment.
