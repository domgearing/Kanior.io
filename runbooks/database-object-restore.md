# Database and object restore

Scope: PostgreSQL operational state plus authoritative source/version objects. OneDrive is not a
backup. This runbook does not set company RPO/RTO, region, retention, or reopening authority.

## Required permissions and owners

- Incident owner: operations lead approved by the data owner.
- Database restore identity: isolated recovery environment only; no application traffic.
- Object restore identity: read access to the independent backup and write access only to the
  isolated recovery prefix/bucket.
- Security/data owner: approves verification and explicitly authorizes reopening.

## Procedure

1. Declare the incident, freeze outbound exports/provider submissions, and record the target
   recovery point. Keep the recovery environment unreachable by normal API, worker, and user
   identities.
2. Restore the PostgreSQL backup and authoritative objects from compatible recovery points. Retain
   immutable object versions and their original references.
3. Reapply the deletion ledger, tombstones, holds, disabled identities, current memberships, and
   document restrictions before enabling any reader.
4. Verify every restored object against the backup manifest and database SHA-256/byte-length
   metadata. Quarantine any mismatch and raise a source-integrity incident.
5. Rebuild derived lexical/vector indexes. Do not replace canonical objects from an index or export.
6. Reconcile leased/queued jobs, outbox events, and provider operations. Unknown external outcomes
   require provider reconciliation or operator review, never blind resubmission.
7. Run migration, RLS/cross-tenant, canonical reproduction, and exact quote-integrity smoke tests.
8. Keep exports and provider side effects disabled until all checks pass. Record the achieved
   recovery point/time, exceptions, artifact manifest hash, and approvers.
9. The security/data owner explicitly authorizes reopening. Restore credentials are revoked or
   returned to the recovery boundary after the exercise.

## Local synthetic exercise

From Git Bash with Docker Desktop running:

```bash
./scripts/backup-restore-smoke.sh
```

The script creates a disposable PostgreSQL container and temporary object tree, migrates and seeds
fictional data, backs up both stores, restores to a separate database/object directory, verifies the
database marker and all object hashes, and removes the isolated resources. Passing this exercise
proves only the local mechanism; it does not approve production recovery policy or confidential use.

## Escalation

Any manifest mismatch, missing tombstone/hold, unauthorized restored read, uncertain provider side
effect, incompatible recovery points, or failed quote-integrity check blocks reopening and is
escalated as a source-integrity/security incident.
