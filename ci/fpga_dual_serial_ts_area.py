"""Synthesize real T/S serial TS sinks; partial resource figure only."""
import collections,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"build/serial-ts";OUT.mkdir(parents=True,exist_ok=True)
source=ROOT/"rtl/isdb_serial_ts_sink.sv"
script=f"read_verilog -sv {source}; hierarchy -check -top dual_isdb_serial_ts_sinks; synth_gowin -family gw2a -top dual_isdb_serial_ts_sinks -nowidelut -json {OUT/'mapped.json'}; check -assert"
p=subprocess.run(["yosys","-Q","-p",script],capture_output=True,text=True)
(OUT/"yosys.log").write_text(p.stdout+"\n"+p.stderr)
result={"scope":"dual serial TS sinks only; does not contain RS, demod, board pins or PHY","source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),"synthesis_exit":p.returncode}
if p.returncode==0:
 cells=json.loads((OUT/"mapped.json").read_text())["modules"]["dual_isdb_serial_ts_sinks"]["cells"]
 c=collections.Counter(x["type"] for x in cells.values())
 result.update(mapped_logic=sum(v for k,v in c.items() if re.fullmatch("LUT[1-4]|ALU",k)),mapped_ff=sum(v for k,v in c.items() if k.startswith("DFF")),mapped_bsram=sum(c[k] for k in ("DPB","SDPB","DPX9B","SDPX9B")),mapped_distributed_ram=c["RAM16SDP4"],mapped_dsp=c["MULT18X18"])
else:print((p.stdout+p.stderr)[-3000:])
(OUT/"area.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result,indent=2))
sys.exit(p.returncode)
