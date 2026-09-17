# ADR-002: Python-owned contract generation

Status: accepted for contract scaffolding; application implementation is pending.

ADR-001 remains reserved for the stack/repository-layout decision requested by the readiness workplan.

## Context

Architecture selects Python/FastAPI/Pydantic and generated shared API types. There is no application yet. Agents need implementable foundation contracts without independently maintaining Python DTOs, OpenAPI and TypeScript. Architecture §§8 and 24 supersede legacy meeting/organization names in the specification.

## Decision

`contracts/models.py` owns wire models and cross-field validators. `contracts/http.py` owns the bounded foundation operation registry. A deterministic generator emits OpenAPI 3.1 and JSON Schema, then pinned openapi-typescript emits client declarations from that OpenAPI. Python services import the source models directly. No server handlers, database models, auth implementation or provider calls are introduced by this decision.

Generated artifacts are committed and checked by regeneration into a temporary directory. CI rejects drift and invalid/unsafe schema fixtures even before an application manifest exists. The first API implementation must test its FastAPI route/schema surface against these contracts. It may use the registry to configure routes; it must not replace the contract authority with independently maintained annotations.

The narrow tooling environment is pinned under `tools/contracts/`; it is not the product dependency manager. When root Python/JS workspaces are introduced, move these exact tool dependencies into the chosen lockfiles and preserve the generation commands and single source. Do not maintain duplicate competing pipelines.

## Alternatives

Hand-authored OpenAPI plus generated Python would add a model generator to the selected Pydantic stack. Hand-maintained DTOs in every language allow drift. A fake FastAPI server would suggest endpoints exist when no behavior is implemented. The chosen small registry produces an honest design contract without exposing placeholder routes.

## Consequences

Structural schemas do not express all semantic checks (for example end time >= start time, current permissions or passage bounds). Python validators enforce local relationships; documented service/database checks enforce contextual invariants. TypeScript and JSON Schema are not evidence of authorization or runtime implementation.

## Security and migration implications

Models forbid unknown fields; request schemas do not accept caller-selected ownership. Fixtures are fictional. No database migration is introduced. Naming follows architecture (`documents`, `tenant_id`), without compatibility aliases because no deployed API exists.

## Tool references

- [Pydantic JSON Schema generation](https://docs.pydantic.dev/latest/concepts/json_schema/)
- [openapi-typescript CLI](https://openapi-ts.dev/cli)
