"""Mapped area of T PAR4 and S PAR11 33tap complex FIR MACs only."""
import collections,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"build/dual-complex-fir33";OUT.mkdir(parents=True,exist_ok=True)
source=ROOT/"rtl/isdb_complex_fir33.sv";top="dual_isdb_complex_fir33"
ys=f"read_verilog -sv {source}; hierarchy -check -top {top}; synth_gowin -family gw2a -top {top} -nowidelut -json {OUT/'mapped.json'}; check -assert"
p=subprocess.run(["yosys","-Q","-p",ys],capture_output=True,text=True)
(OUT/"yosys.log").write_text(p.stdout+"\n"+p.stderr)
result={"scope":"T/S complex FIR 33-tap arithmetic only, coefficients programmable; no resampling/polyphase control, sync, equalization or full top","synthesis_exit":p.returncode,"source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"receiver_complete":False}
if p.returncode==0:
 cells=json.loads((OUT/"mapped.json").read_text())["modules"][top]["cells"]
 cnt=collections.Counter(x["type"] for x in cells.values())
 result.update(mapped_cells=dict(cnt),mapped_logic=sum(v for k,v in cnt.items() if re.fullmatch("LUT[1-4]|ALU",k)),mapped_ff=sum(v for k,v in cnt.items() if k.startswith("DFF")),mapped_bsram=sum(cnt[k] for k in ("DPB","SDPB","DPX9B","SDPX9B")),mapped_distributed_ram=cnt["RAM16SDP4"],mapped_dsp=cnt["MULT18X18"])
else:print((p.stdout+p.stderr)[-5000:])
(OUT/"area.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({k:v for k,v in result.items() if k!="mapped_cells"},indent=2))
sys.exit(p.returncode)
