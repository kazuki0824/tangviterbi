"""T-only 10-pin Octal RX and command/status area; partial receiver only."""
import collections, hashlib, json, re, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"build/fpga-t-octal-endpoint"
OUT.mkdir(parents=True,exist_ok=True)
files=["rtl/s3_async_fifo.sv","rtl/s3_spi_rx.sv","rtl/s3_page_guard.sv","rtl/s3_pooled_page_store.sv",
       "rtl/s3_rf_credit.sv","rtl/s3_spi_control.sv","rtl/s3_spi_t_octal_control_endpoint.sv"]
top="s3_spi_t_octal_control_endpoint"
ys="read_verilog -sv "+" ".join(str(ROOT/f) for f in files)+"; hierarchy -check -top "+top+"; synth_gowin -family gw2a -top "+top+" -nowidelut -json "+str(OUT/"mapped.json")+"; check -assert"
p=subprocess.run(["yosys","-Q","-p",ys],capture_output=True,text=True)
(OUT/"yosys.log").write_text(p.stdout+"\n"+p.stderr)
report={"scope":"T SPI2 Octal RF/control/credit only; no 16/32KiB bulk, RF demod, S, TS or physical timing",
        "top":top,"synthesis_exit":p.returncode,"receiver_approved":False,"board_pin_fit":None,
        "source_sha256":{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
if p.returncode==0:
    obj=json.loads((OUT/"mapped.json").read_text())["modules"][top]["cells"]
    counts=collections.Counter(c["type"] for c in obj.values())
    report.update(mapped_cells=dict(counts),
       mapped_logic=sum(v for k,v in counts.items() if re.fullmatch(r"LUT[1-4]|ALU",k)),
       mapped_ff=sum(v for k,v in counts.items() if k.startswith("DFF")),
       mapped_bsram=sum(counts[k] for k in ("DPB","SDPB","DPX9B","SDPX9B")),
       mapped_distributed_ram=counts["RAM16SDP4"],
       mapped_dsp=counts["MULT18X18"])
else:
    print("Synthesis failed:",p.stdout[-2000:],p.stderr[-2000:])
(OUT/"area.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps({k:v for k,v in report.items() if k not in ("source_sha256","mapped_cells")},indent=2))
sys.exit(p.returncode)
