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
from datetime import datetime, timezone
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


def review_evidence(comments, current_head):
    current_reviewers = set()
    stale_reviewers = set()
    for c in comments:
        p = projection.payload(c.get("body") or "")
        if not p or p.get("type") != "REVIEW":
            continue
        for artifact in p.get("artifacts", []):
            if not HEAD_RE.fullmatch(artifact):
                continue
            if artifact == current_head:
                current_reviewers.add(p.get("agent_id") or "")
            else:
                stale_reviewers.add(p.get("agent_id") or "")
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
        exact_head = api(f"{root}/pulls/{pr_number}").get("head", {}).get("sha", "")
        referenced_sha = m.group(2)
        if exact_head and not exact_head.startswith(referenced_sha):
            # The task references a stale head; retain it as stale evidence only.
            review_count, stale_count = review_evidence(comments_by_issue[int(row["task"][1:])], head)
            stale_count += review_count
            review_count = 0
        else:
            review_count, stale_count = review_evidence(comments_by_issue[int(row["task"][1:])], head)
        review_meta.append({
            "pr": pr_number,
            "head": head,
            "review_needed": bool(row.get("review_needed", False)),
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
