"""Stage 2-2: check all 29 frozen FPGA blocks, without fail-fast."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def audit():
 scope=json.loads((ROOT/"reports/fpga-estimate-closure/scope.json").read_text())
 ledger=json.loads((ROOT/"reports/fpga-estimate-closure/block-inventory.json").read_text())
 wanted=scope["required_stages"]["t"]+scope["required_stages"]["s"]+scope["required_support"]
 entries=ledger["entries"]
 checks=[]
 def ck(n,ok):checks.append({"name":n,"ok":bool(ok)})
 ids=[e["id"] for e in entries]
 ck("exactly 29 frozen ids",len(entries)==29 and len(set(ids))==29 and set(ids)=={e["id"] for e in wanted})
 for item in wanted:
  e=next((v for v in entries if v["id"]==item["id"]),{})
  state=e.get("status")
  path=e.get("candidate_source")
  ck("state:"+item["id"],state in ("partial","missing","integrated"))
  ck("candidate:"+item["id"],((path is None and state=="missing") or (isinstance(path,str) and (ROOT/path).is_file())))
  ck("ownership:"+item["id"],not(state!="integrated" and e.get("owner_status")=="verified"))
 return {"checks":checks,"all_conditions_checked":len(checks),"ng":sum(not c["ok"] for c in checks),"inventory_complete":all(c["ok"] for c in checks),"stage2_complete":False}
if __name__=="__main__":print(json.dumps(audit(),indent=2,ensure_ascii=False))
