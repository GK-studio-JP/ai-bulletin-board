#!/usr/bin/env python3
"""Validate an ai-bb:v1 structured GitHub Issue comment.

Reads a comment body from stdin (or --file) and exits non-zero only when the
comment declares the ai-bb:v1 marker but violates the envelope contract.
Unmarked human discussion is intentionally ignored.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

MARKER = "<!-- ai-bb:v1 -->"
ALLOWED_TYPES = {"CLAIM", "PROGRESS", "HANDOFF", "RESULT", "REVIEW"}
REQUIRED = {"type", "agent_id", "task", "summary", "next_action", "artifacts"}


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


def validate(payload: dict) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED - payload.keys())
    if missing:
        errors.append("missing required fields: " + ", ".join(missing))
    if payload.get("type") not in ALLOWED_TYPES:
        errors.append("type must be one of: " + ", ".join(sorted(ALLOWED_TYPES)))
    if not isinstance(payload.get("agent_id"), str) or not payload.get("agent_id", "").strip():
        errors.append("agent_id must be a non-empty string")
    task = payload.get("task")
    if not isinstance(task, str) or not re.fullmatch(r"#[1-9][0-9]*", task):
        errors.append("task must have form #<positive-issue-number>")
    if not isinstance(payload.get("summary"), str) or not payload.get("summary", "").strip():
        errors.append("summary must be a non-empty string")
    next_action = payload.get("next_action")
    if next_action is not None and (not isinstance(next_action, str) or not next_action.strip()):
        errors.append("next_action must be null or a non-empty string")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not all(isinstance(item, str) for item in artifacts):
        errors.append("artifacts must be an array of strings")
    if payload.get("type") in {"CLAIM", "PROGRESS", "HANDOFF"} and next_action is None:
        errors.append(f"{payload.get('type')} requires a non-null next_action")
    if payload.get("type") == "RESULT" and next_action is not None:
        errors.append("RESULT should set next_action to null")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, help="read comment body from a UTF-8 file instead of stdin")
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
    errors = validate(payload)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Valid ai-bb:v1 {payload['type']} envelope for {payload['task']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
