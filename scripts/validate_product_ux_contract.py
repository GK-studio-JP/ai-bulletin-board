#!/usr/bin/env python3
import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "ai-bb-product-ux-e2e:v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._/-]*$")
LIFECYCLES = {"DISCOVERY","PROPOSED","ADMITTED","REJECTED","DEFERRED","IMPLEMENTING","VERIFIED"}
REQUIRED_METRICS = {
    "transition_success",
    "destination_correct",
    "action_count",
    "vertical_travel_px",
    "vertical_travel_vh",
    "reversal_count",
    "target_visible_before",
    "target_visible_after",
    "target_distance_before_px",
    "target_distance_after_px",
    "horizontal_overflow_px",
    "overlap_count",
    "clipping_count",
    "state_persistence_pass",
    "keyboard_accessibility_pass",
    "empty_error_state_pass",
}
BOOL_METRICS = {
    "transition_success",
    "destination_correct",
    "target_visible_before",
    "target_visible_after",
    "state_persistence_pass",
    "keyboard_accessibility_pass",
    "empty_error_state_pass",
}
NUM_METRICS = REQUIRED_METRICS - BOOL_METRICS
COMMON = {"schema_version","kind","owner","next_action"}
FIELDS = {
    "product_proposal": COMMON | {
        "proposal_id","lifecycle","problem","evidence_refs","expected_user_value",
        "affected_surfaces","dependencies","security_privacy_constraints",
        "acceptance_tests","size_risk","workstream_ref",
    },
    "ux_finding": COMMON | {
        "finding_id","lifecycle","evidence_refs","surfaces","friction","hypothesis",
        "acceptance_tests","workstream_ref","rendered_e2e_ref",
    },
    "journey_definition": {"schema_version","kind","journey_id","steps","expected_destination",
        "required_viewports","required_metrics","evidence_refs","next_action"},
    "e2e_result": {"schema_version","kind","journey_id","executor_schema","measured_at",
        "viewport","metrics","artifact_ref","baseline_ref","comparison","budgets","next_action"},
}
REQUIRED_FIELDS = {
    "product_proposal": {
        "schema_version","kind","proposal_id","lifecycle","problem","evidence_refs",
        "expected_user_value","affected_surfaces","dependencies","security_privacy_constraints",
        "acceptance_tests","size_risk","owner","next_action",
    },
    "ux_finding": {
        "schema_version","kind","finding_id","lifecycle","evidence_refs","surfaces","friction",
        "hypothesis","acceptance_tests","owner","next_action",
    },
    "journey_definition": {
        "schema_version","kind","journey_id","steps","expected_destination","required_viewports",
        "required_metrics","evidence_refs","next_action",
    },
    "e2e_result": {
        "schema_version","kind","journey_id","executor_schema","measured_at","viewport","metrics",
        "artifact_ref","baseline_ref","comparison","budgets","next_action",
    },
}

class ContractError(ValueError):
    pass

def _require(cond, msg):
    if not cond:
        raise ContractError(msg)

def _nonempty_str(value, name):
    _require(isinstance(value, str) and value.strip(), f"{name} must be a non-empty string")

def _id(value, name):
    _nonempty_str(value, name)
    _require(ID_RE.fullmatch(value) is not None, f"{name} must be a stable lowercase identifier")

def _list(value, name, *, nonempty=False):
    _require(isinstance(value, list), f"{name} must be a list")
    if nonempty:
        _require(len(value) > 0, f"{name} must not be empty")
    for item in value:
        _nonempty_str(item, f"{name} item")

def _strict_fields(record, allowed):
    extra = set(record) - allowed
    _require(not extra, f"unknown fields: {sorted(extra)}")

def _required_fields(record, required):
    missing = required - set(record)
    _require(not missing, f"missing required fields: {sorted(missing)}")

