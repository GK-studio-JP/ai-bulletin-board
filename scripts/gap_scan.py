#!/usr/bin/env python3
"""Deterministic standing Product/UX GAP_SCAN projection helpers.

Inputs are already-sanitized canonical finding/evidence/workstream facts. This
module never admits work or mutates GitHub; it forces every unresolved finding
to a single routing disposition and emits a freshness/operator-report receipt.
"""
from __future__ import annotations
from datetime import datetime, timezone

OPEN_LIFECYCLES={"DISCOVERY","PROPOSED"}
TERMINAL_DISPOSITIONS={"LIVE_EQUIVALENT","PROPOSE","DEFERRED","REJECTED","HUMAN_REQUIRED"}

def _iso(value):
    if isinstance(value,str):
        value=datetime.fromisoformat(value.replace("Z","+00:00"))
    if value.tzinfo is None: value=value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00","Z")

def gap_scan(findings, workstreams, *, scanned_at, safety_interrupt=None):
    """Return one sanitized GAP_SCAN receipt.

    A stale/deferred/closed PR is evidence only: only a live workstream whose
    finding_id matches can satisfy an unresolved finding. Safety interrupts
    always route Human Required rather than proposing autonomous admission.
    """
    live={str(w.get("finding_id")):w for w in workstreams if w.get("state")=="live"}
    gaps=[]
    for f in findings:
        if f.get("lifecycle") not in OPEN_LIFECYCLES: continue
        finding_id=str(f["finding_id"])
        equivalent=live.get(finding_id)
        if safety_interrupt:
            disposition="HUMAN_REQUIRED"; next_action="Human Required: resolve the safety interrupt before routing this finding."
        elif equivalent:
            disposition="LIVE_EQUIVALENT"; next_action=f"Continue live equivalent workstream {equivalent['workstream']}."
        elif f.get("authority_disposition") in {"DEFERRED","REJECTED"}:
            disposition=f["authority_disposition"]; next_action=str(f.get("authority_reason") or "Retain the explicit authority disposition.")
        else:
            disposition="PROPOSE"; next_action="Route a fresh non-overlapping workstream proposal through #16; do not self-admit."
        evidence=list(dict.fromkeys(map(str,f.get("evidence_refs",[]))))
        gaps.append({
            "finding_id":finding_id,
            "journey":str(f.get("journey") or ""),
            "impact":str(f.get("impact") or f.get("friction") or ""),
            "freshness":str(f.get("freshness") or "unknown"),
            "evidence_refs":evidence,
            "disposition":disposition,
            "duplicate_workstream": equivalent.get("workstream") if equivalent else None,
            "next_action":next_action,
        })
    if any(g["disposition"] not in TERMINAL_DISPOSITIONS for g in gaps):
        raise ValueError("gap lacks exactly one disposition")
    stamp=_iso(scanned_at)
    return {
        "schema":"ai-bb-gap-scan:v1",
        "scanned_at":stamp,
        "gap_count":len(gaps),
        "gaps":gaps,
        "freshness_receipt":{"scanned_at":stamp,"status":"fresh"},
        "operator_report_receipt":{"required":bool(gaps or safety_interrupt),"status":"required" if gaps or safety_interrupt else "no-material-gap"},
    }
