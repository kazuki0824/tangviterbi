"""Synthesize both FPGA SPI endpoints together; a partial diagnostic, never full receiver proof."""
import json,subprocess,hashlib,re,collections,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/("build/dual-endpoint-ingress-only" if "--ingress-only" in sys.argv else "build/dual-endpoint-area")
OUT.mkdir(parents=True,exist_ok=True)
import argparse
parser=argparse.ArgumentParser()
parser.add_argument("--ingress-only",action="store_true")
args=parser.parse_args()
top=("dual_s3_spi_ingress_only_area_top" if args.ingress_only else "dual_s3_spi_endpoints_area_top")
files=sorted((ROOT/"rtl").glob("s3_*.sv"))+[ROOT/("experiments/"+top+".sv")]
cmd=["yosys","-Q","-p","read_verilog -sv "+" ".join(str(x) for x in files)+"; hierarchy -check -top "+top+"; synth_gowin -family gw2a -top "+top+" -nowidelut -json "+str(OUT/"mapped.json")+"; check -assert"]
p=subprocess.run(cmd,capture_output=True,text=True)
(OUT/"yosys.log").write_text(p.stdout+"\n"+p.stderr)
result={"scope":"T/S SPI endpoint synthesis only, ingress-only cut" if args.ingress_only else "T/S SPI endpoints with reverse IQ and FFT support, full existing endpoint",
 "synthesis_exit":p.returncode,"source_sha256":{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
 "receiver_complete":False,"full_top_fit":None,"full_top_timing":None}
if p.returncode==0:
 cells=json.loads((OUT/"mapped.json").read_text())["modules"][top]["cells"]
 cnt=collections.Counter(x["type"] for x in cells.values())
 result["cells"]=dict(cnt)
 result["mapped_logic_lut_alu"]=sum(v for k,v in cnt.items() if re.fullmatch("LUT[1-4]|ALU",k))
 result["mapped_ff"]=sum(v for k,v in cnt.items() if k.startswith("DFF"))
 result["mapped_bsram"]=cnt["DPB"]+cnt["SDPB"]+cnt["DPX9B"]+cnt["SDPX9B"]
 result["mapped_distributed_ram"]=cnt["RAM16SDP4"]
 result["mapped_dsp"]=cnt["MULT18X18"]
 result["logic_with_ram_site_proxy"]=result["mapped_logic_lut_alu"]+4*cnt["RAM16SDP4"]
 result["area_class"]="synthesis only: no P&R placement and no I/O fit"
(OUT/"result.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({k:v for k,v in result.items() if k not in ("cells","source_sha256")},indent=2))
sys.exit(p.returncode)
