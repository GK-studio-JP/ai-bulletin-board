#!/usr/bin/env python3
"""Deterministic regression tests for the Pages canonical replay."""
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("projection", Path(__file__).with_name("build_pages_projection.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

def iso(t):
    return t.isoformat().replace("+00:00", "Z")

def comment(cid, seconds, payload, edited=False):
    created = T0 + timedelta(seconds=seconds)
    body = m.MARKER + "\n\x60\x60\x60json\n" + __import__("json").dumps(payload) + "\n\x60\x60\x60"
    return {"id": cid, "created_at": iso(created), "updated_at": iso(created + timedelta(seconds=1) if edited else created), "body": body}

def event(kind, agent, key, next_action="work"):
    return {"type": kind, "agent_id": agent, "task": "#1", "idempotency_key": key, "summary": kind, "next_action": None if kind == "RESULT" else next_action, "artifacts": []}

issue = {"number": 1}

# Edited marker-bearing comment must fail closed even when current body is malformed.
bad = comment(1, 0, event("CLAIM", "a", "k1"), edited=True)
bad["body"] = m.MARKER + "\nnot-json"
assert m.replay(issue, [bad], T0)[0] == "history_unsafe"

# Expired former owner cannot renew or complete after the 900-second boundary.
comments = [
    comment(1, 0, event("CLAIM", "a", "k1")),
    comment(2, 901, event("HEARTBEAT", "a", "k2")),
    comment(3, 902, event("RESULT", "a", "k3")),
]
state, owner, _ = m.replay(issue, comments, T0 + timedelta(seconds=903))
assert (state, owner) == ("open", None)

# A later claimant after expiry owns; old owner RELEASE cannot clear it.
comments.append(comment(4, 903, event("CLAIM", "b", "k4")))
comments.append(comment(5, 904, event("RELEASE", "a", "k5")))
state, owner, _ = m.replay(issue, comments, T0 + timedelta(seconds=905))
assert (state, owner) == ("claimed", "b")

# Conflicting duplicate idempotency key has no state effect.
comments = [
    comment(1, 0, event("CLAIM", "a", "same")),
    comment(2, 1, event("RELEASE", "a", "same")),
]
state, owner, _ = m.replay(issue, comments, T0 + timedelta(seconds=2))
assert (state, owner) == ("claimed", "a")

# Effective RESULT remains terminal to later protocol CLAIMs in this Issue.
comments = [
    comment(1, 0, event("CLAIM", "a", "r1")),
    comment(2, 1, event("RESULT", "a", "r2")),
    comment(3, 2, event("CLAIM", "b", "r3")),
]
state, owner, _ = m.replay(issue, comments, T0 + timedelta(seconds=3))
assert (state, owner) == ("completed", None)

# Projection boundary is an explicit whitelist and never copies Issue/comment payloads.
privacy_claim = event("CLAIM", "agent-safe", "privacy-claim")
secret = event("PROGRESS", "agent-safe", "privacy-1", "Authorization: Bearer super-secret-token-value")
secret["artifacts"] = ["PR:#53@97e0d877", "https://evil.example/raw", "token=secret"]
c = comment(9, 1, secret)
state, owner, last = m.replay(issue, [comment(8, 0, privacy_claim), c], T0 + timedelta(seconds=2))
row = m.project_row({"number": 1, "title": "Authorization: Bearer title-secret", "body": "RAW PRIVATE ISSUE BODY"}, state, owner, last)
assert tuple(row.keys()) == m.SAFE_FIELDS
assert row["title"] == "[redacted]"
assert row["next_action"] == "[redacted]"
assert row["artifacts"] == ["PR:#53@97e0d877"]
assert row["last_activity_at"] == iso(T0 + timedelta(seconds=1))
assert row["lease_expires_at"] == iso(T0 + timedelta(seconds=900))
assert row["review_needed"] is True
assert row["current_head"] == "PR:#53@97e0d877"
serialized = __import__("json").dumps(row)
assert "RAW PRIVATE ISSUE BODY" not in serialized
assert "super-secret-token-value" not in serialized
assert "title-secret" not in serialized
assert "evil.example" not in serialized
assert "token=secret" not in serialized

# Exact-head REVIEW coverage clears review_needed without exposing review bodies.
reviewed = event("REVIEW", "reviewer", "privacy-2", "checked")
reviewed["artifacts"] = ["PR:#53@97e0d877"]
state, owner, last = m.replay(issue, [comment(8, 0, privacy_claim), c, comment(10, 2, reviewed)], T0 + timedelta(seconds=3))
row = m.project_row({"number": 1, "title": "Safe title"}, state, owner, last)
assert row["review_needed"] is False
assert row["current_head"] == "PR:#53@97e0d877"
assert row["last_activity_at"] == iso(T0 + timedelta(seconds=2))

# Stale lease evidence survives later non-ownership activity after expiry.
stale_claim = event("CLAIM", "lease-owner", "lease-1")
stale_review = event("REVIEW", "reviewer", "lease-2")
state, owner, last = m.replay(
    issue,
    [comment(20, 0, stale_claim), comment(21, 901, stale_review)],
    T0 + timedelta(seconds=902),
)
row = m.project_row({"number": 1, "title": "Lease task"}, state, owner, last)
assert (state, owner) == ("open", None)
assert row["lease_expires_at"] == iso(T0 + timedelta(seconds=900))
assert row["lease_status"] == "stale"

# Review coverage is exact-head and must come from a different logical agent.
head1 = "PR:#53@1111111"
head2 = "PR:#53@2222222"
owner_claim = event("CLAIM", "author", "head-claim")
produced1 = event("PROGRESS", "author", "head-1")
produced1["artifacts"] = [head1]
produced2 = event("PROGRESS", "author", "head-2")
produced2["artifacts"] = [head2]
stale_review = event("REVIEW", "reviewer", "head-review-old")
stale_review["artifacts"] = [head1]
state, owner, last = m.replay(
    issue,
    [comment(30, 0, owner_claim), comment(31, 1, produced1), comment(32, 2, produced2), comment(33, 3, stale_review)],
    T0 + timedelta(seconds=4),
)
row = m.project_row({"number": 1, "title": "Review task"}, state, owner, last)
assert row["current_head"] == head2
assert row["review_needed"] is True

# A later non-review mention of an already-seen older head must not regress current_head.
stale_nonreview = event("PROGRESS", "manager", "head-stale-nonreview")
stale_nonreview["artifacts"] = [head1]
state, owner, last = m.replay(
    issue,
    [comment(40, 0, owner_claim), comment(41, 1, produced1), comment(42, 2, produced2), comment(43, 3, stale_nonreview)],
    T0 + timedelta(seconds=4),
)
row = m.project_row({"number": 1, "title": "Non-regressive head task"}, state, owner, last)
assert row["current_head"] == head2
assert row["review_needed"] is True

self_review = event("REVIEW", "author", "head-self-review")
self_review["artifacts"] = [head1]
state, owner, last = m.replay(
    issue,
    [comment(50, 0, owner_claim), comment(51, 1, produced1), comment(52, 2, self_review)],
    T0 + timedelta(seconds=3),
)
row = m.project_row({"number": 1, "title": "Self review task"}, state, owner, last)
assert row["review_needed"] is True

# A non-owner mention cannot establish or overwrite implementation-head authorship.
manager_mention = event("PROGRESS", "manager", "head-manager-mention")
manager_mention["artifacts"] = [head1]
author_review = event("REVIEW", "author", "head-author-review")
author_review["artifacts"] = [head1]
state, owner, last = m.replay(
    issue,
    [comment(60, 0, owner_claim), comment(61, 1, manager_mention), comment(62, 2, produced1), comment(63, 3, author_review)],
    T0 + timedelta(seconds=4),
)
row = m.project_row({"number": 1, "title": "Author attribution task"}, state, owner, last)
assert row["current_head"] == head1
assert row["review_needed"] is True

independent_review = event("REVIEW", "other-reviewer", "head-independent-review")
independent_review["artifacts"] = [head1]
state, owner, last = m.replay(
    issue,
    [comment(70, 0, owner_claim), comment(71, 1, manager_mention), comment(72, 2, produced1), comment(73, 3, independent_review)],
    T0 + timedelta(seconds=4),
)
row = m.project_row({"number": 1, "title": "Independent review task"}, state, owner, last)
assert row["current_head"] == head1
assert row["review_needed"] is False

# Benign display strings are bounded and normalized.
assert m.safe_text("  review   PR #53  ") == "review PR #53"
assert len(m.safe_text("x" * 500)) == 280

print("pages projection replay/privacy regressions: ok")
