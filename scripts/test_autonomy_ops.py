#!/usr/bin/env python3
"""Deterministic regressions for v0.3 autonomy/watchdog derivation."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("autonomy", Path(__file__).with_name("autonomy_ops.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def row(task="#1", state="open", lease="", review=False, head="", next_action="work"):
    return {
        "task": task, "state": state, "agent": "", "lease_status": lease,
        "review_needed": review, "current_head": head, "next_action": next_action,
    }


# Duplicate dispatch/workstream must be a first-class health violation.
out = m.derive([row()], [], "MAIN_GREEN", {"v0.3/autonomy-ops": [59, 60]})
assert out["health"]["duplicate_workstream_violation"] is True

# Same exact SHA reviewed by more than one logical reviewer is a review storm.
reviews = [{"pr": 12, "head": "PR:#12@abcdef1", "review_needed": False, "review_count": 2, "stale_review_count": 0}]
out = m.derive([row(head="PR:#12@abcdef1")], reviews, "MAIN_GREEN", {})
assert out["health"]["review_storm"] is True

# Stale SHA review is surfaced and does not satisfy current-head work.
reviews = [{"pr": 12, "head": "PR:#12@abcdef2", "review_needed": True, "review_count": 0, "stale_review_count": 1}]
out = m.derive([row(head="PR:#12@abcdef2", review=True)], reviews, "MAIN_GREEN", {})
assert out["health"]["stale_review"] is True
assert out["queue"][0]["next_class"] == "review-needed"

# Red main freezes ordinary implementation/integration behind broken-main/security.
out = m.derive([row(task="#9"), row(task="#10", head="PR:#10@abcdef1")], [], "MAIN_RED", {})
assert all(x["next_class"] == "broken-main/security" for x in out["queue"])

# Lease expiry/reclaim availability remains visible: stale open task is implementation-ready.
out = m.derive([row(task="#11", state="open", lease="stale")], [], "MAIN_GREEN", {})
assert out["health"]["stale_or_expiring_claim"] is True
assert out["queue"][0]["next_class"] == "implementation-ready"

# Human-required escalation outranks otherwise implementation-ready state.
out = m.derive([row(task="#23", next_action="Human Owner must decide repository visibility")], [], "MAIN_GREEN", {})
assert out["health"]["human_required"] is True
assert out["queue"][0]["next_class"] == "idle/human-required"

# Main status is conservative: unknown without checks; red on any failure; green only all-complete safe conclusions.
assert m.main_check_state([]) == "MAIN_UNKNOWN"
assert m.main_check_state([{"status": "completed", "conclusion": "failure"}]) == "MAIN_RED"
assert m.main_check_state([
    {"status": "completed", "conclusion": "success"},
    {"status": "completed", "conclusion": "skipped"},
]) == "MAIN_GREEN"

print("autonomy_ops regressions: ok")
