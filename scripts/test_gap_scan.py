#!/usr/bin/env python3
import pathlib,sys
from datetime import datetime,timezone
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from gap_scan import gap_scan

NOW=datetime(2026,9,18,13,0,tzinfo=timezone.utc)
def finding(**extra):
    base={"finding_id":"board/narrow-review-target-below-fold","lifecycle":"DISCOVERY","journey":"board/review-needed-inspect@narrow:390x844","impact":"Accepted green E2E still leaves the review target 147 px below the viewport before action.","freshness":"current accepted evidence","evidence_refs":["path:data/product-ux-e2e/ux-finding-narrow-review-target-2026-09-18.json","PR:#68:stale-deferred"]}
    base.update(extra); return base

def main():
    # Green transition evidence does not erase accepted UX friction, and stale PR #68 is not live.
    scan=gap_scan([finding()],[],scanned_at=NOW)
    assert scan["gap_count"]==1 and scan["gaps"][0]["disposition"]=="PROPOSE"
    assert "147 px" in scan["gaps"][0]["impact"]
    assert scan["operator_report_receipt"]["status"]=="required"
    # A live equivalent deduplicates routing rather than creating another lane.
    live=[{"finding_id":finding()["finding_id"],"workstream":"ux/narrow-review-current","state":"live"}]
    assert gap_scan([finding()],live,scanned_at=NOW)["gaps"][0]["disposition"]=="LIVE_EQUIVALENT"
    # Explicit authority disposition is terminal and preserved.
    deferred=finding(authority_disposition="DEFERRED",authority_reason="Owner deferred pending redesign evidence.")
    assert gap_scan([deferred],[],scanned_at=NOW)["gaps"][0]["disposition"]=="DEFERRED"
    # Safety always prevents autonomous proposal/admission.
    unsafe=gap_scan([finding()],[],scanned_at=NOW,safety_interrupt="MAIN_RED")
    assert unsafe["gaps"][0]["disposition"]=="HUMAN_REQUIRED"
    # Even an empty scan emits deterministic freshness and operator-report receipts.
    empty=gap_scan([],[],scanned_at=NOW)
    assert empty["gap_count"]==0 and empty["freshness_receipt"]["status"]=="fresh"
    assert empty["operator_report_receipt"]["status"]=="no-material-gap"
    print("gap scan: ok")
if __name__=="__main__": main()
