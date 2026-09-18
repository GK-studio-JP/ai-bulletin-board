#!/usr/bin/env python3
"""Build a sanitized read-only Pages projection from GitHub Issues/comments.

GitHub remains authoritative. This builder emits only derived, public-to-repo
coordination fields and fails closed when replay cannot be completed safely.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from validate_product_ux_contract import validate_records

MARKER = "<!-- ai-bb:v1 -->"
LEASE_SECONDS = 900
EVENT_TYPES = {"CLAIM", "HEARTBEAT", "RELEASE", "PROGRESS", "HANDOFF", "RESULT", "REVIEW"}
REQUIRED = {"type", "agent_id", "task", "idempotency_key", "summary", "next_action", "artifacts"}
SAFE_ARTIFACT = re.compile(r"^(?:Issue:#?\d+|PR:#?\d+(?:@[0-9a-f]{7,40})?|commit:[0-9a-f]{7,40}|merge:[0-9a-f]{7,40}|path:[A-Za-z0-9._/\-]+|[A-Za-z0-9._/\-]+)$")

SAFE_FIELDS = ("task", "title", "state", "agent", "last_event", "last_activity_at", "lease_expires_at", "lease_status", "review_needed", "current_head", "next_action", "artifacts")
CREDENTIAL_LIKE = re.compile(r"(?i)(?:authorization\s*:|bearer\s+|token\s*=|api[_-]?key\s*=|password\s*=|cookie\s*:|private[_ -]?key)")


def safe_text(value, limit=280):
    """Normalize bounded display text and fail closed on credential-like content."""
    text = " ".join(str(value or "").split())
    if CREDENTIAL_LIKE.search(text):
        return "[redacted]"
    return text[:limit]


def safe_reference(value, limit=240):
    """Allow only bounded non-URL evidence/reference tokens into public projection."""
    text = safe_text(value, limit)
    if (
        not text
        or text == "[redacted]"
        or "://" in text
        or "?" in text
        or "&" in text
        or "=" in text
        or SAFE_REFERENCE.fullmatch(text) is None
    ):
        raise ValueError("unsafe projection reference")
    return text


def safe_text_list(values, *, limit=240):
    if not isinstance(values, list):
        raise ValueError("projection list must be a list")
    return [safe_text(value, limit) for value in values]


def api(url: str):
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ai-bb-pages-builder"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return json.load(r), r.headers


def paged(url: str):
    out = []
    page = 1
    while True:
        sep = "&" if "?" in url else "?"
        batch, _ = api(f"{url}{sep}per_page=100&page={page}")
        if not isinstance(batch, list):
            raise RuntimeError("unexpected GitHub response")
        out.extend(batch)
        if len(batch) < 100:
            return out
        page += 1


def payload(body: str):
    if MARKER not in body:
        return None
    tail = body.split(MARKER, 1)[1]
    m = re.search(r"```json\s*(\{.*?\})\s*```", tail, re.S | re.I)
    if not m:
        m = re.search(r"(\{.*\})", tail, re.S)
    if not m:
        return None
    try:
        value = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def canonical(p, issue_number):
    return (
        REQUIRED <= p.keys()
        and p.get("type") in EVENT_TYPES
        and p.get("task") == f"#{issue_number}"
        and isinstance(p.get("agent_id"), str) and bool(p["agent_id"].strip())
        and isinstance(p.get("idempotency_key"), str) and bool(p["idempotency_key"].strip())
        and isinstance(p.get("summary"), str)
        and isinstance(p.get("artifacts"), list)
        and all(isinstance(x, str) for x in p["artifacts"])
        and (p.get("next_action") is None or isinstance(p.get("next_action"), str))
        and (p.get("type") not in {"CLAIM", "HEARTBEAT"} or bool(p.get("next_action")))
        and (p.get("type") != "RESULT" or p.get("next_action") is None)
    )


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def replay(issue, comments, now):
    number = issue["number"]
    events = []
    # Check edit evidence for every marker-bearing comment before parsing.
    # An edit can make a formerly canonical event malformed/noncanonical; because
    # this API view cannot recover its creation-time body, canonical v1 fails closed.
    for c in comments:
        body = c.get("body") or ""
        if MARKER not in body:
            continue
        created = parse_time(c["created_at"])
        updated = c.get("updated_at")
        if updated and parse_time(updated) != created:
            return "history_unsafe", None, None
        p = payload(body)
        if p is not None and canonical(p, number):
            events.append((created, int(c["id"]), p, c))
    events.sort(key=lambda x: (x[0], x[1]))

    seen = {}
    owner = None
    expiry = None
    last_lease_expiry = None
    completed = False
    last = None
    current_head = ""
    reviewed_heads = set()
    head_authors = {}
    seen_heads = set()
    for created, cid, p, c in events:
        key = p["idempotency_key"]
        normalized = json.dumps(p, sort_keys=True, separators=(",", ":"))
        if key in seen:
            if seen[key] != normalized:
                continue
            continue
        seen[key] = normalized
        last = (created, cid, p, c)
        typ = p["type"]
        # Lease expiry is a derived event-boundary fact. Clear stale ownership
        # before evaluating any ownership-sensitive event or projection authorship.
        if owner is not None and expiry is not None and created >= expiry:
            owner = None
            expiry = None
        live = owner is not None and expiry is not None
        heads = [x for x in p.get("artifacts", []) if re.fullmatch(r"PR:#?\d+@[0-9a-f]{7,40}", x)]
        if heads:
            if typ == "REVIEW":
                for head in heads:
                    author = head_authors.get(head)
                    if author and p["agent_id"] != author:
                        reviewed_heads.add(head)
            elif typ in {"PROGRESS", "HANDOFF", "RESULT"} and live and p["agent_id"] == owner:
                for head in heads:
                    if head in seen_heads:
                        continue
                    seen_heads.add(head)
                    current_head = head
                    head_authors.setdefault(head, p["agent_id"])
        if typ == "CLAIM":
            if not live and not completed:
                owner = p["agent_id"]
                expiry = created + timedelta(seconds=LEASE_SECONDS)
                last_lease_expiry = expiry
        elif typ == "HEARTBEAT":
            if live and p["agent_id"] == owner:
                expiry = created + timedelta(seconds=LEASE_SECONDS)
                last_lease_expiry = expiry
        elif typ == "RELEASE":
            if live and p["agent_id"] == owner:
                owner = expiry = None
                last_lease_expiry = None
        elif typ == "RESULT":
            if live and p["agent_id"] == owner:
                completed = True
                owner = expiry = None
                last_lease_expiry = None
    if completed:
        state = "completed"
    elif owner is not None and expiry is not None and now < expiry:
        state = "claimed"
    else:
        state = "open"
        owner = None
    if last is not None:
        lease_status = ""
        display_expiry = expiry if owner is not None and expiry is not None else last_lease_expiry
        if display_expiry is not None:
            if owner is not None and expiry is not None and now < expiry:
                lease_status = "expiring" if expiry - now <= timedelta(seconds=300) else "active"
            elif now >= display_expiry:
                lease_status = "stale"
        meta = {
            "last_activity_at": last[0].astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "lease_expires_at": display_expiry.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if display_expiry is not None else "",
            "lease_status": lease_status,
            "review_needed": bool(current_head and current_head not in reviewed_heads),
            "current_head": current_head,
        }
        last = (*last, meta)
    return state, owner, last


def safe_artifacts(items):
    return [x for x in items if SAFE_ARTIFACT.fullmatch(x)][:8]

def project_row(issue, state, owner, last):
    """Explicit whitelist boundary between GitHub payloads and Pages JSON."""
    p = last[2] if last else {}
    meta = last[4] if last and len(last) > 4 else {}
    row = {
        "task": f"#{issue['number']}",
        "title": safe_text(issue.get("title") or "", 180),
        "state": state,
        "agent": safe_text(owner or "", 160),
        "last_event": p.get("type", "") if p.get("type") in EVENT_TYPES else "",
        "last_activity_at": meta.get("last_activity_at", ""),
        "lease_expires_at": meta.get("lease_expires_at", ""),
        "lease_status": meta.get("lease_status", "") if meta.get("lease_status", "") in {"", "active", "expiring", "stale"} else "",
        "review_needed": bool(meta.get("review_needed", False)),
        "current_head": meta.get("current_head", "") if SAFE_ARTIFACT.fullmatch(meta.get("current_head", "")) else "",
        "next_action": safe_text(p.get("next_action") or ""),
        "artifacts": safe_artifacts(p.get("artifacts", [])),
    }
    return {key: row[key] for key in SAFE_FIELDS}


def _bool(value, name):
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be boolean")
    return value


def _nonnegative_int(value, name):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be non-negative integer")
    return value


def project_autonomy(snapshot, repository):
    """Whitelisted projection of the already-derived read-only autonomy snapshot."""
    if not isinstance(snapshot, dict) or snapshot.get("schema") != "ai-bb-autonomy:v1":
        raise ValueError("unsupported autonomy snapshot")
    if SAFE_REPOSITORY.fullmatch(repository or "") is None:
        raise ValueError("invalid repository identity")

    raw_health = snapshot.get("health")
    if not isinstance(raw_health, dict):
        raise ValueError("autonomy health must be an object")
    main_status = raw_health.get("main_status")
    if main_status not in MAIN_STATUSES:
        raise ValueError("invalid main_status")
    health = {"main_status": main_status}
    for key in AUTONOMY_HEALTH_FIELDS[1:]:
        health[key] = _bool(raw_health.get(key), f"health.{key}")

    queue = []
    raw_queue = snapshot.get("queue")
    if not isinstance(raw_queue, list):
        raise ValueError("autonomy queue must be a list")
    for raw in raw_queue:
        if not isinstance(raw, dict):
            raise ValueError("autonomy queue row must be an object")
        task = str(raw.get("task") or "")
        if re.fullmatch(r"#\d+", task) is None:
            raise ValueError("invalid autonomy task")
        state = raw.get("state")
        if state not in TASK_STATES:
            raise ValueError("invalid autonomy state")
        lease_status = raw.get("lease_status") or ""
        if lease_status not in LEASE_STATES:
            raise ValueError("invalid autonomy lease_status")
        current_head = raw.get("current_head") or ""
        if current_head and EXACT_HEAD.fullmatch(current_head) is None:
            raise ValueError("invalid autonomy current_head")
        next_class = raw.get("next_class")
        if next_class not in NEXT_CLASSES:
            raise ValueError("invalid autonomy next_class")
        row = {
            "task": task,
            "state": state,
            "agent": safe_text(raw.get("agent") or "", 160),
            "lease_status": lease_status,
            "review_needed": _bool(raw.get("review_needed"), "queue.review_needed"),
            "current_head": current_head,
            "next_action": safe_text(raw.get("next_action") or ""),
            "next_class": next_class,
            "waiting_reason": safe_text(raw.get("waiting_reason") or ""),
        }
        queue.append({key: row[key] for key in AUTONOMY_QUEUE_FIELDS})

    deduped = {}
    raw_reviews = snapshot.get("review_queue")
    if not isinstance(raw_reviews, list):
        raise ValueError("autonomy review_queue must be a list")
    for raw in raw_reviews:
        if not isinstance(raw, dict):
            raise ValueError("review queue row must be an object")
        pr = _nonnegative_int(raw.get("pr"), "review.pr")
        if pr <= 0:
            raise ValueError("review.pr must be positive")
        head = str(raw.get("head") or "")
        match = EXACT_HEAD.fullmatch(head)
        if match is None or int(match.group(1)) != pr:
            raise ValueError("review head must match pr")
        review_needed = _bool(raw.get("review_needed"), "review.review_needed")
        review_count = _nonnegative_int(raw.get("review_count"), "review.review_count")
        stale_count = _nonnegative_int(raw.get("stale_review_count"), "review.stale_review_count")
        key = (repository, pr, head)
        current = {
            "repository": repository,
            "pr": pr,
            "head": head,
            "review_needed": review_needed,
            "review_count": review_count,
            "stale_review_count": stale_count,
        }
        previous = deduped.get(key)
        if previous is None:
            deduped[key] = current
            continue
        needs_review = previous["review_needed"] or review_needed
        previous["review_needed"] = needs_review
        previous["review_count"] = (
            min(previous["review_count"], review_count)
            if needs_review
            else max(previous["review_count"], review_count)
        )
        previous["stale_review_count"] = max(previous["stale_review_count"], stale_count)

    review_queue = [deduped[key] for key in sorted(deduped, key=lambda item: (item[1], item[2]))]
    human_required = [
        {
            "task": row["task"],
            "next_action": row["next_action"],
            "waiting_reason": row["waiting_reason"],
        }
        for row in queue
        if row["next_class"] == "idle/human-required"
        and row["waiting_reason"] == "human-required decision"
    ]
    return {
        "health": health,
        "queue": queue,
        "review_queue": review_queue,
        "human_required": human_required,
    }


def _optional_reference(value):
    if value in {None, ""}:
        return None
    return safe_reference(value)


def _optional_text(value, limit=280):
    if value is None:
        return None
    return safe_text(value, limit)


def _product_proposal(record):
    return {
        "proposal_id": safe_reference(record["proposal_id"]),
        "lifecycle": record["lifecycle"],
        "problem": safe_text(record["problem"], 400),
        "evidence_refs": [safe_reference(x) for x in record["evidence_refs"]],
        "expected_user_value": safe_text(record["expected_user_value"], 400),
        "affected_surfaces": safe_text_list(record["affected_surfaces"]),
        "dependencies": safe_text_list(record["dependencies"]),
        "security_privacy_constraints": safe_text_list(record["security_privacy_constraints"], limit=320),
        "acceptance_tests": safe_text_list(record["acceptance_tests"], limit=320),
        "size_risk": safe_text(record["size_risk"], 320),
        "owner": safe_text(record["owner"], 160),
        "next_action": _optional_text(record["next_action"], 320),
        "workstream_ref": _optional_reference(record.get("workstream_ref")),
    }


def _ux_finding(record):
    rendered_ref = _optional_reference(record.get("rendered_e2e_ref"))
    return {
        "finding_id": safe_reference(record["finding_id"]),
        "lifecycle": record["lifecycle"],
        "evidence_refs": [safe_reference(x) for x in record["evidence_refs"]],
        "surfaces": safe_text_list(record["surfaces"]),
        "friction": safe_text(record["friction"], 400),
        "hypothesis": safe_text(record["hypothesis"], 400),
        "acceptance_tests": safe_text_list(record["acceptance_tests"], limit=320),
        "workstream_ref": _optional_reference(record.get("workstream_ref")),
        "rendered_e2e_ref": rendered_ref,
        "visual_acceptance_status": "verified" if record["lifecycle"] == "VERIFIED" and rendered_ref else "not_recorded",
        "owner": safe_text(record["owner"], 160),
        "next_action": _optional_text(record["next_action"], 320),
    }


def _e2e_result(record):
    budgets = record["budgets"]
    projected_budget = None
    if budgets is not None:
        projected_budget = {
            "baseline_ref": safe_reference(budgets["baseline_ref"]),
            "rationale": safe_text(budgets["rationale"], 400),
            "thresholds": dict(sorted(budgets["thresholds"].items())),
        }
    viewport = record["viewport"]
    return {
        "journey_id": safe_reference(record["journey_id"]),
        "executor_schema": safe_reference(record["executor_schema"]),
        "measured_at": record["measured_at"],
        "viewport": {
            "class": viewport["class"],
            "width": viewport["width"],
            "height": viewport["height"],
        },
        "metrics": dict(sorted(record["metrics"].items())),
        "artifact_ref": safe_reference(record["artifact_ref"]),
        "baseline_ref": _optional_reference(record["baseline_ref"]),
        "comparison": record["comparison"],
        "budgets": projected_budget,
        "next_action": _optional_text(record["next_action"], 320),
    }


def project_product_ux(records):
    """Validate strict board contract first, then emit a smaller Pages whitelist."""
    if not isinstance(records, list):
        raise ValueError("Product/UX records must be a list")
    if records:
        validate_records(records)

    proposals = [_product_proposal(r) for r in records if r.get("kind") == "product_proposal"]
    findings = [_ux_finding(r) for r in records if r.get("kind") == "ux_finding"]

    latest = {}
    for record in records:
        if record.get("kind") != "e2e_result":
            continue
        vp = record["viewport"]
        key = (
            record["journey_id"],
            record["executor_schema"],
            vp["class"],
            vp["width"],
            vp["height"],
        )
        measured = parse_time(record["measured_at"])
        previous = latest.get(key)
        if previous is None or measured > previous[0]:
            latest[key] = (measured, record)

    e2e_latest = [_e2e_result(latest[key][1]) for key in sorted(latest)]
    proposals.sort(key=lambda r: r["proposal_id"])
    findings.sort(key=lambda r: r["finding_id"])
    return {
        "proposals": proposals,
        "ux_findings": findings,
        "e2e_latest": e2e_latest,
    }


def load_product_ux_records(directory):
    records = []
    for path in sorted(Path(directory).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            records.extend(data)
        else:
            records.append(data)
    return records


def build_output(rows, autonomy_snapshot, repository, product_records):
    return {
        "schema": "ai-bb-pages:v2",
        "generated": True,
        "tasks": rows,
        "autonomy": project_autonomy(autonomy_snapshot, repository),
        "product_ux": project_product_ux(product_records),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--autonomy-input", required=True)
    parser.add_argument("--product-ux-dir", default="data/product-ux-e2e")
    parser.add_argument("--output", default="pages/board.json")
    args = parser.parse_args()

    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise SystemExit("GITHUB_REPOSITORY is required")
    root = f"https://api.github.com/repos/{repo}"
    issues = [x for x in paged(f"{root}/issues?state=all") if "pull_request" not in x]
    now = datetime.now(timezone.utc)
    rows = []
    for issue in issues:
        comments = paged(issue["comments_url"])
        state, owner, last = replay(issue, comments, now)
        rows.append(project_row(issue, state, owner, last))
    rows.sort(key=lambda r: int(r["task"][1:]))

    autonomy_snapshot = json.loads(Path(args.autonomy_input).read_text(encoding="utf-8"))
    product_records = load_product_ux_records(args.product_ux_dir)
    output = build_output(rows, autonomy_snapshot, repo, product_records)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
