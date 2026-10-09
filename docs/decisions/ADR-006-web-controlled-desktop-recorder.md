# ADR-006: Authenticated web control of the desktop recorder

Status: accepted for the local/test implementation; confidential rollout remains gated by architecture §38.

## Context

The Recall Desktop SDK must run on the recording computer, but an employee wants to choose a meeting and operate Start/Pause/Resume/Stop from the web app. A browser cannot invoke the SDK on another machine. An unauthenticated localhost bridge or a browser-held Recall credential would create an unacceptable control boundary.

## Decision

Use PostgreSQL-backed, short-lived recorder commands through the existing authenticated API. The desktop app registers a random device ID and heartbeats while signed in with Recall capture enabled. A web session for the *same internal employee* can list that employee's devices and submit one pending command per device. Start names an authorized, active document and requires current contributor/owner membership. Pause and resume require current write access to the active document; a Stop request remains available to the device owner after revocation so Recall can end local capture, although the server-side transition may then fail and require operator reconciliation. Every mutation requires the existing Origin/CSRF checks. Commands have client operation keys, a short expiry, a single claim, terminal result, and safe error codes. The desktop app alone invokes Recall and reports the result; the web app polls safe device/command state. The recorder must remain visible and running locally.

This is a control channel, not a replacement for Electron capture, a general remote-execution facility, or a promise that a browser can launch an uninstalled app. A separate, per-user Windows `verelo-recorder://open` handler can open or focus the locally built app. It accepts only that fixed link, not a document ID, command, or arbitrary argument. The API accepts only the four enumerated actions and UUID references; it never accepts scripts, URLs, provider tokens, audio or transcript bytes. Device status is advisory; a completed result must match an employee-owned capture session in the expected persisted state. Expired or uncertain commands require inspection of the reported recorder state before retrying Start.

## Alternatives considered

- A localhost HTTP bridge was rejected because an Internet page would address a privileged local service and need a second origin/authorization design.
- Direct browser Recall capture was rejected because the existing SDK and tested system-audio path run in Electron.
- An in-memory queue was rejected because API restarts would lose pending commands and status.

## Consequences

The desktop app must be open and authenticated. Multiple devices are explicit in the web UI; commands never silently target whichever computer responds first. Short polling adds modest API/database load. Offline and failed states are visible, and local desktop controls continue to work.

## Security implications

Database rows are tenant/workspace/user scoped with forced RLS. A 256-bit device token stored in Electron user data is hashed at rest and required for heartbeat, claim, and result; the browser never receives it. The service rechecks membership before command issuance and uses the same-user device binding. A guessed device, command, or document ID does not disclose another employee's state. Command and completion audits contain IDs and safe states only. A compromised session can request actions for that same employee's recorder, so the visible desktop state, short-lived commands, secure sessions, MFA in staging/production, and immediate employee disable remain required.

## Migration implications

An expand-only Alembic migration adds device and command tables. Existing desktop versions simply do not heartbeat and appear offline. No existing capture or ingestion rows are rewritten. Staging deployment still requires Entra, independent resources, backups, and the manual policy gates.
