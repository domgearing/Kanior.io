# Integration reference

Authority: `ARCHITECTURE.md` §§4, 7, 17, 19–22, 38–39 and `PROJECT_SPEC.md` §§4, 6, 11–14. Internal contracts remain in [API_CONTRACTS.md](API_CONTRACTS.md), [DATA_MODEL.md](DATA_MODEL.md), and [SECURITY.md](SECURITY.md).

Documentation verified: **2026-09-16**. Verification means the cited official pages were read; it does not establish tenant access, account settings, installed SDK compatibility or a successful live integration. **No live provider tests have been run for this reference.** No connector, fake implementation, credentials or deployed configuration is added by these documents.

## Provider index and readiness

| Guide | Selected protocol / model | Open prerequisite |
|---|---|---|
| [Microsoft Entra](integrations/microsoft-entra.md) | OIDC/OAuth 2.0, tenant-specific v2.0 endpoints | Test tenant, assigned employees, lifecycle provisioning, client library pin |
| [Recall](integrations/recall.md) | Desktop SDK + REST `/api/v1`; audio-only capture | **R1 audio handoff feasibility gate**, exact SDK/Electron/OS pins |
| [AssemblyAI](integrations/assemblyai.md) | REST `/v2`, `universal-3-5-pro` | Regional account/model access, training opt-out and retention evidence |
| [OpenAI](integrations/openai.md) | REST `/v1/responses` and `/v1/embeddings` | Approved model identifiers, dimensions, account data controls |
| [Graph / OneDrive](integrations/microsoft-graph.md) | Microsoft Graph `v1.0`, application identity | **G1 destination/permissions feasibility gate**, effective-reader proof |
| [Backblaze B2](integrations/backblaze-b2.md) | S3-compatible API, Signature V4 | Region/buckets, scoped keys, version-specific storage tests |

Provider APIs that lack immutable revisions are identified by their documented protocol path, checked date and captured synthetic response fixtures. Library versions are not fabricated: where no library is installed, its exact version is OPEN and must be pinned in the implementation lockfile before connector code merges. Never use floating `latest` SDK/model choices. An HTTP API selection does not select an HTTP library version.

## First feasibility work

Run the bounded synthetic R1 and G1 procedures in the linked guides **before implementing their production connectors**. Independent foundation and fake-adapter work can proceed. Record results using [EVIDENCE_TEMPLATE.md](integrations/EVIDENCE_TEMPLATE.md); a documentation review or mocked test cannot change a gate to PASS.

| Gate | Owner | Required evidence | Current status |
|---|---|---|---|
| R1 | Capture engineer + IT/device owner | SDK/OS/client matrix; signed completion event; playable audio copied to private storage with byte hash/duration; no Recall transcription; interruption and cleanup behavior | NOT RUN |
| G1 | Microsoft 365 administrator + export engineer | Destination type/ownership; exact consent and resource grants; allowed and forbidden uploads; complete reader verification; revocation, drift and deletion results | NOT RUN |

If either experiment fails, document the failing operation and continue independent work. Do not silently use meeting bots, add Recall transcription, grant tenant-wide file access, or substitute a SharePoint library for the requested OneDrive destination. Material alternatives follow the architecture's ADR process.

## Shared adapter contract

Interfaces in provider guides are conceptual provider-neutral proposals for their implementation phase, not new public HTTP endpoints or finalized generated DTOs. Use internal UUIDs and trusted scope; opaque provider references stay within connector persistence. Signed URLs, tokens and raw provider objects never enter domain responses. Finalize typed DTOs using the existing Python-owned generation workflow when implementing an adapter.

Every side-effect call takes a durable application `operation_key`, bound to tenant/project/resource/action and payload hash. This is **not** a claim that the provider accepts an idempotency header. Persist submission intent and provider reference; reconcile uncertain outcomes before issuing another paid/upload/create operation. Where reconciliation is unavailable, mark `outcome_unknown` for bounded operator recovery, not automatic blind resubmission. Reauthorize jobs before side effects and reject stale/tombstoned resources.

