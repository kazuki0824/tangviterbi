"""Mapped resource count for one real independently vector-tested RS decoder,
a 2-source codeword arbiter, and two independent serial TS pin sinks.
This is NOT a full ISDB-T/S receiver and does not provide PHY STA.
"""
import collections,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"build/shared-rs-dual-ts"
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/"experiments"))
from s3_rs_isdb import source
rs_source=OUT/"rs_isdb_verified.sv"
rs_source.write_text(source(True,True))
files=[rs_source,ROOT/"rtl/isdb_serial_ts_sink.sv",ROOT/"rtl/shared_rs2_dual_ts.sv"]
top="shared_rs2_dual_ts"
script="read_verilog -sv "+" ".join(str(x) for x in files)+f"; hierarchy -check -top {top}; synth_gowin -family gw2a -top {top} -nowidelut -json {OUT/'mapped.json'}; check -assert"
p=subprocess.run(["yosys","-Q","-p",script],capture_output=True,text=True)
(OUT/"yosys.log").write_text(p.stdout+"\n"+p.stderr)
report={"scope":"Shared corrected RS(204,188) one engine, two codeword sources, two 3-wire TS output FIFOs; missing RF frontend, inner FEC, interleave, full memory/PHY",
        "full_receiver_implemented":False,"synthesis_exit":p.returncode,
        "source_sha256":{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
if p.returncode==0:
 cells=json.loads((OUT/"mapped.json").read_text())["modules"][top]["cells"]
 cnt=collections.Counter(x["type"] for x in cells.values())
 report.update(mapped_logic=sum(v for k,v in cnt.items() if re.fullmatch(r"LUT[1-4]|ALU",k)),mapped_ff=sum(v for k,v in cnt.items() if k.startswith("DFF")),mapped_bsram=sum(cnt[k] for k in ("DPB","SDPB","DPX9B","SDPX9B")),mapped_distributed_ram=cnt["RAM16SDP4"],mapped_dsp=cnt["MULT18X18"],mapped_cells=dict(cnt))
else:print("Yosys error tail:",(p.stdout+p.stderr)[-4000:])
(OUT/"area.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps({k:v for k,v in report.items() if k not in ("mapped_cells","source_sha256")},indent=2))
sys.exit(p.returncode)
