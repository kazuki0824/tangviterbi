"""Stage 2 resource-estimate gate: comprehensive audit, no fail-fast.

Exit success only if every required FPGA block has actual, non-overlapping resource
accounting and a full receiver top P&R report. Keep negative evidence distinct.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCOPE = ROOT / "reports/fpga-estimate-closure/scope.json"
RECON = ROOT / "reports/fpga-estimate-closure/stage2-reconciliation.md"

def audit():
    data=json.loads(SCOPE.read_text())
    report=RECON.read_text()
    checks=[]
    def ck(n,ok,detail):
        checks.append(dict(name=n,ok=bool(ok),detail=detail))
    ck("reconciliation evidence recorded",all(t in report for t in ("20726","22002","1276","1266","22977")),"Maintain distinct incompatible area experiments")
    ck("capacity correctly reported",data["capacity"]["logic_positions"]==20736 and data["capacity"]["bsram_blocks"]==46,"Tang20K envelope")
    ck("no partial P&R upgraded to full",data["physical_probes"]["full_top_area"]["value"] is None and data["physical_probes"]["full_top_timing"]["value"] is None,"Previously saved 166.2234 MHz is a fixture")
    stages=data["required_stages"]["t"]+data["required_stages"]["s"]+data["required_support"]
    for item in stages:
        ck("area:"+item["id"],item.get("area")=="integrated_measured",item["name"])
    for name in ("logic","ff","bsram","distributed_ram","dsp","pll","pins","sdram_storage"):
        ck("full-top physical resource:"+name,False,"No single all-receiver placed netlist and ownership-reconciled measurement")
    ck("shared-component double counts",False,"Instance-level ownership mapping not yet established")
    ck("full receiver legal placement",False,"No qualifying fully-connected FPGA netlist and P&R result")
    stage2_complete=all(x["ok"] for x in checks)
    return dict(stage=2,all_conditions_checked=len(checks),ng=sum(not x["ok"] for x in checks),completion=stage2_complete,stage3_permitted=stage2_complete,checks=checks)

def main():
    result=audit()
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return int(not result["completion"])

if __name__=="__main__":sys.exit(main())
