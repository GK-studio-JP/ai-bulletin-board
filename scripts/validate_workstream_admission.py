#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, re, sys, urllib.request

KEY_LINE = re.compile(r"(?im)^\s*workstream\s*:\s*([^\s]+)\s*$")
VALID_KEY = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,127}$")
IMPLEMENTATION_TITLE = re.compile(r"^\s*(?:\[v0\.2\]|\[TASK\])", re.I)

def extract_key(body: str):
    matches = KEY_LINE.findall(body or "")
    if not matches:
        return None, None
    if len(matches) != 1:
        return None, "exactly one workstream key is required"
    key = matches[0].strip().lower()
    if not VALID_KEY.fullmatch(key):
        return None, "invalid workstream key"
    return key, None

def is_managed_implementation(issue: dict) -> bool:
    return bool(IMPLEMENTATION_TITLE.match(str(issue.get("title") or "")))

def validate_issue(current: dict, open_issues: list[dict]) -> list[str]:
    errors = []
    key, key_error = extract_key(str(current.get("body") or ""))
    if key_error:
        return [key_error]
    if is_managed_implementation(current) and not key:
        return ["managed implementation Issue is missing required workstream key"]
    if not key:
        return []
    current_number = int(current.get("number") or 0)
    conflicts = []
    for issue in open_issues:
        if "pull_request" in issue:
            continue
        number = int(issue.get("number") or 0)
        if number == current_number:
            continue
        other_key, other_error = extract_key(str(issue.get("body") or ""))
        if other_error or not other_key:
            continue
        if other_key == key:
            conflicts.append(number)
    if conflicts:
        joined = ", ".join(f"#{n}" for n in sorted(conflicts))
        errors.append(f"duplicate open workstream {key} already exists on {joined}")
    return errors

def validate_event(event: dict, open_issues: list[dict]) -> list[str]:
    if event.get("action") not in {"opened", "reopened"}:
        return []
    issue = event.get("issue")
    if not isinstance(issue, dict):
        return ["event does not contain an Issue payload"]
    return validate_issue(issue, open_issues)

def github_open_issues(repo: str, token: str) -> list[dict]:
    out, page = [], 1
    while True:
        url = f"https://api.github.com/repos/{repo}/issues?state=open&per_page=100&page={page}"
        headers = {"Accept":"application/vnd.github+json","User-Agent":"ai-bb-workstream-admission","Authorization":f"Bearer {token}"}
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise RuntimeError("unexpected GitHub issues response")
        out.extend(batch)
        if len(batch) < 100:
            return out
        page += 1

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event", required=True)
    parser.add_argument("--issues-json")
    args = parser.parse_args()
    with open(args.event, encoding="utf-8") as f:
        event = json.load(f)
    if args.issues_json:
        with open(args.issues_json, encoding="utf-8") as f:
            open_issues = json.load(f)
    else:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        token = os.environ.get("GITHUB_TOKEN", "")
        if not repo or not token:
            raise SystemExit("GITHUB_REPOSITORY and GITHUB_TOKEN are required")
        open_issues = github_open_issues(repo, token)
    errors = validate_event(event, open_issues)
    if errors:
        for error in errors:
            print("admission-error:", error, file=sys.stderr)
        return 1
    print("workstream admission: ok")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
