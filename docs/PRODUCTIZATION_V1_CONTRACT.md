# Productization v1 Phase-0 Contract

Status: **normative Phase-0 design contract**. Parent: Issue #81, synthesized target: Issue #74 comment `5727168855`.

This document freezes productization semantics and acceptance inputs only. It does **not** implement an installer, reusable workflow delivery, scheduler/runtime changes, console redesign, browser relay changes, dependency pin migration, GitHub App mutation, reference-repository provisioning, or any UI experiment.

## 1. Supported v1 profile

A v1 installation is bound to exactly one GitHub.com repository. Scheduler-owned implementation pull requests are local to that repository. External repositories are adapter/executor/evidence sources and every external reference is repository-qualified.

GitHub Actions is required. Two release-gated profiles are normative:

- `public-pages`: public repository, sanitized Pages console only by explicit public opt-in.
- `private-no-public-console`: private repository, no implicit public projection.

Initial v1 does not claim multi-repository control-plane scheduling, GitHub Enterprise Server, Actions-disabled operation, monorepo portability, or public-Issue browser command/result transport.

## 2. Core and optional modules

The reusable core preserves GitHub Issue plus creation-time canonical comments as source of truth; append-only events; deterministic ordering, idempotency, leases and `history_unsafe`; exact-head independent review; expected-head integration; workstream admission; autonomy/review derivation; and a sanitized projection contract.

Product/UX records, Pages presentation, rendered E2E/browser execution, and project adapters are optional/versioned modules. Reusable core must not depend on fixed Issue numbers, historical title prefixes, repository names, branch names, Supabase project IDs, or executor implementation details.

## 3. Configuration and generated installation state

`schemas/productization-v1.schema.json` defines the versioned Phase-0 bundle. Runtime-facing identity is symbolic. Generated state maps roles such as `manager`, `review_manager`, `product_ux`, and `rendered_executor` to installation-specific resources.

The installation record has a durable `installation_id`, repository identity, branch configuration, role bindings, managed-resource inventory, and installed component/schema versions. Reruns reconcile by stable identity rather than title or Issue-number guessing.

Persisted productization config and manifests contain secret **references/names only**, never secret values.

## 4. Trust and authorization

`agent_id` is audit identity and never authentication. Product state-effect authorization is a separate GitHub-native policy. Only configured GitHub principals (App installation, user, or team identity) may be state-effective, and every state effect is represented by an explicit grant binding `principal_id` + `capability` + symbolic `task_scope`. Task scope is either `*`, `role:<symbolic-role>`, or `workstream:<stable-key>`; fixed Issue-number scopes are forbidden. A grant is invalid if the principal is unmapped or if the granted capability is absent from that principal's declared capability set. Marker-bearing comments without a matching principal/capability/task grant are audit-only.

Worker, reviewer, integrator, and deployer capabilities are separable. Production, destructive, account, permission, and security-sensitive actions remain Human Required.

Untrusted/fork PR validation is tokenless/offline. Repository-sensitive replay/projection belongs only to trusted default-branch, schedule, or explicit trusted-manual execution. `pull_request_target` must never combine untrusted-head checkout with secrets or privileged repository reads.

## 5. Supply-chain contract

Executable third-party GitHub Actions are referenced by immutable 40-hex commit SHA. Runtime/package dependencies use lockfiles and deterministic install. Release evidence carries component/action/dependency identities, digests, provenance, and SBOM digest.

Phase 0 validates the contract shape only; it does not migrate existing production workflows.

## 6. Installation lifecycle semantics

Normative lifecycle states are:

`PLANNED -> PREFLIGHT -> INSTALLING -> ACTIVE -> UPGRADING | DEGRADED -> RECOVERING -> ACTIVE -> DECOMMISSIONED`.

Bootstrap is a future product state machine, not `WORKER_BOOTSTRAP.md`. Its contract requires dry-run/preflight, ordered phases, stable operation IDs, resumable journal, deterministic reconcile behavior, explicit irreversible stop points, and human-readable plus machine-readable completion output.

Preflight covers repository identity/visibility, trusted principal/App capability, Actions availability, required checks/protection/environment expectations, console classification/mode, adapter inputs, required secret names/presence, and compatibility.

A second identical run must not duplicate control Issues, workflows, environments, credentials, or generated role bindings. Existing-project collisions require explicit adopt/create/abort resolution.

