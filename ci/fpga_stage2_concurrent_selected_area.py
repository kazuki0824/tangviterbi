"""CAD-only concurrent area screening. Unconnected blocks are NOT a receiver."""
import collections,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"build/stage2-concurrent-selected"
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
from ci.shared_receiver_fft_metadata_refresh_evidence import FILES
rs=OUT/"rs_isdb_verified.sv"
sys.path.insert(0,str(ROOT/"experiments"))
from s3_rs_isdb import source
rs.write_text(source(True,True))
sources=list(dict.fromkeys([*(str(ROOT/x) for x in FILES),
 *(str(p) for p in sorted((ROOT/"rtl").glob("s3_*.sv"))),
 *(str(ROOT/"rtl"/(n+".sv")) for n in ["dual_s3_26pin_transport_candidate","dual_s3_26pin_iq_ingress_candidate","isdb_complex_fir33","dual_s3_ingress_to_fir_candidate","isdb_serial_ts_sink","shared_rs2_dual_ts"]),
 str(rs),str(ROOT/"experiments/stage2_cocurrent_selected_subassemblies_area_top.sv")]))
top="stage2_cocurrent_selected_subassemblies_area_top"
cmd="read_verilog -sv "+" ".join(sources)+"; hierarchy -check -top "+top+"; synth_gowin -family gw2a -top "+top+" -nowidelut -json "+str(OUT/"mapped.json")+"; check -assert"
p=subprocess.run(["yosys","-Q","-p",cmd],cwd=ROOT/"reports/pr7-fft-archive",capture_output=True,text=True)
(OUT/"yosys.log").write_text(p.stdout+"\n"+p.stderr)
res={"scope":"three disconnected actual subassemblies with scan fixture, NOT full demodulator, no physical P&R",
"synthesis_exit":p.returncode,"full_receiver_connected":False,"estimate_complete":False,
"source_sha256":{str(Path(f).relative_to(ROOT)):hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in sources}}
if p.returncode==0:
 cells=json.loads((OUT/"mapped.json").read_text())["modules"][top]["cells"]
 c=collections.Counter(x["type"] for x in cells.values())
 res.update(mapped_logic=sum(v for k,v in c.items() if re.fullmatch(r"LUT[1-4]|ALU",k)),mapped_ff=sum(v for k,v in c.items() if k.startswith("DFF")),mapped_bsram=sum(c[k] for k in ("DPB","SDPB","DPX9B","SDPX9B")),mapped_distributed_ram=c["RAM16SDP4"],mapped_dsp=c["MULT18X18"])
else:print("Synthesis error tail:",(p.stdout+p.stderr)[-5000:])
(OUT/"result.json").write_text(json.dumps(res,indent=2)+"\n")
print(json.dumps({k:v for k,v in res.items() if k!="source_sha256"},indent=2))
sys.exit(p.returncode)
