from pathlib import Path

html = Path("pages/index.html").read_text(encoding="utf-8")

# The search field updates results/URL on input. Its later blur/change event must
# not trigger a second synchronous render that can replace a task link during
# activation. Non-search controls still update on change.
required = [
    "const filterForm=document.getElementById('filters')",
    "filterForm.addEventListener('input',event=>{if(event.target.matches('input[type=\"search\"]'))updateQuery()})",
    "filterForm.addEventListener('change',event=>{if(!event.target.matches('input[type=\"search\"]'))updateQuery()})",
]
for snippet in required:
    assert snippet in html, f"missing guarded filter event policy: {snippet}"

assert "addEventListener('change',updateQuery)" not in html
assert "addEventListener('input',updateQuery)" not in html

# Deterministic event-order contract for the deployed UI:
# typing search -> one update; blur/change of that search -> no second update;
# select change -> one update.
def updates(event_type: str, control_type: str) -> bool:
    if event_type == "input":
        return control_type == "search"
    if event_type == "change":
        return control_type != "search"
    return False

assert updates("input", "search")
assert not updates("change", "search")
assert updates("change", "select")
assert not updates("input", "select")

print("PAGES_FILTER_EVENT_REGRESSION_OK")


# v0.3 console remains a read-only presentation over the same sanitized board.json.
console_contract = [
    'id="v03-console"',
    'id="health-panel"',
    'id="human-required"',
    'id="autonomy-groups"',
    'id="review-queue"',
    'id="product-proposals"',
    'id="ux-findings"',
    'id="e2e-latest"',
    "function renderV03(data)",
    "renderV03(data)",
    "next_class",
    "waiting_reason",
    "review_queue",
    "human_required",
    "product_ux",
    "visual_acceptance_status",
    "baseline_ref",
    "comparison",
    "budgets",
    "expected_user_value",
    "acceptance_tests",
]
for snippet in console_contract:
    assert snippet in html, f"missing v0.3 presentation contract: {snippet}"

# New operational surfaces must not introduce another data source or unsafe HTML writes.
assert html.count("fetch(") == 1
assert "fetch('./board.json'" in html
assert "innerHTML" not in html
assert "localStorage" not in html
assert "sessionStorage" not in html
assert "method:'POST'" not in html
assert 'method:"POST"' not in html

# Presentation grouping is keyed by the sanitized next_class field. The same
# deterministic rule is used for fixture/readiness reasoning before #30 lands.
fixture_queue = [
    {"task": "#1", "next_class": "review-needed"},
    {"task": "#2", "next_class": "review-needed"},
    {"task": "#3", "next_class": "idle/human-required"},
    {"task": "#4"},
]
groups = {}
for row in fixture_queue:
    groups.setdefault(str(row.get("next_class") or "unclassified"), []).append(row["task"])
assert groups == {
    "review-needed": ["#1", "#2"],
    "idle/human-required": ["#3"],
    "unclassified": ["#4"],
}

assert "row.expected_user_value" in html
assert "row.acceptance_tests" in html
assert "row.value" not in html
assert "row.acceptance)" not in html

print("PAGES_V03_CONSOLE_REGRESSION_OK")
