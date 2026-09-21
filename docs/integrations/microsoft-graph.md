# Microsoft Graph / OneDrive

Documentation verified: **2026-09-16**. Live smoke test / **G1 gate: NOT RUN**. Authority: architecture §19; spec §11.1–11.2. Production connector implementation depends on G1; isolated feasibility code is permitted.

## API, operations and official references

Selected: Microsoft Graph **v1.0**, service-owned application identity, fixed company OneDrive for Business drive/folder. A SharePoint team library is an explicit IT decision, not an automatic substitution. No beta endpoints or employee delegated-token dependency. No SDK selected; pin any client library before implementation.

Operations: resolve configured drive/item metadata, create deterministic project/document/version folders, upload immutable Markdown/TXT/provenance JSON, read back/check bytes, inspect destination permissions, reconcile drift and remove governed exports. Use drive-item content/upload-session operations; [upload-session reference](https://learn.microsoft.com/en-us/graph/api/driveitem-createuploadsession?view=graph-rest-1.0) documents sequential fragments, 320-KiB alignment, expiration and recovery. Treat upload URLs as secrets; follow upload-host authorization rules, not blanket forwarding of Graph bearer headers.

## Authentication, permissions and environment

Use tenant-specific [client credentials](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow) with certificate or approved federated credential; token scope `https://graph.microsoft.com/.default`. Provisioning administrator and runtime exporter are different identities. The runtime app must not grant itself permissions.

[Selected permissions](https://learn.microsoft.com/en-us/graph/permissions-selected-overview) require consent, a resource-specific assignment and a matching token. **Candidate to test**, not an approved working grant: application `Files.SelectedOperations.Selected` plus write access on the intended folder. Test all required upload/read/delete/permission operations, not just discovery. A selected site/library alternative must be explicitly approved with its broader boundary. Do not silently add `Files.ReadWrite.All` or `Sites.FullControl.All` to make a failing test pass.

| Name | Kind / setup |
|---|---|
| `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID` | Config; isolated export application |
| `GRAPH_CLIENT_CREDENTIAL_REF` | Secret reference; certificate/private key or federation setup |
| `GRAPH_BASE_URL` | Config; approved cloud `.../v1.0` endpoint |
| `GRAPH_EXPORT_DRIVE_ID`, `GRAPH_EXPORT_FOLDER_ID` | Config; test bootstrap destination only; production per-project mappings live in `export_destinations` |
| `GRAPH_ACL_VERIFIER_CONFIG_REF` | Config/secret reference as applicable; approved effective-access inspection mechanism, separate identity if necessary |

**Effective-reader blocker:** [List permissions](https://learn.microsoft.com/en-us/graph/api/driveitem-list-permissions?view=graph-rest-1.0) documents caller-dependent visibility; a non-owner may see only applicable permissions. Its application-permission table also differs from the Selected overview. Therefore `/permissions` success or a short list does not prove complete effective readership. G1 must establish a supported verifier covering inheritance, groups/nested membership, sharing links, guests and owner access with its exact granted permissions. Unresolved/partial results return `permission_unverified` and block export. Additional verifier privileges require an explicit reviewed decision, not automatic exporter privilege expansion.

## Provider-neutral adapter and synthetic response

```text
ExportProvider.verify_destination(destination_ref, permitted_readers) -> AccessVerification
ExportProvider.export(version_ref, destination_ref, artifact_handles, operation_key) -> ExportResult
ExportProvider.reconcile(manifest_ref) -> DriftResult
ExportProvider.delete_export(manifest_ref, operation_key) -> CleanupResult
```

```json
{"export_manifest_id":"10000000-0000-4000-8000-000000000031","state":"verified","verified_formats":["markdown","text","provenance_json"],"permission_verification":"complete"}
```

Only return verified after every artifact's bytes/hash and destination access are checked. Store provider item IDs/ETags privately. Titles remain inside files; deterministic paths use UUIDs/version numbers. No private notes or default audio export.

## Reliability and data lifecycle

Apply shared metadata/transfer budgets. Honor 429 retry guidance, persist resumable progress/expiry, reconcile a lost completion response before re-uploading. Use `(version,destination,format)` operation identity; existing different bytes/ETag are drift, not permission to overwrite. Conditional conflicts return blocked/drift state. Never turn retries into unlimited renamed duplicates. A fresh session may be needed after expiry, but first reconcile destination state. Failed Graph calls must not hide canonical app transcripts.

Graph receives approved export bytes and provenance. Destinations must have readers no broader than source readers; MVP mappings match project membership. Membership changes pause exports until reverified; daily reconciliation is the MVP minimum, plus change-triggered checks. External edits are not imported. Retention/recycle bins, holds, backup copies and downloaded/offline copies complicate deletion; record per-system completion and never promise instant recall. OPEN: destination ownership/lifecycle, effective-reader verifier, exact grants, external-sharing policy, managed-device policy, retention and allowed export identity.

## Fake behavior and G1 live smoke procedure

Fake: resumable partial upload, 429, session expiry, late duplicate completion, ETag conflict, partial ACL visibility, nested-group expansion failure, broad sharing link, revoked grant and external deletion.

Live G1 (Microsoft 365 administrator + engineer, disposable synthetic resources):

1. Choose and record OneDrive-for-Business versus explicitly approved team-library destination, account ownership/license continuity, cloud and drive/folder references in restricted evidence.
2. Consent only the candidate Selected permission; before resource assignment prove denial. Grant the selected test folder using the separate admin identity. Record exact role/scope; prove sibling/other-drive access still fails.
3. With exporter identity, create folders and upload/read/hash all three small versioned artifacts; test a resumable fixture too. Record which exact operations each grant supports, including permission inspection and cleanup. Upload success alone is not PASS.
4. Establish complete effective-reader verification, including inherited access, groups, guests, organization/anonymous links and owner. Seed an unauthorized reader/link and prove export blocks. If the verifier cannot see it, G1 fails.
5. Remove a project member and show subsequent export is paused until destination reconciliation; revoke the app's resource grant and prove denial. Re-run known operation without duplicates; inject a conflicting external edit and prove no overwrite.
6. Delete only recorded synthetic exports, inspect recycle/retention behavior and remove test grants. Record residual retained copies and deadlines.

PASS requires both working least-privilege operations and trustworthy source-to-destination access comparison, with negative controls. Record outcomes using the evidence template. An API limitation must produce a scoped design decision; it is not authorization to broaden tenant access.
