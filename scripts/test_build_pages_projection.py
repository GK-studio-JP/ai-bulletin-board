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
secret = event("CLAIM", "agent-safe", "privacy-1", "Authorization: Bearer super-secret-token-value")
secret["artifacts"] = ["PR:#53@97e0d877", "https://evil.example/raw", "token=secret"]
c = comment(9, 0, secret)
state, owner, last = m.replay(issue, [c], T0 + timedelta(seconds=1))
row = m.project_row({"number": 1, "body": "RAW PRIVATE ISSUE BODY"}, state, owner, last)
assert tuple(row.keys()) == m.SAFE_FIELDS
assert row["next_action"] == "[redacted]"
assert row["artifacts"] == ["PR:#53@97e0d877"]
serialized = __import__("json").dumps(row)
assert "RAW PRIVATE ISSUE BODY" not in serialized
assert "super-secret-token-value" not in serialized
assert "evil.example" not in serialized
assert "token=secret" not in serialized

# Benign display strings are bounded and normalized.
assert m.safe_text("  review   PR #53  ") == "review PR #53"
assert len(m.safe_text("x" * 500)) == 280

print("pages projection replay/privacy regressions: ok")
