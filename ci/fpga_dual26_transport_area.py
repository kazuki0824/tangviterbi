"""Stage-2 T/S 26-connector-line transport integration area estimate.
The demodulator and TS sinks are NOT implemented; this is a component probe.
"""
import collections,hashlib,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"build/fpga-dual26-transport"
OUT.mkdir(parents=True,exist_ok=True)
files=sorted((ROOT/"rtl").glob("s3_*.sv"))+[ROOT/"rtl/dual_s3_26pin_transport_candidate.sv"]
top="dual_s3_26pin_transport_candidate"
text="read_verilog -sv "+" ".join(str(p) for p in files)+"; hierarchy -check -top "+top+"; synth_gowin -family gw2a -top "+top+" -nowidelut -json "+str(OUT/"mapped.json")+"; check -assert"
p=subprocess.run(["yosys","-Q","-p",text],capture_output=True,text=True)
(OUT/"yosys.log").write_text(p.stdout+"\n"+p.stderr)
source=(ROOT/"rtl/dual_s3_26pin_transport_candidate.sv").read_text()
pin_checks={
 "T Octal only":all(v in source for v in ("input wire t_spi2_clk,t_spi2_cs_n,inout wire [7:0] t_spi2_d", "s3_spi_t_octal_control_endpoint t")),
 "S Octal and Quad":all(v in source for v in ("input wire s_spi2_clk,s_spi2_cs_n,input wire [7:0] s_spi2_d", "input wire s_spi3_clk,s_spi3_cs_n,inout wire [3:0] s_spi3_d")),
 "external independent credits omitted":"output wire [2:0] RF_credit_gray" not in source and "output wire [5:0] RF_credit_gray" not in source,
 "no full TS claims":"No RF demod, TS sink" in source,
}
report={"area_scope":"T/S physical SPI transport only; RF outputs are internal interface placeholders for future demod stages",
 "synthesis_exit":p.returncode,"pin_checks":pin_checks,"transport_physical_pins":10+16,
 "reserved_ts_pins":6,"reserved_event_pins":2,"total_planned":34,
 "full_receiver_area":None,"board_pin_cst_pass":False,
 "source_sha256":{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
if p.returncode==0:
 obj=json.loads((OUT/"mapped.json").read_text())["modules"][top]["cells"]
 cnt=collections.Counter(v["type"] for v in obj.values())
 report.update(mapped_logic=sum(v for k,v in cnt.items() if re.fullmatch(r"LUT[1-4]|ALU",k)),
               mapped_ff=sum(v for k,v in cnt.items() if k.startswith("DFF")),
               mapped_bsram=sum(cnt[k] for k in ("DPB","SDPB","DPX9B","SDPX9B")),
               mapped_distributed_ram=cnt["RAM16SDP4"],mapped_dsp=cnt["MULT18X18"])
else: print("Yosys failure tail:",p.stdout[-4000:],p.stderr[-3000:])
(OUT/"result.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps({k:v for k,v in report.items() if k!="source_sha256"},indent=2))
sys.exit(int(p.returncode!=0 or not all(pin_checks.values())))
