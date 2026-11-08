"""Compare unmodified vs bank-addressed FIR using identical pinned Gowin mapping."""
import collections,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"build/dual-banked-fir33"
OUT.mkdir(parents=True,exist_ok=True)
sources={
 "baseline":("rtl/isdb_complex_fir33.sv","dual_isdb_complex_fir33"),
 "banked":("experiments/isdb_complex_fir33_banked.sv","dual_isdb_complex_fir33_banked")
}
def count_netlist(netlist,top):
 cells=json.loads(netlist.read_text())["modules"][top]["cells"]
 c=collections.Counter(x["type"] for x in cells.values())
 return {"logic":sum(v for k,v in c.items() if re.fullmatch(r"LUT[1-4]|ALU",k)),
  "ff":sum(v for k,v in c.items() if k.startswith("DFF")),
  "bsram":sum(c[k] for k in ("DPB","SDPB","DPX9B","SDPX9B")),
  "distributed_ram":c["RAM16SDP4"],"dsp":c["MULT18X18"]}
results={}
failure=False
for name,(src,top) in sources.items():
 f=ROOT/src
 netlist=OUT/(name+"-mapped.json")
 script=f"read_verilog -sv {f}; hierarchy -check -top {top}; synth_gowin -family gw2a -top {top} -nowidelut -json {netlist}; check -assert"
 p=subprocess.run(["yosys","-Q","-p",script],capture_output=True,text=True)
 (OUT/(name+"-yosys.log")).write_text(p.stdout+"\n"+p.stderr)
 results[name]={"source":src,"sha256":hashlib.sha256(f.read_bytes()).hexdigest(),"synthesis_exit":p.returncode}
 if p.returncode==0:results[name].update(count_netlist(netlist,top))
 else:
  failure=True
  print((p.stdout+p.stderr)[-5000:])
if not failure:
 results["difference"]={name:results["banked"][name]-results["baseline"][name]
  for name in ("logic","ff","bsram","distributed_ram","dsp")}
results["scope"]="33-tap dual FIR arithmetic only; exact streaming oracle; not P&R or full receiver"
results["replaces_rtl"]=False
(OUT/"comparison.json").write_text(json.dumps(results,indent=2)+"\n")
print(json.dumps({key:value for key,value in results.items()},indent=2))
sys.exit(int(failure))
