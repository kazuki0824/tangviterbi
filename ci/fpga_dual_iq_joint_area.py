"""Measure bit-exact ingress-connected 2-S3 endpoint co-residency with FFT/K7.
The FFT/K7 subassembly is independent: NOT a full receiver resource number.
"""
import json,hashlib,collections,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"build/dual-iq-ingress-joint-fft"
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
from ci.shared_receiver_fft_metadata_refresh_evidence import FILES
files=list(dict.fromkeys([*FILES,
    *[str(f.relative_to(ROOT)) for f in sorted((ROOT/"rtl").glob("s3_*.sv"))],
    "experiments/dual_s3_spi_ingress_only_area_top.sv",
    "experiments/dual_s3_iq_ingress_joint_fft_area_top.sv"]))
top="dual_s3_iq_ingress_joint_fft_area_top"
script="read_verilog -sv "+" ".join(str(ROOT/f) for f in files)+"; hierarchy -check -top "+top+"; synth_gowin -family gw2a -top "+top+" -nowidelut -json "+str(OUT/"mapped.json")+"; check -assert"
p=subprocess.run(["yosys","-Q","-p",script],cwd=ROOT/"reports/pr7-fft-archive",capture_output=True,text=True)
(OUT/"yosys.log").write_text(p.stdout+"\n"+p.stderr)
if p.returncode:print("Yosys failure tail:",(p.stdout+"\n"+p.stderr)[-6500:],flush=True)
result=dict(scope="two SPI endpoints connected to two lossless I10/Q10 unpackers; FFT/K7 independently driven; no complete demod/TS",synthesis_exit=p.returncode,full_receiver_implemented=False,full_top_area_verified=False,source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files})
if p.returncode==0:
    cells=json.loads((OUT/"mapped.json").read_text())["modules"][top]["cells"]
    cnt=collections.Counter(x["type"] for x in cells.values())
    result.update(cell_types=dict(cnt),mapped_logic_lut_alu=sum(v for k,v in cnt.items() if re.fullmatch(r"LUT[1-4]|ALU",k)),mapped_ff=sum(v for k,v in cnt.items() if k.startswith("DFF")),mapped_bsram=sum(cnt[k] for k in ("DPB","SDPB","DPX9B","SDPX9B")),mapped_distributed_ram=cnt["RAM16SDP4"],mapped_dsp=cnt["MULT18X18"])
    result["logic_ram_site_proxy"]=result["mapped_logic_lut_alu"]+4*result["mapped_distributed_ram"]
(OUT/"result.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({k:v for k,v in result.items() if k not in ("cell_types","source_sha256")},indent=2))
sys.exit(p.returncode)
