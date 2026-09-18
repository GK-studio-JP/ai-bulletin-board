#!/usr/bin/env python3
"""Derive a read-only autonomy/watchdog snapshot from GitHub-native state.

This tool never mutates Issues, PRs, repository settings, or protocol state.
It consumes canonical GitHub Issue/comment history plus exact current PR heads
and emits a small sanitized operational snapshot for Actions/Pages consumers.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import build_pages_projection as projection

WORKSTREAM_RE = re.compile(r"(?mi)^workstream:\s*([a-z0-9._/-]+)\s*$")
HEAD_RE = re.compile(r"^PR:#?(\d+)@([0-9a-f]{7,40})$")
HUMAN_RE = re.compile(r"(?i)\b(?:human required|human owner|owner decision|required human)\b")
FAIL_CONCLUSIONS = {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}

SAFE_TASK_FIELDS = (
    "task", "state", "agent", "lease_status", "review_needed", "current_head",
    "next_action", "next_class", "waiting_reason",
)
SAFE_REVIEW_FIELDS = ("pr", "head", "review_needed", "review_count", "stale_review_count")
SAFE_HEALTH_FIELDS = (
    "main_status", "duplicate_workstream_violation", "review_storm",
    "stale_review", "stale_or_expiring_claim", "history_unsafe", "human_required",
)


def api(url: str):
    token = os.environ.get("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-bb-autonomy-watchdog",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return json.load(r)


def paged(url: str):
    out = []
    page = 1
    while True:
        sep = "&" if "?" in url else "?"
        batch = api(f"{url}{sep}per_page=100&page={page}")
        if not isinstance(batch, list):
            raise RuntimeError("unexpected GitHub response")
        out.extend(batch)
        if len(batch) < 100:
            return out
        page += 1


def workstream_keys(issues):
    owners = defaultdict(list)
    for issue in issues:
        if "pull_request" in issue or issue.get("state") != "open":
            continue
        body = issue.get("body") or ""
        for key in WORKSTREAM_RE.findall(body):
            owners[key].append(issue["number"])
    return {k: sorted(v) for k, v in owners.items()}


def main_check_state(check_runs):
    if not check_runs:
        return "MAIN_UNKNOWN"
    if any((c.get("conclusion") or "") in FAIL_CONCLUSIONS for c in check_runs):
        return "MAIN_RED"
    completed = [c for c in check_runs if c.get("status") == "completed"]
    if len(completed) == len(check_runs) and all(
        (c.get("conclusion") or "") in {"success", "neutral", "skipped"} for c in completed
    ):
        return "MAIN_GREEN"
    return "MAIN_UNKNOWN"


def head_identity(artifact):
    m = HEAD_RE.fullmatch(artifact or "")
    return (int(m.group(1)), m.group(2)) if m else None


def same_head(artifact, target):
    """Match the same PR head while allowing canonical short SHA artifacts."""
    left = head_identity(artifact)
    right = head_identity(target)
    return bool(left and right and left[0] == right[0] and (left[1].startswith(right[1]) or right[1].startswith(left[1])))


def review_evidence(comments, current_head, issue_number):
    """Count only canonical independent review evidence under replay semantics."""
    events = []
    for c in comments:
        body = c.get("body") or ""
        if projection.MARKER not in body:
            continue
        created = projection.parse_time(c["created_at"])
        updated = c.get("updated_at")
        if updated and projection.parse_time(updated) != created:
            return 0, 0
        p = projection.payload(body)
        if p is not None and projection.canonical(p, issue_number):
            events.append((created, int(c["id"]), p))
    events.sort(key=lambda x: (x[0], x[1]))

    seen = {}
    owner = None
    expiry = None
    completed = False
    head_authors = {}
    current_reviewers = set()
    stale_reviewers = set()

    for created, _cid, p in events:
        key = p["idempotency_key"]
        normalized = json.dumps(p, sort_keys=True, separators=(",", ":"))
        if key in seen:
            continue
        seen[key] = normalized

        if owner is not None and expiry is not None and created >= expiry:
            owner = None
            expiry = None
        live = owner is not None and expiry is not None
        typ = p["type"]
        heads = [x for x in p.get("artifacts", []) if HEAD_RE.fullmatch(x)]

        if typ == "REVIEW":
            for head in heads:
                author = head_authors.get(head)
                if not author or p["agent_id"] == author:
                    continue
                if same_head(head, current_head):
                    current_reviewers.add(p["agent_id"])
                else:
                    stale_reviewers.add(p["agent_id"])
        elif typ in {"PROGRESS", "HANDOFF", "RESULT"} and live and p["agent_id"] == owner:
            for head in heads:
                head_authors.setdefault(head, p["agent_id"])

        if typ == "CLAIM":
            if not live and not completed:
                owner = p["agent_id"]
                expiry = created + timedelta(seconds=projection.LEASE_SECONDS)
        elif typ == "HEARTBEAT":
            if live and p["agent_id"] == owner:
                expiry = created + timedelta(seconds=projection.LEASE_SECONDS)
        elif typ == "RELEASE":
            if live and p["agent_id"] == owner:
                owner = expiry = None
        elif typ == "RESULT":
            if live and p["agent_id"] == owner:
                completed = True
                owner = expiry = None

    return len(current_reviewers), len(stale_reviewers)


def classify_task(row, main_status):
    state = row.get("state") or "open"
    next_action = row.get("next_action") or ""
    if state == "history_unsafe":
        return "broken-main/security", "history_unsafe"
    if HUMAN_RE.search(next_action):
        return "idle/human-required", "human-required decision"
    if main_status == "MAIN_RED":
        return "broken-main/security", "required current-main check is red"
    if state == "claimed":
        return "live-claim", row.get("lease_status") or "active claim"
    if row.get("current_head") and row.get("review_needed"):
        return "review-needed", "current exact head lacks independent review"
    if row.get("current_head"):
        return "integration/verification", "reviewed current head awaits integration/verification"
    if state == "completed":
        return "idle/human-required", "completed"
    return "implementation-ready", "open and unclaimed"


def derive(tasks, review_meta, main_status, duplicate_keys):
    queue = []
    for row in tasks:
        next_class, reason = classify_task(row, main_status)
        safe = {k: row.get(k, "") for k in SAFE_TASK_FIELDS if k not in {"next_class", "waiting_reason"}}
        safe["next_class"] = next_class
        safe["waiting_reason"] = reason
        queue.append(safe)

    queue.sort(key=lambda x: ([
        "broken-main/security", "live-claim", "review-needed",
        "implementation-ready", "integration/verification", "idle/human-required"
    ].index(x["next_class"]), int((x.get("task") or "#0")[1:])))

    health = {
        "main_status": main_status,
        "duplicate_workstream_violation": bool(duplicate_keys),
        "review_storm": any(x["review_count"] > 1 for x in review_meta),
        "stale_review": any(x["stale_review_count"] > 0 for x in review_meta),
        "stale_or_expiring_claim": any(x.get("lease_status") in {"stale", "expiring"} for x in tasks),
        "history_unsafe": any(x.get("state") == "history_unsafe" for x in tasks),
        "human_required": any(HUMAN_RE.search(x.get("next_action") or "") for x in tasks),
    }
    return {
        "schema": "ai-bb-autonomy:v1",
        "generated": True,
        "health": {k: health[k] for k in SAFE_HEALTH_FIELDS},
        "queue": queue,
        "review_queue": review_meta,
        "duplicate_workstreams": duplicate_keys,
    }


def collect(repo: str):
    root = f"https://api.github.com/repos/{repo}"
    repository = api(root)
    main_sha = repository["default_branch"]
    branch = api(f"{root}/branches/{main_sha}")
    head_sha = branch["commit"]["sha"]

    issues = [x for x in paged(f"{root}/issues?state=all") if "pull_request" not in x]
    open_issues = [x for x in issues if x.get("state") == "open"]
    now = datetime.now(timezone.utc)

    tasks = []
    comments_by_issue = {}
    for issue in issues:
        comments = paged(issue["comments_url"])
        comments_by_issue[issue["number"]] = comments
        state, owner, last = projection.replay(issue, comments, now)
        tasks.append(projection.project_row(issue, state, owner, last))

    review_meta = []
    for row in tasks:
        head = row.get("current_head") or ""
        if not head:
            continue
        m = HEAD_RE.fullmatch(head)
        if not m:
            continue
        pr_number = int(m.group(1))
        issue_number = int(row["task"][1:])
        exact_head_sha = api(f"{root}/pulls/{pr_number}").get("head", {}).get("sha", "")
        exact_head = f"PR:#{pr_number}@{exact_head_sha}" if exact_head_sha else head
        review_count, stale_count = review_evidence(
            comments_by_issue[issue_number], exact_head, issue_number
        )
        review_meta.append({
            "pr": pr_number,
            "head": exact_head,
            "review_needed": review_count == 0,
            "review_count": review_count,
            "stale_review_count": stale_count,
        })
    review_meta = [{k: x[k] for k in SAFE_REVIEW_FIELDS} for x in review_meta]

    checks = api(f"{root}/commits/{head_sha}/check-runs").get("check_runs", [])
    duplicates = {k: v for k, v in workstream_keys(open_issues).items() if len(v) > 1}
    return derive(tasks, review_meta, main_check_state(checks), duplicates)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="pages/autonomy.json")
    args = parser.parse_args()
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise SystemExit("GITHUB_REPOSITORY is required")
    data = collect(repo)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
