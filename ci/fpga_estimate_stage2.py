"""Stage 2 resource-estimate gate: comprehensive audit, no fail-fast.

Exit success only if every required FPGA block has actual, non-overlapping resource
accounting and a full receiver top P&R report. Keep negative evidence distinct.
"""
import json
import sys
import hashlib
import re
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
    proof_path=ROOT / "reports/fpga-estimate-closure/full-top-proof.json"
    proof=json.loads(proof_path.read_text()) if proof_path.exists() else {}
    def verified_file(node):
        if not isinstance(node, dict):
            return False
        p=node.get("path"); h=node.get("sha256")
        if not isinstance(p,str) or not isinstance(h,str) or not re.fullmatch(r"[0-9a-f]{64}",h):
            return False
        target=(ROOT/p).resolve()
        if not target.is_relative_to(ROOT) or not target.is_file():
            return False
        return hashlib.sha256(target.read_bytes()).hexdigest()==h

    file_proofs={k:proof.get(k,{}) for k in ("source","routed_netlist","timing_report","resource_report","constraints")}
    for name,node in file_proofs.items():
        ck("evidence file sha256:"+name,verified_file(node),"Require real file and matching SHA-256")
    evidence_set=all(verified_file(node) for node in file_proofs.values())
    measured=proof.get("blocks",{})
    resources=proof.get("resources",{})
    stages=data["required_stages"]["t"]+data["required_stages"]["s"]+data["required_support"]
    for item in stages:
        ck("area:"+item["id"],bool(evidence_set and measured.get(item["id"],{}).get("placed_instance") and measured.get(item["id"],{}).get("owned_resources") and measured.get(item["id"],{}).get("source_sha256")),item["name"])
    for name in ("logic","ff","bsram","distributed_ram","dsp","pll","pins","sdram_storage"):
        ck("full-top physical resource:"+name,evidence_set and resources.get(name,{}).get("value") is not None and resources.get(name,{}).get("evidence_hash")==file_proofs["resource_report"].get("sha256"),"Require single all-receiver placed netlist and ownership-reconciled measurement")
    ck("shared-component double counts",evidence_set and proof.get("all_instance_ownership_unique") is True,"Instance-level ownership must be established")
    ck("full receiver legal placement",evidence_set and proof.get("all_stage_connected") is True and proof.get("legal_placement") is True and proof.get("all_stage_functional_checks") is True,"All required blocks and functions must be present")
    stage2_complete=all(x["ok"] for x in checks)
    return dict(stage=2,all_conditions_checked=len(checks),ng=sum(not x["ok"] for x in checks),completion=stage2_complete,stage3_permitted=stage2_complete,checks=checks)

def main():
    result=audit()
    print(json.dumps(result,indent=2,ensure_ascii=False))
    return int(not result["completion"])

if __name__=="__main__":sys.exit(main())
