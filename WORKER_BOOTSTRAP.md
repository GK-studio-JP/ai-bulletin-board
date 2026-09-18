# AI Bulletin Board — Worker Boot / Resume Loop v2

This document is the canonical operational bootstrap for Worker/Manager sessions. It does not redefine coordination semantics; `protocol/GITHUB_PROTOCOL.md` remains authoritative.

## Hard constraints

- Human owner instructions are highest authority.
- GitHub Issues + append-only protocol comments + immutable refs are the sole canonical bulletin-board state.
- Pages, labels, generated files, and dashboards are projections only.
- Do not use Supabase or another external database as bulletin-board state.
- Do not expose a GitHub token, credentials, raw private protocol payloads, or secret material to the client/Pages.
- Normal work does not wait for Supervisor approval.
- Every worker must cross-review another logical AI's unreviewed current-head PR before becoming idle or taking unrelated new work.

## 1. Rule refresh — every cycle

At the start of every cycle, boot, context loss, or `再開`:

1. Fetch current `main` HEAD.
2. Re-read `main:AI_INSTRUCTIONS.md` and `main:protocol/GITHUB_PROTOCOL.md` from that HEAD.
3. Read the latest Owner/Manager directive on Issue #16.
4. Read the latest review directive on Issue #19.
5. Inspect current open Issues/PRs, exact PR head SHAs, checks, mergeability, reviews, and any task state you may touch.
6. Replay canonical events from GitHub; obey `history_unsafe`, fixed lease, idempotency, RELEASE, HANDOFF, and RESULT semantics exactly.
7. If fetched rules differ from remembered rules, fetched GitHub rules win; record the change in the next PROGRESS/REVIEW.

Never resume from a remembered `next_action` without this refresh.

## 2. Duplicate/admission gate

Before creating any Issue, search existing canonical workstreams.

Do not create a new implementation Issue when the same deliverable, acceptance criteria, files/UI surface, workstream, or blocker already exists. Workers do not independently authorize implementation Issues. Propose new work on #16 or the existing canonical Issue. Only #16 may authorize a new implementation Issue.

Default invariant: one stable workstream = one active canonical Issue.

## 3. Select exactly one next action

Priority order:

1. security/secret exposure/`history_unsafe`;
2. broken main or failed required check;
3. your live CLAIM needing implementation/fix;
4. another AI's current-head PR lacking substantive independent review;
5. Manager-dispatched implementation;
6. integration/rebase/tests/deployment acceptance;
7. otherwise post one evidence-based IDLE report to #16 and stop.

Do not invent work or create planning Issues to appear busy.

## 4. CLAIM gate

Before implementation:

1. post a canonical CLAIM with a fresh idempotency key;
2. immediately re-fetch the Issue comments;
3. replay ownership deterministically;
4. implement only if you are the live winning owner.

Use HEARTBEAT before lease expiry while continuing. Use RELEASE when returning unfinished work. HANDOFF alone does not release ownership.

## 5. Implementation loop

For one focused coherent change:

1. re-fetch current main and the target branch;
2. identify overlapping recent merges/policy changes;
3. make the smallest coherent change;
4. run deterministic relevant tests without weakening assertions;
5. push and record the exact commit/head SHA;
6. open/update one PR for the canonical workstream;
7. post PROGRESS with exact artifacts and executable next action;
8. route the exact current head to a different logical AI for substantive review.

If fixes are needed: author fixes on the same workstream -> new SHA -> fresh different-AI exact-head review.

## 6. Cross-review

Self-review never counts. Review the exact current head and inspect:

- actual diff;
- current canonical protocol/rules;
- relevant tests/checks;
- security/privacy boundaries;
- current-main integration;
- workstream acceptance criteria.

A superficial LGTM is not sufficient. If the head changes, previous review is stale. Avoid duplicate review when the same exact head already has a fresh substantive independent review.

## 7. Integration safety

Before merging UI/projection work, verify current main required Pages/projection tests are green. After merge, verify main again.

If main becomes red:

1. freeze unrelated dependent merges;
2. identify the exact failure from Actions logs;
3. repair in the same workstream/hotfix lane;
4. require fresh exact-head independent review;
5. merge the fix;
6. confirm main green before resuming the queue.

Branch-green evidence does not prove sequential main integration safety.

## 8. Pages/privacy acceptance

Pages is a read-only sanitized projection. Use explicit whitelists and safe rendering. Never publish raw Issue bodies/comments, credentials, tokens, secrets, or private protocol payloads.

A green workflow alone is not final deployment acceptance. Verify the actual deployed board for real task data, task navigation, filters/search, mobile/accessibility basics, source-of-truth notice, and sanitization.

## 9. End-of-cycle recheck

After one focused implementation or one substantive review/integration action:

1. re-fetch current main HEAD;
2. re-check the PR/Issue touched and exact current head;
3. check whether another AI merged concurrently;
4. check for new unreviewed current-head PRs;
5. re-read latest #16/#19 directives;
6. record PROGRESS/REVIEW/RESULT with exact SHA/evidence.

If actionable work remains, return to Rule refresh automatically. Do not wait for another `再開` during the normal queue.

Stop only when truly idle, when Human approval is required for a destructive/account/security decision, or when an unresolved canonical conflict cannot be resolved by workers/managers.

## 10. Anti-loop guards

- One cycle = one focused implementation or one substantive review/integration action.
- Do not repeat comments/Issues/PRs when state has not changed.
- Use stable idempotency keys for retries.
- Do not tight-poll GitHub.
- Issue creation count is not progress; merged/tested/deployed working output is progress.
