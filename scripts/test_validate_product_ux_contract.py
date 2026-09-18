#!/usr/bin/env python3
import copy
from validate_product_ux_contract import ContractError, REQUIRED_METRICS, validate_record

SCHEMA = "ai-bb-product-ux-e2e:v1"

def must_fail(record, contains):
    try:
        validate_record(record)
    except ContractError as exc:
        assert contains in str(exc), (contains, str(exc))
    else:
        raise AssertionError(f"expected failure containing {contains!r}")

proposal = {
    "schema_version": SCHEMA,
    "kind": "product_proposal",
    "proposal_id": "product/search-shortcuts",
    "lifecycle": "PROPOSED",
    "problem": "Repeated navigation requires too many actions.",
    "evidence_refs": ["artifact:rendered-e2e/search-20260918"],
    "expected_user_value": "Reduce repeated navigation cost.",
    "affected_surfaces": ["pages-board"],
    "dependencies": [],
    "security_privacy_constraints": ["sanitized projection only"],
    "acceptance_tests": ["rendered journey remains within admitted budget"],
    "size_risk": "small UI change; low architecture risk",
    "owner": "product-lab",
    "next_action": "Request #16 admission after baseline evidence review",
}
validate_record(proposal)

bad = copy.deepcopy(proposal)
bad["workstream_ref"] = "v0.3/unadmitted"
must_fail(bad, "advisory lifecycle")

admitted = copy.deepcopy(proposal)
admitted["lifecycle"] = "ADMITTED"
admitted["workstream_ref"] = "v0.3/autonomy-ops"
validate_record(admitted)

finding = {
    "schema_version": SCHEMA,
    "kind": "ux_finding",
    "finding_id": "ux/mobile-filter-friction",
    "lifecycle": "VERIFIED",
    "evidence_refs": ["artifact:rendered-e2e/mobile-filter-20260918"],
    "surfaces": ["pages-board"],
    "friction": "Filter path is visually dense on narrow screens.",
    "hypothesis": "Grouping controls reduces scan cost.",
    "acceptance_tests": ["desktop and narrow rendered evidence remains clean"],
    "workstream_ref": "v0.3/autonomy-ops",
    "rendered_e2e_ref": "artifact:rendered-e2e/mobile-filter-after",
    "owner": "ux-lab",
    "next_action": None,
}
validate_record(finding)

bad = copy.deepcopy(finding)
bad.pop("rendered_e2e_ref")
must_fail(bad, "rendered_e2e_ref")

journey = {
    "schema_version": SCHEMA,
    "kind": "journey_definition",
    "journey_id": "board/find-open-task",
    "steps": ["board_landing","search_task","open_task"],
    "expected_destination": "canonical_issue",
    "required_viewports": [
        {"class":"desktop","width":1440,"height":900},
        {"class":"narrow","width":390,"height":844},
    ],
    "required_metrics": sorted(REQUIRED_METRICS),
    "evidence_refs": ["Issue:#59","Issue:#62"],
    "next_action": "Collect first real baseline",
}
validate_record(journey)

bad = copy.deepcopy(journey)
bad["required_viewports"] = [{"class":"desktop","width":1440,"height":900}]
must_fail(bad, "desktop and narrow")

metrics = {
    "transition_success": True,
    "destination_correct": True,
    "action_count": 3,
    "vertical_travel_px": 640,
    "vertical_travel_vh": 0.758,
    "reversal_count": 0,
    "target_visible_before": False,
    "target_visible_after": True,
    "target_distance_before_px": 520,
    "target_distance_after_px": 0,
    "horizontal_overflow_px": 0,
    "overlap_count": 0,
    "clipping_count": 0,
    "state_persistence_pass": True,
    "keyboard_accessibility_pass": True,
    "empty_error_state_pass": True,
}
baseline = {
    "schema_version": SCHEMA,
    "kind": "e2e_result",
    "journey_id": "board/find-open-task",
    "executor_schema": "browser-agent-rendered-e2e:v1",
    "measured_at": "2026-09-18T01:00:00Z",
    "viewport": {"class":"narrow","width":390,"height":844},
    "metrics": metrics,
    "artifact_ref": "artifact:10500000000",
    "baseline_ref": None,
    "comparison": "baseline",
    "budgets": None,
    "next_action": "Use measured baseline to propose justified budgets",
}
validate_record(baseline)

bad = copy.deepcopy(baseline)
bad["budgets"] = {
    "baseline_ref": "artifact:made-up",
    "rationale": "arbitrary",
    "thresholds": {"action_count": 2},
}
must_fail(bad, "must match result baseline_ref")

compared = copy.deepcopy(baseline)
compared["baseline_ref"] = "artifact:10500000000"
compared["comparison"] = "unchanged"
compared["budgets"] = {
    "baseline_ref": "artifact:10500000000",
    "rationale": "Thresholds are derived from the accepted measured baseline and preserve current successful journey behavior.",
    "thresholds": {
        "transition_success": True,
        "destination_correct": True,
        "action_count": 4,
        "horizontal_overflow_px": 0,
    },
}
validate_record(compared)

bad = copy.deepcopy(compared)
bad["raw_page_text"] = "private payload"
must_fail(bad, "unknown fields")

print("Product/UX/E2E contract regressions passed")
