#!/usr/bin/env python3
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("admission", Path(__file__).with_name("validate_workstream_admission.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def issue(number, title, body="", state="open"):
    return {"number": number, "title": title, "body": body, "state": state}

existing = issue(10, "[v0.2] Existing lane", "workstream: v0.2/ui-overview")
event = {"action":"opened","issue":issue(20,"[v0.2] New lane","workstream: v0.2/ui-overview")}
assert m.validate_event(event,[existing,event["issue"]]) == ["duplicate open workstream v0.2/ui-overview already exists on #10"]

event = {"action":"opened","issue":issue(21,"[TASK] Unique lane","workstream: v0.2/search")}
assert m.validate_event(event,[existing,event["issue"]]) == []

event = {"action":"opened","issue":issue(22,"[v0.2] Missing key","Parent: #16")}
assert m.validate_event(event,[event["issue"]]) == ["managed implementation Issue is missing required workstream key"]

event = {"action":"reopened","issue":issue(23,"[TASK] Reopened duplicate","workstream: v0.2/ui-overview")}
assert m.validate_event(event,[existing,event["issue"]]) == ["duplicate open workstream v0.2/ui-overview already exists on #10"]

pr = {"number":99,"title":"PR","body":"workstream: v0.2/search","pull_request":{}}
event = {"action":"opened","issue":issue(24,"[TASK] Search lane","workstream: v0.2/search")}
assert m.validate_event(event,[pr,event["issue"]]) == []

print("workstream admission regressions: ok")
