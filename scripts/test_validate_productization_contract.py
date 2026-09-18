#!/usr/bin/env python3
"""Deterministic offline regressions for Productization v1 Phase-0 contracts."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from validate_productization_contract import ContractError, SCHEMA_VERSION, validate_bundle

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "productization-v1.schema.json"
REFERENCE_PATH = ROOT / "data" / "productization-v1" / "reference-bundle.json"
NEGATIVE_PATH = ROOT / "data" / "productization-v1" / "negative-fixtures.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def mutate(document, operations):
    out = copy.deepcopy(document)
    for op in operations:
        target = out
        parts = op["path"]
        for part in parts[:-1]:
            target = target[part]
        leaf = parts[-1]
        if op["op"] == "set":
            target[leaf] = copy.deepcopy(op["value"])
        elif op["op"] == "delete":
            del target[leaf]
        else:
            raise AssertionError(f"unsupported fixture operation {op['op']!r}")
    return out


def must_fail(record, contains):
    try:
        validate_bundle(record)
    except ContractError as exc:
        message = str(exc)
        assert contains in message, (contains, message)
    else:
        raise AssertionError(f"expected failure containing {contains!r}")


schema = load(SCHEMA_PATH)
assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
assert schema["additionalProperties"] is False
assert schema["properties"]["schema_version"]["const"] == SCHEMA_VERSION
for name in (
    "project_config",
    "installation_state",
    "authorization_policy",
    "release_manifest",
    "evidence_manifest",
    "compatibility",
    "operator_contract",
):
    assert name in schema["$defs"], name
    assert schema["$defs"][name]["additionalProperties"] is False

reference = load(REFERENCE_PATH)
validate_bundle(reference)

# The second release-gated reference profile is also internally valid without
# exposing a public console. Browser execution, when enabled, is private-relay only.
private = copy.deepcopy(reference)
private["project_config"]["profile"] = "private-no-public-console"
private["project_config"]["console"] = {
    "mode": "private-none",
    "data_classification": "private",
    "public_opt_in": False,
}
private["project_config"]["browser"] = {
    "enabled": True,
    "transport": "private-relay",
}
private["project_config"]["required_secret_refs"] = [
    "RELAY_ENDPOINT",
    "BROWSER_PROFILE_KEY",
]
private["release_manifest"]["supported_profile"] = "private-no-public-console"
validate_bundle(private)

# Unknown fields fail closed.
unknown = copy.deepcopy(reference)
unknown["project_config"]["legacy_issue_number"] = 16
must_fail(unknown, "unknown fields")

negative_fixtures = load(NEGATIVE_PATH)
names = set()
for fixture in negative_fixtures:
    assert set(fixture) == {"name", "contains", "ops"}, fixture
    assert fixture["name"] not in names, fixture["name"]
    names.add(fixture["name"])
    must_fail(mutate(reference, fixture["ops"]), fixture["contains"])

expected_negative_names = {
    "fixed-issue-role-key",
    "unmapped-state-effect-principal",
    "mutable-action-reference",
    "private-project-public-pages",
    "public-issue-browser-transport",
    "incompatible-downgrade",
    "missing-installation-id",
    "duplicate-role-binding",
    "release-component-missing-digest",
    "evidence-artifact-missing-digest",
    "credential-like-secret-material",
}
assert expected_negative_names <= names

print("Productization Phase-0 contract regressions passed")
