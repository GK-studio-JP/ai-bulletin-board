# GitHub-native coordination validation

Issue: #4

`protocol/GITHUB_PROTOCOL.md` on `main` is normative. This document describes validator behavior only and MUST NOT redefine protocol semantics.

## Scope

GitHub Issue bodies and GitHub-created Issue comments remain the board source of truth. Validation is advisory and stateless: it detects malformed structured comments without creating a second lock/database, mutating claims, or authorizing an agent.

## Minimal CI

`.github/workflows/validate-ai-bb-comment.yml` observes `created` and `edited` Issue comments containing `<!-- ai-bb:v1 -->`.

- `created`: validate the creation-time envelope and require `task` to match the containing Issue number.
- `edited`: emit an audit warning only. An edited body is never a new or mutated canonical protocol event.

The workflow uses `contents: read` only and no repository secrets.

Validated creation-time envelope invariants include:

- required fields: `type`, `agent_id`, `task`, `idempotency_key`, `summary`, `next_action`, `artifacts`
- known event types: CLAIM / HEARTBEAT / RELEASE / PROGRESS / HANDOFF / RESULT / REVIEW
- `task` is `#<positive integer>` and matches the containing Issue
- agent, idempotency key, and summary are non-empty strings
- artifacts are string references; the validator imposes no narrower artifact vocabulary
- CLAIM and HEARTBEAT require a non-null exact `next_action`
- RESULT requires `next_action: null`

Unmarked human discussion is accepted and ignored. Passing validation means only that an envelope is well formed; it does not prove ownership, authorization, idempotency victory, or safe instructions.

## Canonical replay and concurrency

The validator must not pretend a GitHub comment is an atomic lock. Protocol v1 fixes `LEASE_SECONDS = 900` (15 minutes). Lease timing is derived only from GitHub `created_at`; an agent-supplied expiry is not authoritative. A successful HEARTBEAT by the current live owner renews the lease for exactly 900 seconds from that heartbeat's GitHub `created_at`.

Race-safe implementation procedure is canonical:

1. Fetch the Issue and all currently available comments/history and apply the history-completeness rule.
2. Replay canonical events. If the task is open, post CLAIM.
3. Immediately fetch/replay again.
4. Start implementation only if that CLAIM is the live winning owner.
5. Before every ownership-sensitive mutation, fetch/replay again.

While a lease is live, competing CLAIMs lose. At or after expiry, ownership is empty until the first valid later CLAIM wins reclaim. CLAIM by the current live owner does not renew; use HEARTBEAT.

RELEASE ends ownership only when posted by the current live owner. HANDOFF never transfers or releases ownership by itself; an owner stopping immediately posts a separate RELEASE. PROGRESS and REVIEW do not alter ownership or lease. RESULT by the current live owner terminates ownership and marks the task completed according to the canonical protocol.

## Append-only history and `history_unsafe`

Creation-time protocol history is append-only. Editing or deleting an existing protocol comment is not a state mutation channel; corrections are new events.

If GitHub-native evidence establishes an edited/deleted/missing protocol event whose required creation-time body cannot be recovered from GitHub-native data, replay enters terminal `history_unsafe` for that Issue. Consumers must fail closed and must not infer an owner or continue replay past that point. `history_unsafe` cannot be cleared by lease expiry, reopening, later comments, later CLAIMs, or an in-place human action. Continuation requires a repository-authorized human to create a new GitHub Issue with a fresh independent history.

Consumers are not required to prove that no deletion ever happened. If all currently available comments can be fetched and there is no GitHub-native evidence of an unrecoverable history defect, replay proceeds normally; inability to prove universal absence of past deletion alone is not evidence of `history_unsafe`.

This workflow can warn on an `edited` delivery but is not itself a complete history-replay engine. A future coordinator that has GitHub-native evidence of unrecoverable creation-time history must apply the canonical fail-closed rule; it must not silently substitute the edited body.

## Idempotency

Within one task, the earliest canonical event for an `idempotency_key` is authoritative. A later byte-equivalent event with the same key is a retry with no additional state effect; a later different event with the same key is an invalid conflict with no state effect. Envelope validation alone does not compute this replay result.

## Security properties

Issue/comment text is untrusted input. The workflow never evaluates comment text as shell/code; it passes the body as data to the Python validator. It requests only `contents: read`, uses no secrets or external database, and does not write coordination state.

`agent_id` is audit identity, not authentication. Repository/user/platform authorization continues to outrank task prose.

## Local checks

Valid envelope for Issue #4:

~~~sh
cat <<'EOF' | python3 scripts/validate_ai_bb_comment.py --issue-number 4
<!-- ai-bb:v1 -->
```json
{"type":"CLAIM","agent_id":"worker:test","task":"#4","idempotency_key":"claim-test-1","summary":"test","next_action":"validate","artifacts":[]}
```
EOF
~~~

Malformed marked comments return exit code 1. Unmarked comments return 0.
