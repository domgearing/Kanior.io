# ADR-007: Local mailbox one-time password sign-in

## Decision

For the local/test identity adapter with local mailbox delivery, present the existing random,
single-use challenge as a password in the ignored development mailbox. The web login asks for the
allowlisted email and that one-time password. The challenge hash includes the normalized email,
so a password cannot be submitted with a different email. It retains the existing ten-minute
expiry, issuance rate limits, atomic consumption, enabled-employee check, and opaque server session.
The local password request and consume routes are unavailable for Entra and Graph delivery.

This is a usability change to development authentication, not a reusable account password. The
password is never persisted in plaintext in PostgreSQL or exposed by an API response. The local
mailbox is a credential store and must remain ignored by Git, restricted to the developer's
computer, and excluded from shared logs and screenshots. The older magic-link endpoints remain
for Graph delivery and compatibility but are not used by the local web login.

## Consequences

- A developer requests a fresh password for each sign-in and copies it from
  `.artifacts/dev-mailbox/latest.json`; requesting another password replaces the mailbox display
  but does not revoke an unconsumed older challenge before its expiry.
- A production-style long-lived password store, password reset flow, or team sign-in is not added.
  Confidential staging/production still requires the Entra controls in ADR-005.
