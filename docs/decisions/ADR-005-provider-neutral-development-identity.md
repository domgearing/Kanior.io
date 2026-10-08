# ADR-005: Provider-neutral identity with development magic links

## Status

Accepted by the product owner on 21 September 2026.

## Context

The architecture originally required Microsoft Entra for every interactive environment. The product
owner wants a credential-free development application without connecting or risking the company
Microsoft tenant. Public signup, domain-only admission, and treating an email address as a durable
authorization identity remain prohibited.

## Decision

Interactive identity is exposed through a provider-neutral `IdentityProvider` boundary. Local and
test environments use a passwordless magic-link adapter. An administrator must first provision an
enabled internal employee and a `magic_link` identity account. The login email is only a mutable
locator; the immutable internal user UUID remains the authorization principal.

Magic-link requests always return the same response. Eligible requests receive a cryptographically
random, single-use credential that is stored only as a SHA-256 digest, expires after ten minutes, and
is consumed atomically with creation of the existing opaque server session. Request rates are bounded
by hashed email and source identifiers. The synthetic delivery adapter writes only to an ignored local
mailbox. It is unavailable outside local/test configuration.

Production identity remains single-tenant Entra authorization-code flow with PKCE. A future Entra
adapter implements the same identity boundary and maps `(tenant ID, object ID)` to the same internal
user UUID. Project authorization, RLS, sessions, CSRF, and resource records do not change during that
migration.

## Alternatives considered

- Connect the company Entra tenant immediately: rejected for the development phase at the product
  owner's request.
- Public email signup or corporate-domain admission: rejected because mailbox/domain possession does
  not establish an approved current employee.
- Put email directly on sessions or use it as the user primary key: rejected because email is mutable
  and reusable.

## Consequences

- Local development requires explicit provisioning and no external email provider.
- Email authentication is weaker than Entra MFA and is not approved for confidential or production
  traffic.
- A transactional mail adapter may replace the local mailbox for an approved non-production setting;
  this does not authorize any provider by itself.
- Entra migration is isolated to the identity adapter and identity-account provisioning.

## Security implications

No token, email address, cookie, or CSRF value enters ordinary logs. Exact Origin checks, HttpOnly
SameSite cookies, CSRF validation, session expiry, immediate internal-user disable, neutral responses,
and rate limiting remain mandatory. Local magic links must never be enabled in staging or production.

## Migration implications

`identity_accounts` separates external identities from internal users. Existing Entra object IDs are
backfilled as `entra` identities. Existing tenant/object columns remain temporarily for compatibility
but become nullable. Entra cutover adds an adapter and provisioning/synchronization; it does not
rewrite users, memberships, projects, or content ownership.
