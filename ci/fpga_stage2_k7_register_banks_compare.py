"""Isolated K7/TC8 metric bank flip-flop tradeoff; not an all-receiver claim."""
import collections,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"build/stage2-k7-register-bank"
OUT.mkdir(parents=True,exist_ok=True)
cases={
 "distributed":"experiments/shared_tc8_k7_context.sv",
 "register_banks":"experiments/shared_tc8_k7_context_regbank.sv"
}
out={"scope":"Isolated TC8/K7 ACS core only; 4 contexts, not receiver; compare metric bank RAM and FF trade","cases":{},"adopted":False}
failed=False
for key,src in cases.items():
 f=ROOT/src;top="shared_tc8_k7_context"
 net=OUT/(key+".json")
 cmd=f"read_verilog -sv {f}; hierarchy -check -top {top}; synth_gowin -family gw2a -top {top} -nowidelut -json {net}; check -assert"
 p=subprocess.run(["yosys","-Q","-p",cmd],capture_output=True,text=True)
 (OUT/(key+".log")).write_text(p.stdout+"\n"+p.stderr)
 cell={"exit":p.returncode,"source_sha256":hashlib.sha256(f.read_bytes()).hexdigest()}
 if p.returncode==0:
  counter=collections.Counter(c["type"] for c in json.loads(net.read_text())["modules"][top]["cells"].values())
  cell.update(logic=sum(v for k,v in counter.items() if re.fullmatch(r"LUT[1-4]|ALU",k)),ff=sum(v for k,v in counter.items() if k.startswith("DFF")),bsram=sum(counter[k] for k in ("DPB","SDPB","DPX9B","SDPX9B")),ram16sdp4=counter["RAM16SDP4"],dsp=counter["MULT18X18"])
  cell["logic_with_ram_blockers"]=cell["logic"]+4*cell["ram16sdp4"]
 else:
  failed=True;print("CAD failure tail",key,(p.stdout+p.stderr)[-3000:])
 out["cases"][key]=cell
if not failed:
 out["diff"]={name:out["cases"]["register_banks"][name]-out["cases"]["distributed"][name] for name in ("logic","ff","bsram","ram16sdp4","dsp","logic_with_ram_blockers")}
(OUT/"result.json").write_text(json.dumps(out,indent=2)+"\n")
print(json.dumps(out,indent=2))
sys.exit(int(failed))
