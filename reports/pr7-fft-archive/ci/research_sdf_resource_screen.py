#!/usr/bin/env python3
"""Measured Gowin synthesis resource *screen*, not physical receiver qualification.

Only the research FFT top is synthesized: an ideal synchronous external-delay
port with no SDRAM/PHY, RF, FEC, TS, board pin map or clock constraints.
Never promote synthesis success to routed fit/STA or full receiver adoption.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
SOURCES=[
    ROOT/"rtl/research_sdf_stage.sv",
    ROOT/"rtl/research_sdf_fft.sv",
    ROOT/"rtl/research_sdf_twiddle.sv",
    ROOT/"rtl/research_sdf_quarter_q16.hex",
]
RAM_TYPES={"DPB","SP","SDPB","SPB","BSRAM"}
DSP_TYPES={"MULT18X18","MULTALU18X18","MULTADDALU18X18","MULT36X36"}
LOGIC_TYPES={"LUT1","LUT2","LUT3","LUT4","ALU","RAM16SDP4"}

def count_cells(design):
    modules=design["modules"]
    counts=Counter()
    visiting=set()
    def visit(module, times):
        if module in visiting:
            raise ValueError(f"recursive synthesized hierarchy: {module}")
        visiting.add(module)
        for cell in modules[module].get("cells",{}).values():
            kind=cell["type"]
            if kind in modules and (kind.startswith("$paramod") or kind.startswith("research_sdf_")):
                visit(kind,times)
            else:
                counts[kind]+=times
        visiting.remove(module)
    visit("research_sdf_fft",1)
    return counts

def screen(counts,logn,exit_code):
    counts=dict(sorted(counts.items()))
    logic=sum(v for k,v in counts.items() if k in LOGIC_TYPES)
    ram=sum(v for k,v in counts.items() if k in RAM_TYPES)
    dsp=sum(v for k,v in counts.items() if k in DSP_TYPES)
    return dict(logn=logn,N=1<<logn,
      synthesized=exit_code==0,source_scope="ideal external synchronous RAM, FFT ONLY",
      primitive_counts=counts,logic_cells=logic,bsram_cells=ram,dsp_cells=dsp,
      upper_limits=dict(logic_sites=20736,bsram_blocks=46,dsp18=48),
      resource_screen=dict(logic=(logic<=20736 if exit_code==0 else None),
                           bsram=(ram<=46 if exit_code==0 else None),
                           dsp=(dsp<=48 if exit_code==0 else None)),
      **{"qualified_receiver":False,"whole_chip_STA":None,"physical_route_fit":None,
         "s3_continuous_IQ":None,"simultaneous_TS":None})

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--yosys",required=True)
    p.add_argument("--logn",type=int,choices=[11,12,13],default=13)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    sv=SOURCES[:3]
    if a.logn != 13:
        raise SystemExit("This pinned synthesis first measures the default LOGN=13 top only")
    synth=(
        "read_verilog -sv -defer "+" ".join(str(p) for p in sv)+"\n"
        
        "synth_gowin -family gw2a -top research_sdf_fft -nowidelut"
        f" -json {a.output.resolve()/'mapped.json'}\n"
        "check -assert\n"
    )
    (a.output/"synth.ys").write_text(synth)
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES}
    with (a.output/"synth.log").open("w") as logfile:
        try:
            r=subprocess.run([a.yosys,"-Q","-s",str(a.output.resolve()/"synth.ys")],
                             cwd=ROOT,stdout=logfile,stderr=subprocess.STDOUT,timeout=480)
            exit_code=r.returncode
        except subprocess.TimeoutExpired:
            exit_code=124
    design_path=a.output/"mapped.json"
    if exit_code==0 and design_path.exists():
        mapped=json.loads(design_path.read_text())
        cell_inventory={name:len(m.get("cells",{})) for name,m in mapped["modules"].items()}
        (a.output/"module-inventory.json").write_text(json.dumps(cell_inventory,indent=2)+"\n")
        counts=count_cells(mapped)
    else:
        counts={}
    result=screen(counts,a.logn,exit_code)
    result.update(tool_exit_code=exit_code,source_sha256=hashes,
                  warning="Never interpret a partial FFT technology map as an integrated 20K receiver fit or timing closure.")
    (a.output/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ("primitive_counts","source_sha256")},indent=2),flush=True)
    if exit_code:
        print((a.output/"synth.log").read_text(errors="replace")[-2800:],file=sys.stderr)
        raise SystemExit(exit_code)
    if not counts or sum(counts.values())==0 or (result["logic_cells"]==0 and result["bsram_cells"]==0 and result["dsp_cells"]==0):
        print("Unrecognized/empty cell classification: "+json.dumps(dict(counts)),file=sys.stderr)
        raise SystemExit("Synthesis resource accounting is zero/unknown; invalid fit evidence")
    # RESOURCE OVERFLOW is legitimate negative experimental evidence.
    # Do not fail the workflow for physical cost; summary records true/false.
if __name__=="__main__":
    main()