## 7. Upgrade, rollback, recovery, and decommission

Compatibility is component-aware across protocol/replay, schemas, workflows, validators, projection, console, adapters, browser executor, and generated state. Upgrades use an ordered migration graph and declare supported source versions, mixed-version behavior, dry-run, and post-upgrade validation.

Rollback never edits or deletes canonical GitHub history. Restoring executable/workflow/config versions is allowed only when persisted schemas/events remain backward-compatible. Otherwise downgrade fails closed and forward repair/migration is required.

Recovery contracts cover interrupted installation/upgrade, repository rename/transfer/default-branch drift, rules/permissions/environment drift, disabled/missing schedules, console/deploy failures, revoked credentials, transient artifact loss, and replacement-repository rebuild with a **new** installation identity and preserved audit links.

Browser profile/cache state is optional rebuildable executor state, never control-plane state.

Decommission stops dispatch/schedules, ends browser sessions, revokes runtime/deployment credentials, disables or archives console as configured, removes only ownership-marked generated mutable resources, preserves canonical audit/evidence, and emits a final manifest.

## 8. Browser adapter and privacy

Browser execution is optional. Packaged v1 excludes public-Issue command/result transport. Issues may carry only sanitized launch/control references. Browser command/result data uses a private relay with tenant/session-scoped authorization, isolation, retention, credential rotation/revocation, allowed-target policy, emergency stop, and cross-tenant negative tests.

Same-browser human takeover/resume remains a supported interaction pattern. Customer surfaces expose readiness, requested human task, privacy warning, expiry, resume/end action, and recovery status without requiring relay implementation jargon.

## 9. Operator contract

Primary operator states are: Healthy/Idle, Work in progress, Review needed, Human action needed, Recovery needed, and Completed/Accepted. Distinguish intentional idle from scheduler/workflow failure, expired ownership, Human Required, MAIN_RED, missing permissions, and stale evidence.

A generated Autonomy Policy explains autonomous capabilities, always-human-gated actions, automatic halt conditions, and resume authority.

Every Human Required record exposes reason/category, exact action, affected surface, urgency, safety/privacy note, canonical evidence link, eligible resolver, defer/cancel semantics, expiry/staleness, and resume path.

Evidence surfaces expose immutable source/release identity, measurement time, freshness/staleness, component-vs-release scope, and acceptance status. “Green” does not imply “fresh.”

Accessibility/mobile/language are release gates: keyboard operation, screen-reader/ARIA semantics, color-independent state, visible focus/errors, long-text expansion, narrow/mobile priority for Human Required and next actions, and an explicit supported-language policy.

## 10. Release and evidence identity

A release manifest pins immutable core/protocol/schema/workflow/module/adapter identities and digests, supported profile, config schema, executable Action SHAs, and SBOM/provenance digest.

A durable evidence manifest is independent of Actions artifact retention and includes release manifest digest and exact reference-project commits. Its artifact inventory must machine-cover every required class: `acceptance_results`, `sanitized_e2e_product_ux`, `security_privacy_sanitizer`, `permission_ruleset_environment`, `provenance_sbom`, `audit_logs_findings`, and `emergency_disable_revoke`. Each class carries a durable content digest and provenance reference; a bundle missing any required class is invalid.

Component evidence may be reused only when immutable identities match. Package-level install/permission/generated-state/deployment evidence is rerun for the packaged release.

## 11. Phase-0 acceptance fixtures

The offline validator and fixtures must reject at least:

- fixed Issue-number role identity instead of symbolic roles;
- empty/missing managed resource inventory;
- state-effect authorization referencing an unmapped GitHub principal, granting a capability the principal does not hold, or using a fixed Issue-number task scope;
- mutable executable Action references;
- private classification combined with public Pages;
- public-Issue browser command/result transport;
- incompatible downgrade after a newer persisted schema/event version;
- missing installation identity/resource map or duplicate role binding;
- release/evidence manifests missing immutable identity/digest, mandatory `core`/`workflows` component identities, or any required durable evidence class.

The validator must run with Python standard library only, no network, no GitHub token, and no secret values.

## 12. Gate to later phases

Phase 0 is complete only after exact-head CI, one independent exact-head review, and current-main post-merge validation. It authorizes no Phase 1 runtime packaging by itself. Each later phase requires a fresh #16 admission.
