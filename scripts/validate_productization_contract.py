#!/usr/bin/env python3
"""Offline validator for the Productization v1 Phase-0 contract bundle.

This validator intentionally uses only the Python standard library and never
contacts GitHub or any other network service. It complements the normative JSON
Schema by enforcing cross-field safety invariants that JSON Schema alone does
not express conveniently.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCHEMA_VERSION = "ai-bb-productization:v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
ACTION_RE = re.compile(r"^[^@]+@[0-9a-f]{40}$")
REPO_REF_RE = re.compile(r"^[^/]+/[^@]+@[0-9a-f]{40}$")
ROLE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
INSTALLATION_RE = re.compile(r"^aibb-[a-z0-9][a-z0-9-]{7,63}$")
SECRET_REF_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,127}$")
TASK_SCOPE_RE = re.compile(r"^(?:\*|role:[a-z][a-z0-9_]*|workstream:[a-z0-9][a-z0-9._/-]{0,127})$")

LIFECYCLE_STATES = {
    "PLANNED", "PREFLIGHT", "INSTALLING", "ACTIVE", "UPGRADING",
    "DEGRADED", "RECOVERING", "DECOMMISSIONED",
}
CAPABILITIES = {
    "claim", "heartbeat", "release", "progress", "handoff", "result",
    "review", "integrate", "deploy",
}
OPERATOR_STATES = {
    "healthy_idle", "work_in_progress", "review_needed",
    "human_required", "recovery_needed", "completed_accepted",
}
REQUIRED_HUMAN_FIELDS = {
    "reason", "action", "surface", "urgency", "safety_privacy",
    "evidence_link", "resolver", "defer_cancel", "expiry_staleness",
    "resume_path",
}
REQUIRED_FRESHNESS_FIELDS = {
    "source_release", "measured_at", "freshness", "scope", "acceptance_status",
}
REQUIRED_HUMAN_GATES = {
    "production", "destructive", "account", "permission", "security_sensitive",
}
REQUIRED_ACCESSIBILITY = {
    "keyboard", "screen_reader", "color_independent", "visible_focus_errors",
    "long_text", "narrow_mobile_priority",
}
REQUIRED_EVIDENCE_CLASSES = {
    "acceptance_results", "sanitized_e2e_product_ux", "security_privacy_sanitizer",
    "permission_ruleset_environment", "provenance_sbom", "audit_logs_findings",
    "emergency_disable_revoke",
}

SECRET_KEY_NAMES = {
    "secret", "secret_value", "password", "token", "access_token",
    "refresh_token", "private_key", "api_key", "credential",
    "credentials", "authorization", "authorization_header",
}
SECRET_PREFIXES = (
    "ghp_", "github_pat_", "sk-", "xoxb-", "xoxp-",
    "-----BEGIN PRIVATE KEY-----", "-----BEGIN RSA PRIVATE KEY-----",
)


class ContractError(ValueError):
    pass


def fail(path: str, message: str) -> None:
    raise ContractError(f"{path}: {message}")


def require_type(value, typ, path: str):
    if not isinstance(value, typ):
        fail(path, f"expected {typ.__name__}")
    return value


def strict_keys(obj: dict, required: set[str], allowed: set[str], path: str) -> None:
    require_type(obj, dict, path)
    missing = sorted(required - set(obj))
    unknown = sorted(set(obj) - allowed)
    if missing:
        fail(path, f"missing required fields {missing}")
    if unknown:
        fail(path, f"unknown fields {unknown}")


def require_nonempty_str(value, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        fail(path, "expected non-empty string")
    return value


def require_bool(value, expected: bool | None, path: str) -> bool:
    if not isinstance(value, bool):
        fail(path, "expected boolean")
    if expected is not None and value is not expected:
        fail(path, f"must be {expected}")
    return value


def require_int(value, path: str, minimum: int = 1) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        fail(path, f"expected integer >= {minimum}")
    return value


def require_list(value, path: str) -> list:
    if not isinstance(value, list):
        fail(path, "expected array")
    return value


def unique_strings(values: list, path: str) -> list[str]:
    if any(not isinstance(x, str) for x in values):
        fail(path, "expected string items")
    if len(values) != len(set(values)):
        fail(path, "duplicate items are not allowed")
    return values


def reject_secret_material(value, path="$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower()
            if normalized in SECRET_KEY_NAMES or normalized.endswith("_secret_value"):
                fail(f"{path}.{key}", "secret values are forbidden; persist a reference/name only")
            reject_secret_material(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_secret_material(child, f"{path}[{index}]")
    elif isinstance(value, str):
        stripped = value.strip()
        if any(stripped.startswith(prefix) for prefix in SECRET_PREFIXES):
            fail(path, "credential-like secret material is forbidden")


def validate_project_config(obj: dict) -> None:
    path = "$.project_config"
    strict_keys(
        obj,
        {"profile", "topology", "console", "browser", "required_secret_refs"},
        {"profile", "topology", "console", "browser", "required_secret_refs"},
        path,
    )
    profile = obj["profile"]
    if profile not in {"public-pages", "private-no-public-console"}:
        fail(f"{path}.profile", "unsupported profile")

    topology = require_type(obj["topology"], dict, f"{path}.topology")
    strict_keys(
        topology,
        {"platform", "repository_mode", "managed_pr_scope", "actions_required"},
        {"platform", "repository_mode", "managed_pr_scope", "actions_required"},
        f"{path}.topology",
    )
    if topology["platform"] != "github.com":
        fail(f"{path}.topology.platform", "v1 supports github.com only")
    if topology["repository_mode"] != "single-repo":
        fail(f"{path}.topology.repository_mode", "v1 supports single-repo only")
    if topology["managed_pr_scope"] != "local":
        fail(f"{path}.topology.managed_pr_scope", "managed PRs must be local")
    require_bool(topology["actions_required"], True, f"{path}.topology.actions_required")

    console = require_type(obj["console"], dict, f"{path}.console")
    strict_keys(
        console,
        {"mode", "data_classification", "public_opt_in"},
        {"mode", "data_classification", "public_opt_in"},
        f"{path}.console",
    )
    if console["mode"] not in {"public-pages", "private-none"}:
        fail(f"{path}.console.mode", "unsupported console mode")
    if console["data_classification"] not in {"public", "private"}:
        fail(f"{path}.console.data_classification", "unsupported data classification")
    require_bool(console["public_opt_in"], None, f"{path}.console.public_opt_in")
    if console["data_classification"] == "private":
        if console["mode"] == "public-pages" or console["public_opt_in"]:
            fail(f"{path}.console", "private classification cannot enable public Pages")
    if profile == "public-pages":
        if console != {"mode": "public-pages", "data_classification": "public", "public_opt_in": True}:
            fail(f"{path}.console", "public-pages profile requires explicit public opt-in")
    if profile == "private-no-public-console":
        if console["data_classification"] != "private" or console["mode"] != "private-none":
            fail(f"{path}.console", "private profile requires private-none console")

    browser = require_type(obj["browser"], dict, f"{path}.browser")
    strict_keys(browser, {"enabled", "transport"}, {"enabled", "transport"}, f"{path}.browser")
    require_bool(browser["enabled"], None, f"{path}.browser.enabled")
    if browser["transport"] not in {"disabled", "private-relay"}:
        fail(f"{path}.browser.transport", "public Issue browser transport is unsupported")
    if browser["enabled"] and browser["transport"] != "private-relay":
        fail(f"{path}.browser.transport", "enabled browser execution requires private-relay")
    if not browser["enabled"] and browser["transport"] != "disabled":
        fail(f"{path}.browser.transport", "disabled browser execution must use disabled transport")

    refs = unique_strings(require_list(obj["required_secret_refs"], f"{path}.required_secret_refs"), f"{path}.required_secret_refs")
    for i, ref in enumerate(refs):
        if not SECRET_REF_RE.match(ref):
            fail(f"{path}.required_secret_refs[{i}]", "secret references must be uppercase names only")


def validate_installation_state(obj: dict) -> None:
    path = "$.installation_state"
    strict_keys(
        obj,
        {"installation_id", "repository", "roles", "resources", "versions", "lifecycle_state"},
        {"installation_id", "repository", "roles", "resources", "versions", "lifecycle_state"},
        path,
    )
    if not isinstance(obj["installation_id"], str) or not INSTALLATION_RE.match(obj["installation_id"]):
        fail(f"{path}.installation_id", "invalid durable installation_id")

    repo = require_type(obj["repository"], dict, f"{path}.repository")
    strict_keys(
        repo,
        {"owner", "name", "repository_id", "default_branch", "integration_branch"},
        {"owner", "name", "repository_id", "default_branch", "integration_branch"},
        f"{path}.repository",
    )
    require_nonempty_str(repo["owner"], f"{path}.repository.owner")
    require_nonempty_str(repo["name"], f"{path}.repository.name")
    require_int(repo["repository_id"], f"{path}.repository.repository_id")
    require_nonempty_str(repo["default_branch"], f"{path}.repository.default_branch")
    require_nonempty_str(repo["integration_branch"], f"{path}.repository.integration_branch")

    roles = require_type(obj["roles"], dict, f"{path}.roles")
    if not roles:
        fail(f"{path}.roles", "at least manager and review_manager roles are required")
    for role, issue_number in roles.items():
        if not ROLE_RE.match(role):
            fail(f"{path}.roles.{role}", "role identity must be symbolic, not a fixed Issue-number key")
        require_int(issue_number, f"{path}.roles.{role}")
    for required in ("manager", "review_manager"):
        if required not in roles:
            fail(f"{path}.roles", f"missing required symbolic role {required}")
    values = list(roles.values())
    if len(values) != len(set(values)):
        fail(f"{path}.roles", "duplicate Issue binding across symbolic roles")

    resources = require_list(obj["resources"], f"{path}.resources")
    if not resources:
        fail(f"{path}.resources", "at least one managed resource is required")
    seen_resources = set()
    for i, resource in enumerate(resources):
        rp = f"{path}.resources[{i}]"
        strict_keys(resource, {"type", "id", "managed", "owner_marker"}, {"type", "id", "managed", "owner_marker"}, rp)
        rtype = require_nonempty_str(resource["type"], f"{rp}.type")
        rid = require_nonempty_str(resource["id"], f"{rp}.id")
        require_bool(resource["managed"], None, f"{rp}.managed")
        require_nonempty_str(resource["owner_marker"], f"{rp}.owner_marker")
        key = (rtype, rid)
        if key in seen_resources:
            fail(rp, "duplicate managed resource identity")
        seen_resources.add(key)

    versions = require_type(obj["versions"], dict, f"{path}.versions")
    strict_keys(versions, {"core", "workflow", "config_schema"}, {"core", "workflow", "config_schema"}, f"{path}.versions")
    require_nonempty_str(versions["core"], f"{path}.versions.core")
    require_nonempty_str(versions["workflow"], f"{path}.versions.workflow")
    if versions["config_schema"] != SCHEMA_VERSION:
        fail(f"{path}.versions.config_schema", f"must be {SCHEMA_VERSION}")

    if obj["lifecycle_state"] not in LIFECYCLE_STATES:
        fail(f"{path}.lifecycle_state", "invalid lifecycle state")


def validate_authorization_policy(obj: dict) -> None:
    path = "$.authorization_policy"
    strict_keys(
        obj,
        {"agent_id_is_authentication", "principals", "state_effect_grants"},
        {"agent_id_is_authentication", "principals", "state_effect_grants"},
        path,
    )
    require_bool(obj["agent_id_is_authentication"], False, f"{path}.agent_id_is_authentication")

    principals = require_list(obj["principals"], f"{path}.principals")
    principal_caps = {}
    for i, principal in enumerate(principals):
        pp = f"{path}.principals[{i}]"
        strict_keys(principal, {"principal_id", "github_kind", "github_id", "capabilities"}, {"principal_id", "github_kind", "github_id", "capabilities"}, pp)
        principal_id = require_nonempty_str(principal["principal_id"], f"{pp}.principal_id")
        if not re.match(r"^[a-z][a-z0-9._/-]{2,127}$", principal_id):
            fail(f"{pp}.principal_id", "invalid principal_id")
        if principal_id in principal_caps:
            fail(f"{pp}.principal_id", "duplicate principal_id")
        if principal["github_kind"] not in {"app", "user", "team"}:
            fail(f"{pp}.github_kind", "unsupported GitHub principal kind")
        require_int(principal["github_id"], f"{pp}.github_id")
        caps = unique_strings(require_list(principal["capabilities"], f"{pp}.capabilities"), f"{pp}.capabilities")
        unknown_caps = sorted(set(caps) - CAPABILITIES)
        if unknown_caps:
            fail(f"{pp}.capabilities", f"unknown capabilities {unknown_caps}")
        principal_caps[principal_id] = set(caps)

    grants = require_list(obj["state_effect_grants"], f"{path}.state_effect_grants")
    if not grants:
        fail(f"{path}.state_effect_grants", "at least one state-effect grant is required")
    seen = set()
    for i, grant in enumerate(grants):
        gp = f"{path}.state_effect_grants[{i}]"
        strict_keys(grant, {"principal_id", "capability", "task_scope"}, {"principal_id", "capability", "task_scope"}, gp)
        principal_id = require_nonempty_str(grant["principal_id"], f"{gp}.principal_id")
        if principal_id not in principal_caps:
            fail(f"{gp}.principal_id", f"unmapped principal cannot affect state: {principal_id}")
        capability = require_nonempty_str(grant["capability"], f"{gp}.capability")
        if capability not in CAPABILITIES:
            fail(f"{gp}.capability", f"unknown capability {capability}")
        if capability not in principal_caps[principal_id]:
            fail(f"{gp}.capability", f"principal lacks capability {capability}")
        task_scope = require_nonempty_str(grant["task_scope"], f"{gp}.task_scope")
        if not TASK_SCOPE_RE.match(task_scope):
            fail(f"{gp}.task_scope", "task scope must be symbolic (*, role:<name>, or workstream:<key>)")
        key = (principal_id, capability, task_scope)
        if key in seen:
            fail(gp, "duplicate state-effect grant")
        seen.add(key)


def validate_release_manifest(obj: dict) -> None:
    path = "$.release_manifest"
    strict_keys(
        obj,
        {"release_id", "supported_profile", "components", "actions", "sbom_digest"},
        {"release_id", "supported_profile", "components", "actions", "sbom_digest"},
        path,
    )
    require_nonempty_str(obj["release_id"], f"{path}.release_id")
    if obj["supported_profile"] not in {"public-pages", "private-no-public-console"}:
        fail(f"{path}.supported_profile", "unsupported release profile")
    components = require_type(obj["components"], dict, f"{path}.components")
    if len(components) < 2:
        fail(f"{path}.components", "release must identify at least core and workflows components")
    missing_required_components = [name for name in ("core", "workflows") if name not in components]
    if missing_required_components:
        fail(f"{path}.components", "must include core and workflows components")
    for name, component in components.items():
        cp = f"{path}.components.{name}"
        if not ROLE_RE.match(name):
            fail(cp, "component key must be symbolic")
        strict_keys(component, {"repository", "commit_sha", "digest"}, {"repository", "commit_sha", "digest"}, cp)
        repository = require_nonempty_str(component["repository"], f"{cp}.repository")
        if repository.count("/") != 1:
            fail(f"{cp}.repository", "repository must be owner/name")
        if not isinstance(component["commit_sha"], str) or not SHA_RE.match(component["commit_sha"]):
            fail(f"{cp}.commit_sha", "immutable 40-hex commit SHA required")
        if not isinstance(component["digest"], str) or not DIGEST_RE.match(component["digest"]):
            fail(f"{cp}.digest", "sha256 digest required")
    actions = require_list(obj["actions"], f"{path}.actions")
    for i, action in enumerate(actions):
        ap = f"{path}.actions[{i}]"
        strict_keys(action, {"uses"}, {"uses"}, ap)
        if not isinstance(action["uses"], str) or not ACTION_RE.match(action["uses"]):
            fail(f"{ap}.uses", "executable Action must be pinned to immutable 40-hex commit SHA")
    if not isinstance(obj["sbom_digest"], str) or not DIGEST_RE.match(obj["sbom_digest"]):
        fail(f"{path}.sbom_digest", "sha256 SBOM digest required")


def validate_evidence_manifest(obj: dict) -> None:
    path = "$.evidence_manifest"
    strict_keys(
        obj,
        {"release_manifest_digest", "reference_commits", "artifacts", "actions_retention_independent"},
        {"release_manifest_digest", "reference_commits", "artifacts", "actions_retention_independent"},
        path,
    )
    if not isinstance(obj["release_manifest_digest"], str) or not DIGEST_RE.match(obj["release_manifest_digest"]):
        fail(f"{path}.release_manifest_digest", "sha256 release-manifest digest required")
    refs = unique_strings(require_list(obj["reference_commits"], f"{path}.reference_commits"), f"{path}.reference_commits")
    if not refs:
        fail(f"{path}.reference_commits", "at least one exact reference commit required")
    for i, ref in enumerate(refs):
        if not REPO_REF_RE.match(ref):
            fail(f"{path}.reference_commits[{i}]", "must be owner/repo@40hex")
    artifacts = require_list(obj["artifacts"], f"{path}.artifacts")
    if not artifacts:
        fail(f"{path}.artifacts", "durable release evidence is required")
    seen_classes = set()
    for i, artifact in enumerate(artifacts):
        ap = f"{path}.artifacts[{i}]"
        strict_keys(
            artifact,
            {"class", "name", "digest", "durable", "provenance_ref"},
            {"class", "name", "digest", "durable", "provenance_ref"},
            ap,
        )
        evidence_class = require_nonempty_str(artifact["class"], f"{ap}.class")
        if evidence_class not in REQUIRED_EVIDENCE_CLASSES:
            fail(f"{ap}.class", f"unsupported evidence class {evidence_class}")
        seen_classes.add(evidence_class)
        require_nonempty_str(artifact["name"], f"{ap}.name")
        if not isinstance(artifact["digest"], str) or not DIGEST_RE.match(artifact["digest"]):
            fail(f"{ap}.digest", "sha256 evidence digest required")
        require_bool(artifact["durable"], True, f"{ap}.durable")
        require_nonempty_str(artifact["provenance_ref"], f"{ap}.provenance_ref")
    missing_classes = sorted(REQUIRED_EVIDENCE_CLASSES - seen_classes)
    if missing_classes:
        fail(f"{path}.artifacts", f"missing required evidence classes {missing_classes}")
    require_bool(obj["actions_retention_independent"], True, f"{path}.actions_retention_independent")


def validate_compatibility(obj: dict) -> None:
    path = "$.compatibility"
    strict_keys(
        obj,
        {"current_version", "supported_upgrade_from", "canonical_history_rewrite", "downgrade_policy", "persisted_schema_versions", "migrations"},
        {"current_version", "supported_upgrade_from", "canonical_history_rewrite", "downgrade_policy", "persisted_schema_versions", "migrations", "requested_downgrade"},
        path,
    )
    require_nonempty_str(obj["current_version"], f"{path}.current_version")
    unique_strings(require_list(obj["supported_upgrade_from"], f"{path}.supported_upgrade_from"), f"{path}.supported_upgrade_from")
    require_bool(obj["canonical_history_rewrite"], False, f"{path}.canonical_history_rewrite")
    if obj["downgrade_policy"] != "fail-closed-if-persisted-schema-unsupported":
        fail(f"{path}.downgrade_policy", "downgrade must fail closed on incompatible persisted schema")
    persisted = unique_strings(require_list(obj["persisted_schema_versions"], f"{path}.persisted_schema_versions"), f"{path}.persisted_schema_versions")
    if not persisted:
        fail(f"{path}.persisted_schema_versions", "at least one persisted schema version required")

    migrations = require_list(obj["migrations"], f"{path}.migrations")
    for i, migration in enumerate(migrations):
        mp = f"{path}.migrations[{i}]"
        strict_keys(migration, {"from", "to", "persisted_schema_compatible"}, {"from", "to", "persisted_schema_compatible"}, mp)
        require_nonempty_str(migration["from"], f"{mp}.from")
        require_nonempty_str(migration["to"], f"{mp}.to")
        require_bool(migration["persisted_schema_compatible"], None, f"{mp}.persisted_schema_compatible")

    requested = obj.get("requested_downgrade")
    if requested is not None:
        rp = f"{path}.requested_downgrade"
        strict_keys(requested, {"target_version", "target_supported_persisted_schema_versions"}, {"target_version", "target_supported_persisted_schema_versions"}, rp)
        require_nonempty_str(requested["target_version"], f"{rp}.target_version")
        supported = unique_strings(
            require_list(requested["target_supported_persisted_schema_versions"], f"{rp}.target_supported_persisted_schema_versions"),
            f"{rp}.target_supported_persisted_schema_versions",
        )
        unsupported = sorted(set(persisted) - set(supported))
        if unsupported:
            fail(rp, f"incompatible downgrade rejected; persisted schemas unsupported by target: {unsupported}")


def validate_operator_contract(obj: dict) -> None:
    path = "$.operator_contract"
    strict_keys(
        obj,
        {"states", "human_required_fields", "evidence_freshness_fields", "autonomy_policy", "accessibility", "supported_language"},
        {"states", "human_required_fields", "evidence_freshness_fields", "autonomy_policy", "accessibility", "supported_language"},
        path,
    )
    states = set(unique_strings(require_list(obj["states"], f"{path}.states"), f"{path}.states"))
    if states != OPERATOR_STATES:
        fail(f"{path}.states", f"must contain exactly {sorted(OPERATOR_STATES)}")

    human_fields = set(unique_strings(require_list(obj["human_required_fields"], f"{path}.human_required_fields"), f"{path}.human_required_fields"))
    missing_human = sorted(REQUIRED_HUMAN_FIELDS - human_fields)
    if missing_human:
        fail(f"{path}.human_required_fields", f"missing required fields {missing_human}")

    freshness = set(unique_strings(require_list(obj["evidence_freshness_fields"], f"{path}.evidence_freshness_fields"), f"{path}.evidence_freshness_fields"))
    missing_freshness = sorted(REQUIRED_FRESHNESS_FIELDS - freshness)
    if missing_freshness:
        fail(f"{path}.evidence_freshness_fields", f"missing required freshness fields {missing_freshness}")

    autonomy = require_type(obj["autonomy_policy"], dict, f"{path}.autonomy_policy")
    strict_keys(autonomy, {"human_gated", "halt_conditions"}, {"human_gated", "halt_conditions"}, f"{path}.autonomy_policy")
    human_gated = set(unique_strings(require_list(autonomy["human_gated"], f"{path}.autonomy_policy.human_gated"), f"{path}.autonomy_policy.human_gated"))
    missing_gates = sorted(REQUIRED_HUMAN_GATES - human_gated)
    if missing_gates:
        fail(f"{path}.autonomy_policy.human_gated", f"missing mandatory human gates {missing_gates}")
    if not require_list(autonomy["halt_conditions"], f"{path}.autonomy_policy.halt_conditions"):
        fail(f"{path}.autonomy_policy.halt_conditions", "at least one halt condition required")

    accessibility = require_type(obj["accessibility"], dict, f"{path}.accessibility")
    strict_keys(accessibility, REQUIRED_ACCESSIBILITY, REQUIRED_ACCESSIBILITY, f"{path}.accessibility")
    for key in REQUIRED_ACCESSIBILITY:
        require_bool(accessibility[key], True, f"{path}.accessibility.{key}")

    require_nonempty_str(obj["supported_language"], f"{path}.supported_language")


def validate_bundle(record: dict) -> None:
    strict_keys(
        record,
        {
            "schema_version", "project_config", "installation_state",
            "authorization_policy", "release_manifest", "evidence_manifest",
            "compatibility", "operator_contract",
        },
        {
            "schema_version", "project_config", "installation_state",
            "authorization_policy", "release_manifest", "evidence_manifest",
            "compatibility", "operator_contract",
        },
        "$",
    )
    if record["schema_version"] != SCHEMA_VERSION:
        fail("$.schema_version", f"must be {SCHEMA_VERSION}")

    reject_secret_material(record)
    validate_project_config(record["project_config"])
    validate_installation_state(record["installation_state"])
    validate_authorization_policy(record["authorization_policy"])
    validate_release_manifest(record["release_manifest"])
    validate_evidence_manifest(record["evidence_manifest"])
    validate_compatibility(record["compatibility"])
    validate_operator_contract(record["operator_contract"])

    if record["project_config"]["profile"] != record["release_manifest"]["supported_profile"]:
        fail("$", "project profile and release supported_profile must match")


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"{path}: unable to load JSON: {exc}") from exc


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} BUNDLE.json [BUNDLE.json ...]", file=sys.stderr)
        return 2
    try:
        for name in argv[1:]:
            path = Path(name)
            record = load_json(path)
            validate_bundle(record)
            print(f"{path}: productization Phase-0 contract valid")
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
