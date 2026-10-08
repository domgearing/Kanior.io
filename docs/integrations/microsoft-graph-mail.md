# Microsoft Graph Mail for magic-link delivery

Documentation verified: **2026-09-25**. Live smoke test: **NOT RUN**. This adapter is separate from
the Graph/OneDrive export identity and permissions. It changes only delivery of an already-authorized
Verelo sign-in token; it does not provision employees or grant project access.

## Selected protocol and security boundary

The server obtains an application token from the tenant-specific OAuth 2.0 token endpoint with the
client-credentials grant and scope `https://graph.microsoft.com/.default`. It then calls Microsoft
Graph `v1.0` `POST /users/{sender}/sendMail`. Microsoft documents `Mail.Send` as the least-privileged
application permission for this operation and returns `202 Accepted`; acceptance does not prove final
mail delivery.

Use a dedicated Exchange Online mailbox such as `verelo-login@company.example` and a dedicated app
registration. Do not reuse the OneDrive export app. Graph's tenant-wide `Mail.Send` application
permission can send as any mailbox unless Exchange Online constrains it. Use Exchange Online
Application RBAC to assign the `Application Mail.Send` role only over the dedicated sender mailbox,
and test both the allowed sender and a forbidden mailbox before enabling the adapter.

Official references:

- [Microsoft Graph `sendMail`](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0)
- [Client-credentials flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow)
- [Exchange Online Application RBAC](https://learn.microsoft.com/en-us/exchange/permissions-exo/application-rbac)

## Microsoft 365 administrator setup

1. Create or select a dedicated licensed/shared sender mailbox with the lifecycle and monitoring your
   organization requires.
2. Create a single-tenant app registration dedicated to Verelo sign-in mail.
3. Add Microsoft Graph **application** permission `Mail.Send` and grant administrator consent.
4. Configure Exchange Online Application RBAC so this service principal can send only from the
   dedicated mailbox. Do not accept unrestricted mailbox access as the finished configuration.
5. Create a short-lived client secret for the initial isolated smoke test. For longer-lived deployed
   operation, replace it with an approved certificate or workload-federated credential before
   confidential use; the current adapter implements client-secret authentication only.
6. Store tenant ID, client ID and the secret in an approved secret store. Inject them into the server
   process; never place real values in `.env.example`, source control, frontend or Electron bundles.

## Verelo configuration

Use an isolated local/test deployment and HTTPS callback origin. Set these only in the ignored local
`.env` or your deployment secret injection:

```text
VERELO_ENVIRONMENT=test
VERELO_INTEGRATIONS_MODE=live
VERELO_IDENTITY_PROVIDER=magic_link
VERELO_MAGIC_LINK_DELIVERY=microsoft_graph
VERELO_MAGIC_LINK_BASE_URL=https://your-verelo-test-host.example/auth/verify
VERELO_PUBLIC_ORIGIN=https://your-verelo-test-host.example
VERELO_SESSION_COOKIE_SECURE=true
VERELO_GRAPH_MAIL_TENANT_ID=<tenant-guid>
VERELO_GRAPH_MAIL_CLIENT_ID=<application-client-guid>
VERELO_GRAPH_MAIL_CLIENT_SECRET=<secret-from-secret-store>
VERELO_GRAPH_MAIL_SENDER=verelo-login@company.example
```

The base Graph and authority URLs default to Microsoft's global cloud endpoints. Change
`VERELO_GRAPH_MAIL_BASE_URL` and `VERELO_GRAPH_MAIL_AUTHORITY_URL` only for an explicitly approved
national-cloud deployment.

## Synthetic and live verification

Normal CI uses an injected HTTP transport and fictional addresses. Before enabling real delivery,
run a bounded test with an already-provisioned fictional/test employee:

1. Confirm an unknown email receives Verelo's neutral response and no message.
2. Confirm an approved employee receives one link, and that the link works once and expires in ten
   minutes.
3. Confirm Graph can send from the configured dedicated mailbox.
4. Attempt to send from a second mailbox by temporarily changing only the sender setting; Graph must
   deny it. Restore the dedicated sender immediately.
5. Revoke the Exchange role assignment and confirm delivery fails neutrally, then restore it.
6. Inspect application/API logs and confirm tokens, links, recipient addresses, client secrets and
   Graph response bodies are absent.
7. Disable the internal employee and confirm no message is sent and existing Verelo sessions stop.

Record the app registration ID, sender mailbox, exact permission/role assignment, test date and safe
pass/fail evidence outside source control. Do not record the secret or magic-link URL.

## Current limitation

ADR-005 and the security contract permit magic-link identity only in local/test environments.
Consequently, this connector intentionally does not make production email authentication valid.
Moving production from Entra SSO to Graph-delivered magic links requires an explicit security and
architecture decision, MFA/passkey design, updated acceptance tests and product-owner approval.
