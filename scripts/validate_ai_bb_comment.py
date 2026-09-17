#!/usr/bin/env python3
"""Validate an ai-bb:v1 structured GitHub Issue comment."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MARKER = "<!-- ai-bb:v1 -->"
ALLOWED_TYPES = {"CLAIM", "HEARTBEAT", "RELEASE", "PROGRESS", "HANDOFF", "RESULT", "REVIEW"}
REQUIRED = {"type", "agent_id", "task", "idempotency_key", "summary", "next_action", "artifacts"}


def extract_payload(body: str) -> dict | None:
    if MARKER not in body:
        return None
    tail = body.split(MARKER, 1)[1]
    match = re.search(r"```json\s*(\{.*?\})\s*```", tail, re.DOTALL | re.IGNORECASE)
    if not match:
        raise ValueError("ai-bb:v1 marker must be followed by a fenced JSON object")
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError("envelope must be a JSON object")
    return value


def validate(payload: dict, issue_number: int | None = None) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED - payload.keys())
    if missing:
        errors.append("missing required fields: " + ", ".join(missing))
    if payload.get("type") not in ALLOWED_TYPES:
        errors.append("type must be one of: " + ", ".join(sorted(ALLOWED_TYPES)))
    for field in ("agent_id", "idempotency_key", "summary"):
        if not isinstance(payload.get(field), str) or not payload.get(field, "").strip():
            errors.append(f"{field} must be a non-empty string")
    task = payload.get("task")
    if not isinstance(task, str) or not re.fullmatch(r"#[1-9][0-9]*", task):
        errors.append("task must have form #<positive-issue-number>")
    elif issue_number is not None and task != f"#{issue_number}":
        errors.append(f"task must match containing Issue #{issue_number}")
    next_action = payload.get("next_action")
    if next_action is not None and (not isinstance(next_action, str) or not next_action.strip()):
        errors.append("next_action must be null or a non-empty string")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not all(isinstance(item, str) for item in artifacts):
        errors.append("artifacts must be an array of strings")
    if payload.get("type") in {"CLAIM", "HEARTBEAT"} and next_action is None:
        errors.append(f"{payload.get('type')} requires a non-null next_action")
    if payload.get("type") == "RESULT" and next_action is not None:
        errors.append("RESULT must set next_action to null")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, help="read comment body from a UTF-8 file instead of stdin")
    parser.add_argument("--issue-number", type=int, help="require payload.task to match this containing Issue number")
    args = parser.parse_args()
    body = args.file.read_text(encoding="utf-8") if args.file else sys.stdin.read()
    try:
        payload = extract_payload(body)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if payload is None:
        print("No ai-bb:v1 marker; nothing to validate.")
        return 0
    errors = validate(payload, args.issue_number)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Valid ai-bb:v1 {payload['type']} envelope for {payload['task']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
