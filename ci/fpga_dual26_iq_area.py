"""Synthesize a partial 34-header-signal-budget T/S raw IQ receiver boundary.
Not a full receiver: genuine ISDB demod/FEC/TS and IO STA not present.
"""
import collections,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"build/fpga-dual26-iq"
OUT.mkdir(parents=True,exist_ok=True)
files=sorted((ROOT/"rtl").glob("s3_*.sv"))+[ROOT/"rtl/dual_s3_26pin_transport_candidate.sv",ROOT/"rtl/dual_s3_26pin_iq_ingress_candidate.sv"]
top="dual_s3_26pin_iq_ingress_candidate"
script="read_verilog -sv "+" ".join(str(p) for p in files)+"; hierarchy -check -top "+top+"; synth_gowin -family gw2a -top "+top+" -nowidelut -json "+str(OUT/"mapped.json")+"; check -assert"
p=subprocess.run(["yosys","-Q","-p",script],capture_output=True,text=True)
(OUT/"yosys.log").write_text(p.stdout+"\n"+p.stderr)
res={"scope":"T 32KiB Octal, S 16KiB Octal/Quad, two native IQ unpackers, no demod/TS/physical STA",
     "synthesis_exit":p.returncode,"full_receiver_implemented":False,"partial_only":True,
     "transport_signal_pins":26,"TS_reserved_pins":6,"event_reserved_pins":2,
     "source_sha256":{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
if p.returncode==0:
 cells=json.loads((OUT/"mapped.json").read_text())["modules"][top]["cells"]
 cc=collections.Counter(c["type"] for c in cells.values())
 res.update(mapped_cells=dict(cc),mapped_logic=sum(v for k,v in cc.items() if re.fullmatch(r"LUT[1-4]|ALU",k)),mapped_ff=sum(v for k,v in cc.items() if k.startswith("DFF")),mapped_bsram=sum(cc[k] for k in ("DPB","SDPB","DPX9B","SDPX9B")),mapped_distributed_ram=cc["RAM16SDP4"],mapped_dsp=cc["MULT18X18"])
else:print("Yosys error tail:",(p.stdout+p.stderr)[-4000:])
(OUT/"result.json").write_text(json.dumps(res,indent=2)+"\n")
print(json.dumps({k:v for k,v in res.items() if k not in ("mapped_cells","source_sha256")},indent=2))
sys.exit(p.returncode)
