# Product / UX / Rendered E2E board contract v1

This document defines the first GitHub-side contract for the standing Product / Feature Lab and UX / UI Optimization Lab admitted under Issue #59. It is a **board-side sanitized contract only**. Browser measurement implementation remains on Issue #62 / `v0.3/browser-e2e-executor`.

## Authority and boundaries

- GitHub Issues, append-only canonical protocol comments, and immutable refs remain authoritative.
- This contract is versioned evidence/projection data, never canonical scheduler state.
- Product/UX proposals are advisory until #16 admits implementation through the anti-dup/workstream gate.
- Proposal/executor authors do not self-approve implementation; exact implementation heads require independent #19 review.
- Browser-agent/Supabase are executor-private transport only.
- Do not store raw page text, raw Issue/comment payloads, credentials, tokens, query values, hashes, cookies, or private browser observations in this contract.

## Contract version

All records use:

```json
{"schema_version":"ai-bb-product-ux-e2e:v1"}
```

Unknown fields fail validation so the Pages whitelist remains explicit.

## Product proposal record

Required fields:

- `kind`: `"product_proposal"`
- `proposal_id`: stable lowercase identifier
- `lifecycle`: one of `DISCOVERY`, `PROPOSED`, `ADMITTED`, `REJECTED`, `DEFERRED`, `IMPLEMENTING`, `VERIFIED`
- `problem`: concise sanitized problem statement
- `evidence_refs`: one or more GitHub-native or sanitized rendered-E2E artifact refs
- `expected_user_value`: concise expected value
- `affected_surfaces`: non-empty list
- `dependencies`: list, possibly empty
- `security_privacy_constraints`: non-empty list
- `acceptance_tests`: non-empty list
- `size_risk`: concise implementation-size/risk statement
- `owner`: logical owner or queue name
- `next_action`: executable next action or `null`

`owner` and `next_action` are required keys for every Product proposal record (`next_action` may be `null` only when intentionally terminal). `ADMITTED`, `IMPLEMENTING`, and `VERIFIED` records additionally require `workstream_ref`. Earlier advisory states must not claim an implementation workstream.

## UX finding / experiment record

Required fields:

- `kind`: `"ux_finding"`
- `finding_id`: stable lowercase identifier
- `lifecycle`: one of `DISCOVERY`, `PROPOSED`, `ADMITTED`, `REJECTED`, `DEFERRED`, `IMPLEMENTING`, `VERIFIED`
- `evidence_refs`: non-empty rendered/browser or GitHub evidence refs
- `surfaces`: non-empty list
- `friction`: concise sanitized description
- `hypothesis`: proposed improvement hypothesis
- `acceptance_tests`: non-empty list
- `owner`
- `next_action`

`owner` and `next_action` are required keys for every UX finding record (`next_action` may be `null` only when intentionally terminal). Meaningful UI changes do not become `VERIFIED` without a `rendered_e2e_ref` pointing to real deployed desktop+narrow evidence.

## Canonical journey definition

A journey definition is versioned before cosmetic optimization:

- `kind`: `"journey_definition"`
- `journey_id`
- `steps`: ordered symbolic actions such as `board_landing`, `search_task`, `open_task`; do not embed private text or target URL values
- `expected_destination`: a sanitized destination class such as `canonical_issue` or `board_filtered`
- `required_viewports`: must include at least one `desktop` and one `narrow` entry
- `required_metrics`: metric names required by the Human Owner directive
- `evidence_refs`
- `next_action`

Required metric names for v1 are:

`transition_success`, `destination_correct`, `action_count`, `vertical_travel_px`, `vertical_travel_vh`, `reversal_count`, `target_visible_before`, `target_visible_after`, `target_distance_before_px`, `target_distance_after_px`, `horizontal_overflow_px`, `overlap_count`, `clipping_count`, `state_persistence_pass`, `keyboard_accessibility_pass`, and `empty_error_state_pass`.

## Rendered E2E result / baseline record

- `kind`: `"e2e_result"`
- `journey_id`
- `executor_schema`: executor-produced schema identifier, currently expected to be a sanitized browser-agent rendered-E2E schema
- `measured_at`: ISO-8601 timestamp
- `viewport`: `{"class":"desktop|narrow","width":int,"height":int}`
- `metrics`: exactly the required numeric/boolean metrics above
- `artifact_ref`: sanitized GitHub artifact/ref identifier
- `baseline_ref`: prior accepted result ref or `null`
- `comparison`: `"baseline" | "improved" | "regressed" | "unchanged" | "uncompared"`
- `budgets`: object or `null`
- `next_action`

A first measured result may establish a baseline with `baseline_ref: null`, `comparison: "baseline"`, and `budgets: null`.

Budgets are not allowed until measured baseline evidence exists. Any non-null `budgets` object must include:

- `baseline_ref`: non-empty ref matching measured evidence
- `rationale`: non-empty evidence-based rationale
- `thresholds`: non-empty map of metric names to numeric/boolean thresholds

The validator performs collection-level reference resolution. `improved`, `regressed`, and `unchanged` results must resolve `baseline_ref` to an included measured `comparison: "baseline"` result for the same journey, executor schema, and exact viewport; `uncompared` and baseline results must not claim a prior baseline. Any non-null budget must resolve to that same measured baseline and include evidence-based rationale. A matching string alone is insufficient. This prevents arbitrary or nonexistent baseline refs from silently turning thresholds into gates.

## Projection safety

Pages may project only explicit fields from validated records. It must not serialize arbitrary nested source payloads. Evidence fields contain references, not raw issue/comment/browser contents. If a producer cannot map a value into this whitelist without carrying private/raw content, omit the record and report a blocker rather than widening the schema implicitly.