Shared safe failure shape: `{code, retryable, outcome_known, retry_after_seconds}`. No provider message/body is returned. Codes:

| Condition | Internal code / handling |
|---|---|
| Credentials rejected / grant missing | `provider_auth` / `provider_permission`; configuration repair, no retry loop |
| Invalid input / unsupported format or model | `provider_invalid_input` / `provider_unsupported`; terminal until corrected |
| Throttling / temporary overload | `provider_throttled` / `provider_unavailable`; bounded scheduled retry |
| Timeout after possible write | `provider_outcome_unknown`; reconcile before retry |
| Missing artifact / expired transfer | `provider_not_found` / `provider_expired`; inspect operation state; do not assume deletion |
| Schema violation / wrong hash | `provider_invalid_response` / `integrity_failure`; suppress output and investigate |
| Destination access cannot be proven | `permission_unverified`; block export, even if upload technically works |

Map these to the existing safe public Error contract or background job status. Provider 401/403 means connector configuration failure, not necessarily that the employee should be logged out. Never disguise an outage as no evidence.

## Timeouts, retries and configuration conventions

The following are **initial application defaults**, not provider SLAs or published quotas. Override through reviewed deployment configuration after measurements:

- Connect timeout 5 seconds; metadata/token/poll request deadline 30 seconds.
- Transfer inactivity timeout 120 seconds; transfer wall-clock deadline 30 minutes, separately configurable from transcription/capture duration. Long workflows checkpoint in durable jobs; do not hold a worker lease without renewal.
- For safe retryable requests: at most three HTTP attempts, exponential jitter starting at 1 second and capped at 30 seconds; honor valid `Retry-After` even when longer by rescheduling the job. SDK retries must count within this budget, not multiply it. After exhaustion, durable workflow policy decides the next attempt/dead-letter state.
- AI interactive calls share a 12-second total provider budget, including retries; slow output falls back according to architecture §16. Cleanup is an asynchronous job and may use a separately configured budget. These budgets require load verification against the spec's latency targets.
- Bound concurrency per account/project; discover account quotas in the smoke test. Rate-limit/retry tests normally use injected faults, not deliberate provider overload.

Common proposed configuration names: `INTEGRATIONS_MODE` (`fake` in tests, `live` only with explicit environment setup), `INTEGRATION_CONNECT_TIMEOUT_SECONDS`, `INTEGRATION_REQUEST_TIMEOUT_SECONDS`, `INTEGRATION_TRANSFER_IDLE_TIMEOUT_SECONDS`, `INTEGRATION_TRANSFER_DEADLINE_SECONDS`, `INTEGRATION_MAX_HTTP_ATTEMPTS`. These names are reserved documentation, not an implemented settings loader. Production startup must reject fake providers when confidential/live operation is enabled.

Provider tables mark **secret** values or **secret references**. Store actual values in a server-side secret store/injected environment, never Markdown, examples, fixtures, git, desktop bundles or standard logs. IDs are configuration, not credentials, but real customer/tenant identifiers do not belong in synthetic fixtures. Do not put credentials in shell command arguments or smoke-test reports.

## Fake and live test separation

Normal CI uses deterministic fictional adapter fixtures, fake clock, bounded fake retries and no network credentials. Fakes preserve asynchronous states, uncertain outcomes and security failures; they must not simply return success. Test-only identity injection follows SECURITY.md and is never a public login route.

Live smoke tests are opt-in, use isolated accounts/resources and a consenting scripted synthetic call or fictional text, have a spend/resource limit, and clean up only their recorded test resources. Store restricted raw evidence outside git; commit a sanitized result summary with version pins, safe response fields, hashes, timings, negative controls and unresolved items. A provider DELETE success is not proof of backup/training-copy erasure. Resolve processor, residency, retention, consent, budget and recovery approvals before confidential traffic.
