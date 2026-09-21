# Microsoft Entra

Documentation verified: **2026-09-16**. Live smoke test: **NOT RUN**. Authority: architecture §§20–21; shared behavior in [INTEGRATIONS.md](../INTEGRATIONS.md).

## API, operations and official references

Selected: OIDC/OAuth 2.0, tenant-specific `/oauth2/v2.0/authorize` and `/token`, OIDC discovery/signing keys, authorization-code flow with PKCE. A maintained Python identity library must be chosen/pinned during identity implementation; no SDK version is installed or approved here. Do not implement JWT verification by hand. The [official authorization-code guide](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow) documents protocol parameters, redirect URIs and PKCE; [protocol overview](https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols) supplies discovery context.

App operations: begin login, validate callback/state/nonce, exchange code, validate issuer/audience/signature/expiry/tenant, resolve assigned enabled employee, establish server session and terminate it. The Graph export identity is separate; signing in does not grant file access.

## Authentication, permissions and environment

Register a single-tenant confidential web application, exact callback URIs, assigned employee app role/group and restricted credentials. Select OIDC `openid profile` for login; request `email` only for display if needed. Do not add Graph directory/file scopes merely to sign in. `offline_access` is not a baseline requirement; adding refresh-token use needs explicit lifecycle/storage design. PKCE does not replace confidential-client authentication. Employee status/assignment must be proven from trusted claims/provisioning, not inferred from email or tenant membership. Missing/overage group evidence fails closed until resolved.

| Name | Kind / setup |
|---|---|
| `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID` | Config; provisioned test tenant/application IDs |
| `ENTRA_REDIRECT_URI` | Config; exact registered API callback |
| `ENTRA_CLIENT_CREDENTIAL_REF` | Secret reference; server certificate/private key or approved client secret, never desktop-side |
| `ENTRA_REQUIRED_EMPLOYEE_ROLE`, `ENTRA_EMPLOYEE_GROUP_ID` | Config; select documented assignment/provisioning mechanism; do not treat either as sufficient without enabled internal user |
| `SESSION_SECRET_REF` | Secret reference for application session protection, distinct from provider credential |

IT must choose how assignment/employee-disable changes reach the internal user record within the spec's target. If a directory connector is needed, separately document its permissions and approval; this guide does not authorize tenant-wide directory reads.

## Provider-neutral adapter and synthetic response

```text
IdentityProvider.begin_login(callback, state_handle) -> RedirectHandle
IdentityProvider.complete_login(code_handle, state_handle) -> VerifiedExternalIdentity
```

```json
{"tenant_external_id":"10000000-0000-4000-8000-000000000001","subject_external_id":"10000000-0000-4000-8000-000000000002","employee_assignment_verified":true,"display_name":"Synthetic Employee"}
```

This intermediate result is not AuthContext. IdentityService maps provisioned internal IDs and checks enabled/assignment state before issuing the existing session. Tokens and authorization codes remain secret connector/session state.

## Reliability and data lifecycle

Use shared 5/30-second network defaults. Login interaction duration is separate from HTTP timeouts. Cache discovery/JWKS respecting cache headers; on unknown signing key refresh once, then reject. Never replay a consumed code indefinitely: uncertain exchange restarts interactive login. State/nonce are single-use, expiry-bound and session-bound. Invalid identity maps to safe `unauthenticated`; provider outage maps to `dependency_unavailable`. Do not log callback query strings.

External data: account identifiers, authentication metadata and redirect/session protocol data; no transcript/audio. Revoke local sessions on disable and enforce 30-minute idle/eight-hour absolute defaults. Provider sign-in/audit retention and enterprise assignment policies belong to IT; local logout is not a claim of deletion from Entra.

## Fake behavior and live smoke procedure

Fake identity is an in-process test dependency only. Cover assigned employee, guest, unassigned, disabled, wrong tenant/audience, expired token, nonce replay and key rotation; still exercise real authorization/RLS.

Live: (1) IT provisions an isolated app and assigned/unassigned/guest accounts; (2) perform browser login with PKCE, inspect safe claim outcomes, verify callback/session/CSRF; (3) prove other-tenant/unassigned/guest denial; (4) disable the internal employee and prove subsequent requests fail; (5) measure directory-change propagation separately; (6) remove test credentials/sessions. Record exact library version, callback setup, assignment mechanism and results. OPEN: actual tenant, credential method, provisioning mechanism, MFA policy and session store implementation.
