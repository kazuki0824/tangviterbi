"""Stage-1 finite-scope audit. Collect every failure; no fail-fast."""
import json
import sys
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "reports/fpga-estimate-closure/scope.json"

def audit(m):
    checks=[]
    def ck(name,ok,detail=""):
        checks.append({"check":name,"ok":bool(ok),"detail":str(detail)})
    ck("schema", m.get("schema")=="fpga-scope-v1")
    t=m["required_stages"]["t"];s=m["required_stages"]["s"];sup=m["required_support"]
    ck("T eight stages",len(t)==8,len(t))
    ck("S six stages",len(s)==6,len(s))
    ids=[z["id"] for z in t+s+sup]
    ck("unique block ownership",len(ids)==len(set(ids)),len(ids))
    ck("frozen PR#10 SHA",len(m["baseline"]["upstream_sha"])==40)
    ck("two independent S3",m["topology"]["soc"]["quantity"]==2)
    ck("one FPGA, simultaneous",m["topology"]["fpga"]["quantity"]==1 and m["topology"]["receiver"]["t_and_s_simultaneously"])
    ck("no reconfiguration",m["topology"]["receiver"]["t_and_s_share_single_fpga_image"])
    ck("no degradation or backhaul",len(m["topology"]["forbidden_changes"])>=6 and "FPGA to S3 payload forbidden" in m["topology"]["owner_rule"])
    ck("input widths",all(m["io"][k]["i_bits"]==10 and m["io"][k]["q_bits"]==10 for k in ("t","s")))
    ck("rates and lossless bandwidth",m["io"]["t"]["samples_per_second"]*20//8==m["io"]["t"]["payload_Bps"] and m["io"]["s"]["samples_per_second"]*20//8==m["io"]["s"]["payload_Bps"])
    ck("mode & modulations",m["io"]["t"]["modes"]==[1,2,3] and set(m["io"]["s"]["modulations"])=={"TC8PSK","BPSK","QPSK"})
    ck("TMCC and dynamic slots",m["io"]["s"]["tmcc"] and m["io"]["s"]["slot_allocation_dynamic"])
    ck("separate TS sinks",all(m["io"]["outputs"].get(k) for k in ("t","s")))
    ck("FPGA resource envelope",m["capacity"]["logic_positions"]==20736 and m["capacity"]["ff_positions"]==15552 and m["capacity"]["bsram_blocks"]==46 and m["capacity"]["dsp18_units"]==48)
    ck("clock constraints scoped",len(m["clock"]["requirements"])>=4 and len(m["clock"]["source_asynchronous"])==2)
    ck("required block has evidence pointer",all(x.get("source") for x in t+s+sup))
    ck("required block not falsely estimated",all(x.get("area") in ("not_integrated","reconcile") and x.get("deadline") in ("not_integrated","reconcile") for x in t+s+sup))
    ck("old area explicitly not full top",m["physical_probes"]["legacy_area"]["classification"].startswith("conditional"))
    ck("partial Fmax explicitly not full top","partial fixture" in m["physical_probes"]["partial_pnr"]["classification"])
    ck("full top presently unknown",m["physical_probes"]["full_top_area"]["value"] is None and m["physical_probes"]["full_top_timing"]["value"] is None)
    ck("document every known unclosed block",len(m["known_unclosed"])>=10)
    ck("not claiming hardware validation",not m["hardware_verified"] and not m["receiver_adopted"])
    ck("strict stage ordering",not any(m.get("stage"+str(i)+"_complete",False) for i in (2,3,4,5)))
    ck("source references listed",len(m["evidence_paths"])>=10)
    return checks

def main():
    checks=audit(json.loads(P.read_text()))
    failed=[x for x in checks if not x["ok"]]
    report={"stage":1,"all_checks_executed":len(checks),"failed_checks":len(failed),"checks":checks,"stage1_completed":not failed,"stage2_approved_to_start":not failed}
    print(json.dumps(report,indent=2))
    return int(bool(failed))

if __name__=="__main__":sys.exit(main())
