#!/usr/bin/env python3
import copy
from validate_product_ux_contract import (
    ContractError,
    REQUIRED_METRICS,
    validate_record,
    validate_records,
)

SCHEMA = "ai-bb-product-ux-e2e:v1"

def must_fail(record, contains):
    try:
        validate_record(record)
    except ContractError as exc:
        assert contains in str(exc), (contains, str(exc))
    else:
        raise AssertionError(f"expected failure containing {contains!r}")

def must_fail_records(records, contains):
    try:
        validate_records(records)
    except ContractError as exc:
        assert contains in str(exc), (contains, str(exc))
    else:
        raise AssertionError(f"expected collection failure containing {contains!r}")

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
bad.pop("owner")
must_fail(bad, "missing required fields")

bad = copy.deepcopy(proposal)
bad.pop("next_action")
must_fail(bad, "missing required fields")

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
bad.pop("owner")
must_fail(bad, "missing required fields")

bad = copy.deepcopy(finding)
bad.pop("next_action")
must_fail(bad, "missing required fields")

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
validate_records([baseline])

bad = copy.deepcopy(baseline)
bad["measured_at"] = "not-a-timestamp"
must_fail(bad, "ISO-8601 date-time")

bad = copy.deepcopy(baseline)
bad["measured_at"] = "2026-09-18T01:00:00"
must_fail(bad, "include timezone")

bad = copy.deepcopy(baseline)
bad["comparison"] = "improved"
must_fail(bad, "requires baseline_ref")

bad = copy.deepcopy(baseline)
bad["comparison"] = "uncompared"
bad["baseline_ref"] = "artifact:10500000000"
must_fail(bad, "uncompared result")

compared = copy.deepcopy(baseline)
compared["artifact_ref"] = "artifact:10500000001"
compared["measured_at"] = "2026-09-18T02:00:00Z"
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
validate_records([baseline, compared])

same_time_baseline = copy.deepcopy(baseline)
same_time_baseline["measured_at"] = compared["measured_at"]
must_fail_records([same_time_baseline, compared], "strictly prior measured result")

future_baseline = copy.deepcopy(baseline)
future_baseline["measured_at"] = "2026-09-18T03:00:00Z"
must_fail_records([future_baseline, compared], "strictly prior measured result")

bad = copy.deepcopy(compared)
bad["baseline_ref"] = "artifact:does-not-exist"
bad["budgets"]["baseline_ref"] = "artifact:does-not-exist"
must_fail_records([baseline, bad], "does not resolve to measured result")

wrong_journey_baseline = copy.deepcopy(baseline)
wrong_journey_baseline["artifact_ref"] = "artifact:wrong-journey"
wrong_journey_baseline["journey_id"] = "board/other-journey"
bad = copy.deepcopy(compared)
bad["baseline_ref"] = "artifact:wrong-journey"
bad["budgets"]["baseline_ref"] = "artifact:wrong-journey"
must_fail_records([wrong_journey_baseline, bad], "same journey_id")

wrong_viewport_baseline = copy.deepcopy(baseline)
wrong_viewport_baseline["artifact_ref"] = "artifact:wrong-viewport"
wrong_viewport_baseline["viewport"] = {"class":"desktop","width":1440,"height":900}
bad = copy.deepcopy(compared)
bad["baseline_ref"] = "artifact:wrong-viewport"
bad["budgets"]["baseline_ref"] = "artifact:wrong-viewport"
must_fail_records([wrong_viewport_baseline, bad], "same viewport")

bad = copy.deepcopy(compared)
bad["raw_page_text"] = "private payload"
must_fail(bad, "unknown fields")

print("Product/UX/E2E contract regressions passed")


# Keep Productization Phase-0 validation inside the existing tokenless PR CI gate.
# This is validation-only: it does not change runtime, scheduler, or workflow behavior.
import runpy
from pathlib import Path

runpy.run_path(
    str(Path(__file__).with_name("test_validate_productization_contract.py")),
    run_name="__main__",
)