def validate_record(record):
    _require(isinstance(record, dict), "record must be an object")
    _require(record.get("schema_version") == SCHEMA_VERSION, "unsupported schema_version")
    kind = record.get("kind")
    _require(kind in FIELDS, "unsupported kind")
    _strict_fields(record, FIELDS[kind])
    _required_fields(record, REQUIRED_FIELDS[kind])

    if "next_action" in record:
        _require(record["next_action"] is None or isinstance(record["next_action"], str),
                 "next_action must be string or null")
    if "owner" in record:
        _nonempty_str(record.get("owner"), "owner")

    if kind in {"product_proposal","ux_finding"}:
        lifecycle = record.get("lifecycle")
        _require(lifecycle in LIFECYCLES, "invalid lifecycle")
        id_key = "proposal_id" if kind == "product_proposal" else "finding_id"
        _id(record.get(id_key), id_key)
        _list(record.get("evidence_refs"), "evidence_refs", nonempty=True)
        _list(record.get("acceptance_tests"), "acceptance_tests", nonempty=True)
        needs_workstream = lifecycle in {"ADMITTED","IMPLEMENTING","VERIFIED"}
        if needs_workstream:
            _nonempty_str(record.get("workstream_ref"), "workstream_ref")
        else:
            _require(record.get("workstream_ref") in {None, ""}, "advisory lifecycle must not claim workstream_ref")

    if kind == "product_proposal":
        for key in ("problem","expected_user_value","size_risk"):
            _nonempty_str(record.get(key), key)
        _list(record.get("affected_surfaces"), "affected_surfaces", nonempty=True)
        _list(record.get("dependencies"), "dependencies")
        _list(record.get("security_privacy_constraints"), "security_privacy_constraints", nonempty=True)

    elif kind == "ux_finding":
        _list(record.get("surfaces"), "surfaces", nonempty=True)
        _nonempty_str(record.get("friction"), "friction")
        _nonempty_str(record.get("hypothesis"), "hypothesis")
        if record.get("lifecycle") == "VERIFIED":
            _nonempty_str(record.get("rendered_e2e_ref"), "rendered_e2e_ref")

    elif kind == "journey_definition":
        _id(record.get("journey_id"), "journey_id")
        _list(record.get("steps"), "steps", nonempty=True)
        _nonempty_str(record.get("expected_destination"), "expected_destination")
        viewports = record.get("required_viewports")
        _require(isinstance(viewports, list) and viewports, "required_viewports must be non-empty list")
        classes = set()
        for vp in viewports:
            _require(isinstance(vp, dict) and set(vp) == {"class","width","height"},
                     "viewport fields must be class,width,height")
            _require(vp["class"] in {"desktop","narrow"}, "viewport class must be desktop or narrow")
            _require(isinstance(vp["width"], int) and vp["width"] > 0, "viewport width must be positive int")
            _require(isinstance(vp["height"], int) and vp["height"] > 0, "viewport height must be positive int")
            classes.add(vp["class"])
        _require(classes == {"desktop","narrow"}, "required_viewports must include desktop and narrow")
        metrics = record.get("required_metrics")
        _require(isinstance(metrics, list) and set(metrics) == REQUIRED_METRICS,
                 "required_metrics must match v1 required metric set")
        _list(record.get("evidence_refs"), "evidence_refs")

    elif kind == "e2e_result":
        _id(record.get("journey_id"), "journey_id")
        _nonempty_str(record.get("executor_schema"), "executor_schema")
        _nonempty_str(record.get("measured_at"), "measured_at")
        vp = record.get("viewport")
        _require(isinstance(vp, dict) and set(vp) == {"class","width","height"},
                 "viewport fields must be class,width,height")
        _require(vp["class"] in {"desktop","narrow"}, "viewport class must be desktop or narrow")
        _require(isinstance(vp["width"], int) and vp["width"] > 0, "viewport width must be positive int")
        _require(isinstance(vp["height"], int) and vp["height"] > 0, "viewport height must be positive int")
        metrics = record.get("metrics")
        _require(isinstance(metrics, dict) and set(metrics) == REQUIRED_METRICS,
                 "metrics must match v1 required metric set")
        for key in BOOL_METRICS:
            _require(isinstance(metrics[key], bool), f"{key} must be boolean")
        for key in NUM_METRICS:
            _require(isinstance(metrics[key], (int,float)) and not isinstance(metrics[key], bool),
                     f"{key} must be numeric")
            _require(metrics[key] >= 0, f"{key} must be non-negative")
        _nonempty_str(record.get("artifact_ref"), "artifact_ref")
        comparison = record.get("comparison")
        _require(comparison in {"baseline","improved","regressed","unchanged","uncompared"},
                 "invalid comparison")
        baseline_ref = record.get("baseline_ref")
        _require(baseline_ref is None or (isinstance(baseline_ref, str) and baseline_ref.strip()),
                 "baseline_ref must be non-empty string or null")
        if comparison == "baseline":
            _require(baseline_ref is None, "baseline comparison must not point to a prior baseline")
        elif comparison in {"improved","regressed","unchanged"}:
            _require(isinstance(baseline_ref, str) and baseline_ref.strip(),
                     f"{comparison} comparison requires baseline_ref")
        elif comparison == "uncompared":
            _require(baseline_ref is None, "uncompared result must not claim baseline_ref")

        budgets = record.get("budgets")
        if budgets is None:
            pass
        else:
            _require(comparison not in {"baseline","uncompared"},
                     "budgets require a compared result with measured baseline")
            _require(isinstance(budgets, dict) and set(budgets) == {"baseline_ref","rationale","thresholds"},
                     "budgets fields must be baseline_ref,rationale,thresholds")
            _nonempty_str(budgets.get("baseline_ref"), "budgets.baseline_ref")
            _nonempty_str(budgets.get("rationale"), "budgets.rationale")
            _require(baseline_ref == budgets["baseline_ref"],
                     "budgets baseline_ref must match result baseline_ref")
            thresholds = budgets.get("thresholds")
            _require(isinstance(thresholds, dict) and thresholds, "budgets.thresholds must be non-empty")
            _require(set(thresholds) <= REQUIRED_METRICS, "budget threshold uses unknown metric")
            for key, value in thresholds.items():
                if key in BOOL_METRICS:
                    _require(isinstance(value, bool), f"budget {key} must be boolean")
                else:
                    _require(isinstance(value, (int,float)) and not isinstance(value, bool) and value >= 0,
                             f"budget {key} must be non-negative numeric")
    return record

