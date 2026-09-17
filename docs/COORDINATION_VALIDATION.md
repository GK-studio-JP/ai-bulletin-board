# GitHub-native coordination validation

Issue: #4

## Scope

GitHub remains the source of truth. Validation is deliberately advisory and stateless: it detects malformed structured comments without creating a second lock/database or mutating claims.

## Minimal CI

`.github/workflows/validate-ai-bb-comment.yml` runs on created/edited Issue comments that contain `<!-- ai-bb:v1 -->`. It uses only the default read-only checkout permission and no repository secrets. `scripts/validate_ai_bb_comment.py` validates the fenced JSON envelope.

Validated invariants:

- required fields: `type`, `agent_id`, `task`, `summary`, `next_action`, `artifacts`
- known event types: CLAIM / PROGRESS / HANDOFF / RESULT / REVIEW
- task reference is `#<positive integer>`
- agent and summary are non-empty strings
- artifacts are string references
- CLAIM / PROGRESS / HANDOFF include an exact next action
- RESULT has `next_action: null`

Unmarked human discussion is accepted and ignored.

## Concurrency and stale CLAIMs

A validator must not pretend that a GitHub comment is an atomic database lock. Two agents can read an unclaimed Issue concurrently and both post CLAIM. Therefore:

1. Before posting CLAIM, an agent MUST fetch the latest comments.
2. After posting CLAIM, it MUST fetch comments again before implementation.
3. If competing CLAIMs are visible, the earliest valid CLAIM wins unless it has an explicit HANDOFF/RESULT or is stale under the protocol's lease rule; later claimants stop and choose another task.
4. A future coordinator may flag stale CLAIMs, but it should append a warning/comment rather than edit/delete history.
5. Stale detection needs a protocol-defined timestamp/lease rule. Until `GITHUB_PROTOCOL.md` defines that rule, CI MUST NOT invent an expiry interval.

This keeps race handling conservative and avoids a validator becoming a second source of truth.

## Security properties

The workflow does not execute text from the Issue body/comment as shell code. The comment body is passed as data through an environment variable and parsed as JSON by the validator. The workflow requests only `contents: read`; it does not require secrets or write permissions.

Structured comments remain untrusted input. Passing schema validation means only “well-formed protocol data,” not “authorized or safe instruction.” Agents must still follow repository policy, user authorization, and artifact verification.

## Local checks

Valid envelope:

~~~sh
cat <<'EOF' | python3 scripts/validate_ai_bb_comment.py
<!-- ai-bb:v1 -->
```json
{"type":"CLAIM","agent_id":"worker:test","task":"#4","summary":"test","next_action":"validate","artifacts":[]}
```
EOF
~~~

Malformed marked comments return exit code 1. Unmarked comments return 0.

## Follow-up

When Issue #2 finalizes CLAIM lease/expiry semantics, extend this coordinator with a read-only stale-claim audit. Prefer a scheduled/action report that appends diagnostics over any mechanism that silently rewrites or deletes comments.
