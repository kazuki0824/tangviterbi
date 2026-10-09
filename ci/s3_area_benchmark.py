#!/usr/bin/env python3
"""Controlled zero-DSP RS area comparison; retain failed timing evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
from s3_rs_area import source
from s3_rs_schedule import source as schedule_source


def run(command, log):
    with log.open("w") as output:
        return subprocess.run(command, cwd=ROOT, stdout=output,
                              stderr=subprocess.STDOUT, timeout=720).returncode


def synth(sources, top, directory, mem=None, narrow=False, vit=True):
    directory.mkdir(parents=True, exist_ok=True)
    commands = ["read_verilog -sv " + " ".join(map(str, sources))]
    if mem is not None:
        commands.append(f"chparam -set WITH_MEM {mem} -set WITH_VITERBI {int(vit)} -set VITERBI_ACS 32 benchmark_top")
    commands += [f"synth_gowin -top {top} -family gw1n " +
                 ("-noiopads " if mem is None else "") +
                 ("-nowidelut " if narrow else "") + f"-json {directory}/design.json",
                 f"tee -o {directory}/stat.json stat -json", "check -assert"]
    script = directory / "synth.ys"
    script.write_text("\n".join(commands) + "\n")
    if run(["yosys", "-Q", "-T", "-s", str(script)], directory / "synth.log"):
        raise RuntimeError(f"synthesis failed: {directory}")
    stat = json.loads((directory / "stat.json").read_text())
    cells = stat["design"]["num_cells_by_type"]
    return {"creator": stat["creator"], "cells": cells,
            "LUT": sum(v for k, v in cells.items() if k.startswith("LUT")),
            "ALU": cells.get("ALU", 0),
            "logic_equivalents": sum(v for k, v in cells.items()
                                     if k.startswith("LUT") or k == "ALU"),
            "FF": sum(v for k, v in cells.items() if k.startswith("DFF"))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("dual", "dual4", "shared4", "resetless", "resetless4", "shared-resetless4", "inverse4", "schedule4"))
    parser.add_argument("--frequency", type=float, default=125)
    args = parser.parse_args()
    out = Path("build/s3-area") / f"{args.kind}-{args.frequency:g}"
    out.mkdir(parents=True, exist_ok=True)
    rtl = out / "rs.sv"
    scheduled = args.kind in ("inverse4", "schedule4")
    text = schedule_source(args.kind == "schedule4") if scheduled else source(args.kind.startswith("shared"))
    if "resetless" in args.kind:
        text = text.replace("""if (!resetn) begin
                lambda[slot] <= 8'd0;
                bpoly[slot] <= 8'd0;
                temp_poly[slot] <= 8'd0;
            end else begin""", "if (resetn) begin")
        text = text.replace("""for (slot=0; slot<9; slot=slot+1) begin : g_polynomial
        always @(posedge clk or negedge resetn)""", """for (slot=0; slot<9; slot=slot+1) begin : g_polynomial
        always @(posedge clk)""")
    rtl.write_text(text)
    narrow = args.kind.endswith("4")
    bound = 2758 if args.kind == "schedule4" else 3166 if scheduled else 3502
    floor = bound * 6.52125 / 188
    result = {"kind": args.kind, "rtl_sha256": hashlib.sha256(rtl.read_bytes()).hexdigest(),
              "scope": "Partial FEC + protocol controller benchmark, not a receiver",
              "RS_conservative_cycles": bound,
              "receiver_RS_minimum_MHz": {"T": bound * 2.90433749 / 188, "S": floor},
              "bounded_uncorrectable_degree": scheduled,
              "constraint_MHz": args.frequency, "seed": 1}
    extra = (["--inverse-saving", "14", "--chien-saving", "408" if args.kind == "schedule4" else "0",
              "--max-cycles", str(bound)] if scheduled else [])
    if run([sys.executable, "experiments/compare_rs.py", "--rtl", str(rtl),
            "--syndrome-cycles", "0", *extra], out / "tests.log"):
        raise RuntimeError("candidate equivalence/arithmetic/service checks failed")
    if scheduled:
        executable = out / "schedule-test"
        if run(["iverilog", "-g2012", "-s", "rs_schedule_tb", "-o", str(executable),
                f"-Prs_schedule_tb.FAST_CHIEN={int(args.kind == 'schedule4')}",
                str(rtl), "tests/rs_schedule_tb.sv"], out / "schedule-compile.log") or run(
                    ["vvp", str(executable)], out / "schedule-tests.log"):
            raise RuntimeError("inverse ROM, Chien scheduling or early-fail test failed")
    result["RS"] = synth([rtl], "rs204_188_compact", out / "rs-module", narrow=narrow)
    result["Viterbi"] = synth(["rtl/viterbi_k7_32acs.sv"], "viterbi_k7_32acs", out / "vit-module", narrow=narrow)
    result["routed"] = {}
    for name, mem in (("core", 0), ("mem", 1), ("rs-clock", 0)):
        d = out / name
        counts = synth(["rtl/viterbi_k7_16acs.sv", "rtl/viterbi_k7_32acs.sv", rtl,
                        "rtl/psram_ctrl.sv", "rtl/benchmark_top.sv"], "benchmark_top", d, mem,
                       narrow=narrow, vit=name != "rs-clock")
        rc = run(["nextpnr-himbaechel", "--json", str(d / "design.json"),
                  "--write", str(d / "routed.json"), "--device", "GW1NR-LV9QN88PC6/I5",
                  "--vopt", "family=GW1N-9C", "--vopt", "cst=constraints/tangnano9k.cst",
                  "--freq", str(args.frequency), "--seed", "1", "--report", str(d / "report.json")],
                 d / "pnr.log")
        log = (d / "pnr.log").read_text()
        routed = log.partition("Routing complete")[2]
        clocks = [float(x) for x in re.findall(
            r"Max frequency for clock '[^']+':\s*([0-9.]+)\s*MHz", routed)]
        packed = {k: int(v) for k, v in re.findall(
            r"Info:\s+([A-Za-z0-9_]+):\s+(\d+)/\s*\d+\s+\d+%", log)}
        fmax = min(clocks) if clocks else None
        result["routed"][name] = {"synthesis": counts, "packed": packed,
            "exit_code": rc, "routing_complete": bool(routed), "Fmax_MHz": fmax,
            "meets_125_MHz": fmax is not None and fmax >= 125,
            "meets_constraint_MHz": fmax is not None and fmax >= args.frequency,
            "meets_receiver_RS_S_floor": fmax is not None and fmax >= floor}
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    # This is a measurement job: incomplete CAD and arithmetic errors fail it;
    # expected missed timing targets remain explicit results, never green timing.
    if any(not x["routing_complete"] or x["Fmax_MHz"] is None
           for x in result["routed"].values()):
        raise SystemExit("incomplete P&R measurement")


if __name__ == "__main__":
    main()
