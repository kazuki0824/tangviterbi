"""Mapped area of T/S 26-pin SPI transport, two native IQ unpackers,
and real parallel complex FIR MAC. Incomplete receiver: resampler/sync/FFT,
interleavers/RS/TS and board timing NOT connected.
"""
import collections,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"build/dual-ingress-fir33";OUT.mkdir(parents=True,exist_ok=True)
files=sorted((ROOT/"rtl").glob("s3_*.sv"))+[ROOT/f"rtl/{name}.sv" for name in (
"dual_s3_26pin_transport_candidate","dual_s3_26pin_iq_ingress_candidate","isdb_complex_fir33","dual_s3_ingress_to_fir_candidate")]
top="dual_s3_ingress_to_fir_candidate"
ys="read_verilog -sv "+" ".join(str(f) for f in files)+f"; hierarchy -check -top {top}; synth_gowin -family gw2a -top {top} -nowidelut -json {OUT/'mapped.json'}; check -assert"
p=subprocess.run(["yosys","-Q","-p",ys],capture_output=True,text=True)
(OUT/"yosys.log").write_text(p.stdout+"\n"+p.stderr)
result={"scope":"T/S transport+IQ unpack+complex FIR 33tap MAC only; no resampling/polyphase, actual symbol sync, FFT, interleaving, RS, TS, pin P&R",
        "synthesis_exit":p.returncode,"receiver_complete":False,
        "source_sha256":{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
if p.returncode==0:
 cells=json.loads((OUT/"mapped.json").read_text())["modules"][top]["cells"]
 c=collections.Counter(v["type"] for v in cells.values())
 result.update(mapped_logic=sum(v for k,v in c.items() if re.fullmatch("LUT[1-4]|ALU",k)),mapped_ff=sum(v for k,v in c.items() if k.startswith("DFF")),mapped_bsram=sum(c[k] for k in ("DPB","SDPB","DPX9B","SDPX9B")),mapped_distributed_ram=c["RAM16SDP4"],mapped_dsp=c["MULT18X18"],mapped_cells=dict(c))
else:print("Yosys error:",(p.stdout+p.stderr)[-4000:])
(OUT/"result.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps({k:v for k,v in result.items() if k not in ("source_sha256","mapped_cells")},indent=2))
sys.exit(p.returncode)
