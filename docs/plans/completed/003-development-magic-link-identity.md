# Development magic-link identity

## Phase and objective

Architecture Phases 0–1. Implement ADR-005's explicit-allowlist development login without changing
the internal principal, opaque session, authorization, RLS, project, or transcript contracts.

## Scope

- Provider-neutral interactive identity interface.
- Local/test-only magic-link provider and ignored synthetic mailbox adapter.
- Administrator provisioning command; no public signup.
- Hashed single-use ten-minute challenges, neutral responses, rate limits, exact Origin checks.
- Atomic challenge consumption and session creation; CSRF-protected logout and immediate disable.
- Database migration, HTTP contracts, web login screen, documentation, and adversarial tests.

## Completion evidence

Implementation is migration `0006_magic_link_identity`. Integration tests cover unknown-account
neutrality, wrong Origin, case-normalized allowlist matching, session issuance, replay rejection,
logout, and immediate internal-user disable. Production remains blocked on an approved Entra setup;
the development adapter cannot start outside local/test configuration.