def validate_records(records):
    _require(isinstance(records, list) and records, "records must be a non-empty list")
    for record in records:
        validate_record(record)

    results = [record for record in records if record.get("kind") == "e2e_result"]
    by_artifact = {}
    for result in results:
        ref = result["artifact_ref"]
        _require(ref not in by_artifact, f"duplicate e2e artifact_ref: {ref}")
        by_artifact[ref] = result

    for result in results:
        baseline_ref = result["baseline_ref"]
        if baseline_ref is None:
            continue
        baseline = by_artifact.get(baseline_ref)
        _require(baseline is not None, f"baseline_ref does not resolve to measured result: {baseline_ref}")
        _require(baseline["comparison"] == "baseline" and baseline["baseline_ref"] is None,
                 "baseline_ref must resolve to a baseline result")
        _require(baseline["journey_id"] == result["journey_id"],
                 "baseline_ref must resolve to the same journey_id")
        _require(baseline["executor_schema"] == result["executor_schema"],
                 "baseline_ref must resolve to the same executor_schema")
        _require(baseline["viewport"] == result["viewport"],
                 "baseline_ref must resolve to the same viewport")
        if result["budgets"] is not None:
            _require(result["budgets"]["baseline_ref"] == baseline["artifact_ref"],
                     "budgets must resolve to the measured baseline result")
    return records

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    args = parser.parse_args()
    data = json.loads(Path(args.path).read_text())
    records = data if isinstance(data, list) else [data]
    validate_records(records)
    print(f"validated {len(records)} record(s) against {SCHEMA_VERSION}")

if __name__ == "__main__":
    try:
        main()
    except (ContractError, json.JSONDecodeError, OSError) as exc:
        print(f"contract validation failed: {exc}", file=sys.stderr)
        sys.exit(1)
