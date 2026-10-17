#!/usr/bin/env python3
"""Measure one shared FFT block; never certify an integrated receiver."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "reports/pr7-fft-archive"
SOURCES = [ROOT/"rtl/shared_sdf_fft.sv", ROOT/"experiments/shared_sdf_benchmark.sv",
           ARCHIVE/"rtl/research_sdf_twiddle.sv", ARCHIVE/"rtl/research_sdf_quarter_q16.hex"]


def inventory(design):
    counts = Counter()
    def visit(name):
        for cell in design["modules"][name].get("cells", {}).values():
            kind = cell["type"]
            module = design["modules"].get(kind)
            if module and not module.get("attributes", {}).get("blackbox"):
                visit(kind)
            else:
                counts[kind] += 1
    visit("shared_sdf_benchmark")
    return dict(sorted(counts.items()))


def run(cmd, cwd, path, timeout):
    with path.open("w") as log:
        try:
            return subprocess.run(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                  timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            return 124


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", choices=("9k", "20k"), required=True)
    parser.add_argument("--resident", action="store_true")
    parser.add_argument("--pnr", action="store_true")
    parser.add_argument("--frequency", type=float, default=110)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for name in ("mapped.json","routed.json","pnr.json","summary.json"):
        (out/name).unlink(missing_ok=True)
    family = "gw1n" if args.board == "9k" else "gw2a"
    script = "read_verilog -sv " + " ".join(str(p) for p in SOURCES[:3]) + "\n"
    script += f"chparam -set EXTERNAL_FIRST {int(not args.resident)} shared_sdf_benchmark\n"
    script += f"synth_gowin -family {family} -top shared_sdf_benchmark -nowidelut -json {out/'mapped.json'}\ncheck -assert\n"
    (out/"synth.ys").write_text(script)
    code = run(["yosys", "-Q", "-s", str(out/"synth.ys")], ARCHIVE, out/"synth.log", 600)
    counts = inventory(json.loads((out/"mapped.json").read_text())) if code == 0 else {}
    result = dict(board=args.board, external_first=not args.resident,
                  scope="shared FFT with signature harness; no receiver, PHY or board I/O closure",
                  tool_version=subprocess.check_output(["yosys", "-V"], text=True).strip(),
                  synth_exit=code, primitive_counts=counts,
                  lut_cells=sum(v for k,v in counts.items() if re.fullmatch(r"LUT[1-4]",k)),
                  alu_cells=counts.get("ALU",0),
                  ff_cells=sum(v for k,v in counts.items() if k.startswith("DFF")),
                  bsram=sum(v for k,v in counts.items() if k in {"DPB","DPX9B","SP","SPX9","SDPB","SDPX9B","SPB"}),
                  dsp18=counts.get("MULT18X18",0),
                  source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES},
                  qualified_receiver=False, whole_receiver_STA=None)
    if args.pnr and code == 0:
        device,fam,pin = (("GW1NR-LV9QN88PC6/I5","GW1N-9C",52) if args.board=="9k" else
                          ("GW2AR-LV18QN88C8/I7","GW2A-18C",4))
        # A test harness pin assignment, explicitly not the receiver wiring.
        pins = ([35,25,26,27,28,29,30,33,34,40,36,41,42,51,53,54,55,56,57,37,38,31,32,48,49]
                if args.board=="9k" else
                [73,74,75,85,77,15,16,27,28,25,26,29,30,31,17,20,19,18,76,80,42,41,56,54,51])
        signals = ["resetn","in_valid","out_ready","external_ready","mode[0]","mode[1]"]
        signals += [f"stimulus[{j}]" for j in range(8)]
        signals += [f"signature[{j}]" for j in range(8)]
        signals += ["in_ready","out_valid","overflow"]
        assert len(signals)==len(pins) and pin not in pins
        (out/"clock.cst").write_text("".join(
            f'IO_LOC "{s}" {p};\nIO_PORT "{s}" IO_TYPE=LVCMOS33;\n'
            for s,p in [("clk",pin),*zip(signals,pins)]))
        cmd = ["nextpnr-himbaechel", "--json", str(out/"mapped.json"), "--device",device,
               "--vopt",f"family={fam}","--vopt",f"cst={out/'clock.cst'}",
               "--freq",str(args.frequency),"--seed","1",
               "--report",str(out/"pnr.json"),"--write",str(out/"routed.json")]
        (out/"pnr-command.json").write_text(json.dumps(cmd,indent=2)+"\n")
        result["pnr_exit"] = run(cmd, ROOT, out/"pnr.log", 600)
        log = (out/"pnr.log").read_text(errors="replace")
        result["pnr_errors"] = [line for line in log.splitlines() if line.upper().startswith("ERROR:")]
        result["route_completed"] = "Routing complete." in log
        result["reported_fmax_mhz"] = re.findall(r"Max frequency.*?: ([0-9.]+) MHz",log)
        result["timing_limitations"] = [line for line in log.splitlines()
                                        if "timing" in line.lower() and any(
                                            s in line.lower() for s in ("no ","missing","unknown","unmodel"))]
        result["timing_target_pass"] = result["pnr_exit"]==0 and result["route_completed"] and not result["pnr_errors"]
        result["pnr_tool_version"] = subprocess.check_output(
            ["nextpnr-himbaechel","--version"],stderr=subprocess.STDOUT,text=True).strip()
        if (out/"pnr.json").exists():
            pnr = json.loads((out/"pnr.json").read_text())
            result["routed_utilization"] = pnr.get("utilization",{})
            result["routed_fmax"] = pnr.get("fmax",{})
            use = result["routed_utilization"]
            result["routed_logic_positions"] = sum(use.get(k,{}).get("used",0) for k in ("LUT4","ALU"))
        result["frequency_target_mhz"] = args.frequency
        result["external_IO_delays_constrained"] = False
    (out/"summary.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
