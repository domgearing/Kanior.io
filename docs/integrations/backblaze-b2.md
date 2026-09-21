# Backblaze B2

Documentation verified: **2026-09-16**. Live smoke test: **NOT RUN**. Authority: architecture §§4, 9, 21, 35; shared behavior in [INTEGRATIONS.md](../INTEGRATIONS.md).

## API, operations and official references

Selected: private B2 through its S3-compatible API using Signature V4 and the provisioned regional endpoint. This compatibility surface is not an independently date-pinned REST version. Record endpoint, tested operations and pinned Python S3 client version at implementation; no SDK is selected here. The [S3 compatibility guide](https://www.backblaze.com/docs/en/cloud-storage-call-the-s3-compatible-api) and [operation inventory](https://www.backblaze.com/docs/en/cloud-storage-api-operations) are the source for supported behavior; do not assume every AWS feature works identically.

Required operations: PutObject, GetObject/HeadObject with pinned version, bounded authorized range reads, multipart upload/complete/abort for large files, list versions and version-specific deletion by the purge identity. Originals, raw transcripts, canonical versions and backups are independent governed objects. The operational database remains PostgreSQL.

## Authentication, permissions and environment

Use standard scoped application keys, not a master key. Map application key ID/key to S3 access-key ID/secret. [Application-key documentation](https://www.backblaze.com/docs/en/cloud-storage-application-keys) covers bucket/prefix restrictions and capabilities. Candidate runtime capabilities: `readFiles`, `writeFiles`, and only required listing capabilities on intended buckets/prefixes. Purge identity separately needs version listing/deletion; backup identity is separate and cannot be controlled by ordinary runtime deletion. Confirm exact capabilities with the selected client; do not grant account-wide listing just for an SDK convenience call.

| Name | Kind / setup |
|---|---|
| `B2_S3_ENDPOINT`, `B2_REGION` | Config; provisioned, allowlisted regional endpoint |
| `B2_BUCKET_NAME` | Config; private authoritative test bucket |
| `B2_APPLICATION_KEY_ID`, `B2_APPLICATION_KEY` | Credential ID / secret; restricted runtime key |
| `B2_PURGE_CREDENTIAL_REF` | Secret reference; separate controlled purge identity |
| `B2_BACKUP_BUCKET_NAME`, `B2_BACKUP_CREDENTIAL_REF` | Config / secret reference; independent backup administrative boundary |

## Provider-neutral adapter and synthetic response

```text
ObjectStorage.put_immutable(scope, stream, expected_sha256, operation_key) -> StoredObject
ObjectStorage.read_version(object_ref, optional_range) -> ByteStream
ObjectStorage.stat_version(object_ref) -> ObjectMetadata
ObjectStorage.purge_versions(object_ref, approved_deletion, operation_key) -> CleanupResult
```

```json
{"object_ref":"synthetic-object-version-1","byte_length":3,"sha256":"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","immutable":true}
```

Example bytes are `abc`; object_ref privately resolves bucket/key/version ID. The `immutable` flag describes an enforced application invariant, not proof of provider Object Lock. Provider ETags are not the application's SHA-256.

## Reliability, data and deletion

Apply shared transfer budgets, stream/hash rather than buffering a 2-GiB asset in memory, checkpoint multipart state and abort abandoned uploads. Persist operation identity and reconcile completed version/hash after a lost response; blindly repeating PutObject can create additional versions. Use unique immutable object keys and pin returned versions; published references never read an unqualified latest key. Application authorization precedes every read; version IDs are not credentials. Hash mismatch is `integrity_failure`; missing published bytes suppress quotes rather than regenerate source.

B2 receives all governed source/derived artifacts selected by the app; backup separation and encryption/region require IT approval. [DeleteObject semantics](https://www.backblaze.com/apidocs/s3-delete-object) distinguish a delete marker without `versionId` from deletion of a specified version. Purge must cover actual versions, markers, multipart remnants and backup policy, not merely hide the current key. Do not enable irreversible retention locks or lifecycle rules that can remove canonical evidence without approved retention/hold design. Restore must verify manifests/hashes and reapply tombstones/authorization before traffic or exports resume.

## Fake behavior and live smoke procedure

Fake: version-aware in-memory storage, exact bytes, range reads, multipart interruption, wrong hash, missing pinned version, duplicate operation, delete marker versus actual version purge, denied prefix and hold-blocked deletion. A simplistic overwrite-only mock is insufficient.

Live: provision a disposable private bucket and separate scoped keys; verify anonymous access and unrelated prefix/bucket access fail; store/re-read `abc` and a multipart-sized synthetic artifact with hashes/version IDs; retry known operations without changing pinned bytes; deny runtime deletion; purge test versions with authorized purge key and verify version listing. Copy to independent backup storage and demonstrate runtime cannot delete it; restore and verify hashes. Clean up only recorded test objects/grants. OPEN: exact client pin/capabilities, regional placement, encryption/key ownership, backup boundary, lifecycle/hold policy and large-file throughput. Local fake success does not prove B2 compatibility.
