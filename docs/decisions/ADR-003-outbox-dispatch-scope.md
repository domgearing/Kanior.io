# ADR-003: Scoped outbox dispatch without RLS bypass

Status: accepted implementation direction; dispatcher and service-grant enforcement are not implemented by this ADR.

## Context

Architecture sections 9.1, 21 and 22 require restricted runtime database roles,
worker resource revalidation and a PostgreSQL transactional outbox. Section 9.1
expressly prohibits runtime table ownership, superuser and `BYPASSRLS` privileges.
The foundation migration scopes `outbox_events` to tenant and workspace. An
unscoped cross-tenant dispatcher therefore cannot read its queue, by design.

The current migration supplies a scope boundary, not the complete worker action
authorization policy. `workers/__main__.py` currently starts and exits; it does
not dispatch events. Neither existing code nor this decision proves the Phase 1
jobs or isolation acceptance gates have passed.

## Decision

Use per-tenant/workspace iteration under a provisioned service identity, with a
project scope for each dispatch transaction. Keep `kanior_worker` restricted by
RLS. Do not add a bypass role, a global content grant, a migration-role connection
or an unrestricted security-definer queue reader.

The initial worker receives its assigned tenant/workspace/project tuples and
registered actions through trusted, operator-provisioned configuration. This is
the same out-of-band provisioning boundary used by the first foundation slice;
it is not a new public API. It contains identifiers and grants, never content.
It must not discover scope by scanning all content, nor trust scope from an
unvalidated event or client request. An empty assignment means no work. A scope
assignment permits attempting an action, not accessing every resource in that
scope: current service grants must still be checked for each transaction.

Before dispatcher implementation, finalize the persisted service-grant contract
and its restricted lookup in the foundation plan. Policies must verify the
current enabled service identity, assigned scope and registered action; setting
a UUID in a session variable is not sufficient authorization. Revoked grants
deny new claims. Configuration refresh failures must not invent additional
assignments, and stale configuration must not override a revoked persisted grant.

## Runtime transaction contract

1. Check out a worker connection with no ambient transaction or session-level
   application context. Begin a fresh transaction for one assigned project.
2. Validate the assignment and bind transaction-local context using
   `set_config(name, value, true)` with parameterized values:
   `app.principal_kind = service`, the provisioned service UUID in
   `app.principal_id`, and the assigned UUIDs in `app.tenant_id`,
   `app.workspace_id` and `app.project_id`. Use fixed setting names. Reject
   missing, malformed or unassigned context before reading queue records.
3. Revalidate the current service grant through the approved restricted lookup.
   RLS `USING` and `WITH CHECK` must enforce the applicable scope and action.
   Select only registered event types for that scope in bounded batches, using
   `FOR UPDATE SKIP LOCKED` and deterministic `(created_at, id)` ordering.
4. Validate the immutable event envelope and its parent references. Insert the
   corresponding durable job(s), then set `dispatched_at` in the **same database
   transaction**. A database unique operation key must deduplicate the event
   and consumer action within its scope. A conflict is success only when the
   existing job matches the intended operation. An unknown schema/type or
   invalid envelope is not marked dispatched; report a safe operator-visible
   failure without logging payloads.
5. Commit only after every required durable job exists. Rollback releases the
   locks and leaves the event pending after an error or crash. `dispatched_at`
   means durable handoff to jobs, not successful external execution. No provider
   request occurs while this dispatch transaction is open.
6. End the transaction before returning the connection or changing scope.
   Roll back on every exception. Never use session-level `SET` or change tenant
   inside a transaction. Discard connections whose rollback/reset fails. Pool
   checkout/reset must reject or clear ambient session context; transaction-local
   settings alone cannot repair a previously contaminated connection.

PostgreSQL documents transaction-local `set_config` and the queue-oriented use
of `SKIP LOCKED`; those mechanisms do not replace authorization or idempotency.
See [configuration functions](https://www.postgresql.org/docs/17/functions-admin.html)
and [row locking](https://www.postgresql.org/docs/17/sql-select.html).

The job executor separately uses durable leases, heartbeats, bounded retries and
provider reconciliation from architecture section 22. It revalidates service
grants, current resource state and any required originating employee permission
at claim and before side effects. Event origin does not confer continuing
authority. Security invalidation and deletion/reconciliation actions must retain
their explicitly provisioned service authority when an employee is disabled or
a source is tombstoned; they must not be mistaken for permission to read or
export that source. Ordinary stale content work must fail closed.

Grant only the queue/job columns and registered operations that dispatch needs.
Keep the event envelope immutable; limit outbox updates to dispatch bookkeeping.
Dispatch authority itself grants no transcript, audio or evidence read. Scoped
action executors obtain only their separately authorized access. Any helper
needed for grant lookup must follow `docs/SECURITY.md` fixed-search-path,
restricted-EXECUTE and dedicated-test requirements.

## Alternatives considered

- **Runtime `BYPASSRLS` or owner connection:** conflicts with the architecture and
  broadens compromise impact to unrelated tenants and content.
- **Privileged global queue function:** could expose a narrow metadata surface,
  but adds a privileged boundary and scope-discovery contract before there is a
  measured need. It is not part of the initial implementation.
- **Unscoped worker with caller-supplied filters:** relies on every query getting
  isolation right and does not satisfy database defense in depth.

PostgreSQL distinguishes runtime roles subject to policies from roles that
bypass them in its [row-security documentation](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).

## Consequences and scale

Poll assigned scopes fairly with bounded batches and idle backoff; one busy or
failed project must not starve others. Scope provisioning is an operational
dependency: adding a project must assign the relevant worker before claiming
background work is available. Monitor undispatched age and failed assignments
using identifiers, counts and safe errors only.

Workers can later partition the provisioned assignment list and use the same
locking and operation keys. Ordering is per aggregate, not global: consumers
must compare the relevant version/revision and reject stale effects. Queue
selection order does not establish execution order. Measure polling latency and
database load before introducing a registry service, broker or privileged
discovery function. Any future discovery mechanism needs its own reviewed
security contract and must preserve scoped execution.

## Required implementation tests

- Real PostgreSQL connections as restricted runtime roles prove no ownership,
  superuser, `BYPASSRLS` or inherited migrator powers; ENABLE/FORCE RLS remains
  active on the queue and scoped job tables.
- Two tenants, multiple workspaces and projects prove that missing, malformed,
  foreign and forged-unassigned context cannot read, claim, update or enqueue
  another scope's work. A disabled service or revoked action grant fails closed.
- Reuse the same pooled connection across tenants after success, rollback,
  exception and cancellation; no scope leaks. Test contaminated session context
  and failed connection reset explicitly.
- Multiple dispatchers and crashes before/after each durable handoff step leave
  no lost event or duplicate logical job. Failure to insert a job rolls back
  `dispatched_at`; duplicate operation keys must preserve matching immutable
  intent. Unsupported events remain observable and undispatched without blocking
  unrelated registered events.
- Revocation/tombstone races prevent stale content side effects while authorized
  access invalidation and reconciliation continue. Restart and out-of-order
  delivery cannot resurrect revoked access or deleted content.
- Runtime grants cannot mutate the event envelope or read confidential source
  tables merely by holding dispatch authority. Logs contain no content/secrets.

## Migration and rollout implications

This ADR changes no database schema and grants no new privileges. The foundation
jobs task must add the service-grant enforcement, scoped jobs schema, operation
uniqueness, restricted column grants and tests before enabling dispatch. The
existing tenant/workspace outbox policy is insufficient by itself for that
rollout. Keep the worker inactive until those gates pass. No confidential pilot
traffic is authorized by this decision.
