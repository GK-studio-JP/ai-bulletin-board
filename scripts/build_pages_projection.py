#!/usr/bin/env python3
"""Build a sanitized read-only Pages projection from GitHub Issues/comments.

GitHub remains authoritative. This builder emits only derived, public-to-repo
coordination fields and fails closed when replay cannot be completed safely.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

MARKER = "<!-- ai-bb:v1 -->"
LEASE_SECONDS = 900
EVENT_TYPES = {"CLAIM", "HEARTBEAT", "RELEASE", "PROGRESS", "HANDOFF", "RESULT", "REVIEW"}
REQUIRED = {"type", "agent_id", "task", "idempotency_key", "summary", "next_action", "artifacts"}
SAFE_ARTIFACT = re.compile(r"^(?:Issue:#?\d+|PR:#?\d+(?:@[0-9a-f]{7,40})?|commit:[0-9a-f]{7,40}|merge:[0-9a-f]{7,40}|path:[A-Za-z0-9._/\-]+|[A-Za-z0-9._/\-]+)$")

SAFE_FIELDS = ("task", "title", "state", "agent", "last_event", "last_activity_at", "lease_expires_at", "review_needed", "current_head", "next_action", "artifacts")
CREDENTIAL_LIKE = re.compile(r"(?i)(?:authorization\s*:|bearer\s+|token\s*=|api[_-]?key\s*=|password\s*=|cookie\s*:|private[_ -]?key)")


def safe_text(value, limit=280):
    """Normalize bounded display text and fail closed on credential-like content."""
    text = " ".join(str(value or "").split())
    if CREDENTIAL_LIKE.search(text): return "[redacted]"
    return text[:limit]


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
    completed = False
    last = None
    current_head = ""
    reviewed_heads = set()
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
        heads = [x for x in p.get("artifacts", []) if re.fullmatch(r"PR:#?\d+@[0-9a-f]{7,40}", x)]
        if heads:
            current_head = heads[-1]
            if typ == "REVIEW":
                reviewed_heads.update(heads)
        # Lease expiry is a derived event-boundary fact. Clear stale ownership
        # before evaluating any later ownership-sensitive event.
        if owner is not None and expiry is not None and created >= expiry:
            owner = None
            expiry = None
        live = owner is not None and expiry is not None
        if typ == "CLAIM":
            if not live and not completed:
                owner = p["agent_id"]
                expiry = created + timedelta(seconds=LEASE_SECONDS)
        elif typ == "HEARTBEAT":
            if live and p["agent_id"] == owner:
                expiry = created + timedelta(seconds=LEASE_SECONDS)
        elif typ == "RELEASE":
            if live and p["agent_id"] == owner:
                owner = expiry = None
        elif typ == "RESULT":
            if live and p["agent_id"] == owner:
                completed = True
                owner = expiry = None
    if completed:
        state = "completed"
    elif owner is not None and expiry is not None and now < expiry:
        state = "claimed"
    else:
        state = "open"
        owner = None
    if last is not None:
        meta = {
            "last_activity_at": last[0].astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "lease_expires_at": expiry.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if owner is not None and expiry is not None and now < expiry else "",
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
        "review_needed": bool(meta.get("review_needed", False)),
        "current_head": meta.get("current_head", "") if SAFE_ARTIFACT.fullmatch(meta.get("current_head", "")) else "",
        "next_action": safe_text(p.get("next_action") or ""),
        "artifacts": safe_artifacts(p.get("artifacts", [])),
    }
    return {key: row[key] for key in SAFE_FIELDS}


def main():
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
    output = {"schema": "ai-bb-pages:v1", "generated": True, "tasks": rows}
    Path("pages").mkdir(exist_ok=True)
    Path("pages/board.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
