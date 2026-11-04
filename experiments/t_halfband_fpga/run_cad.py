#!/usr/bin/env python3
"""Reproduce all four matched v2 Gowin core/probe resource comparisons.

Routing completion is recorded separately from timing-model completeness.
No headline nextpnr Fmax is promoted to a physical timing sign-off.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
import hashlib
import json
import subprocess
import time
from pathlib import Path

from coefficients import PARAMETERS, ROOT, SOURCE

PROFILE_CRITERIA = ["core_synth_exit", "probe_synth_exit", "place_and_route_exit", "routing_completion",
                    "core_four_MULT18X18", "probe_four_MULT18X18", "routed_four_MULT18X18"]
INPUT_FILES = ["run_cad.py", "coefficients.py", "resampler.sv", "fifo_resampler.sv", "probe.sv",
               "coeff_baseline.hex", "coeff_residual.hex"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, logfile, timeout):
    start = time.monotonic()
    with logfile.open("w") as output:
        try:
            code = subprocess.run(command, cwd=SOURCE, stdout=output, stderr=subprocess.STDOUT, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            code = 124
        except Exception as exc:
            output.write(str(exc))
            code = 125
    return {"command": command, "exit_code": code, "seconds": time.monotonic() - start}


def summarize(path, top):
    data = json.loads(path.read_text())
    cells = data["modules"][top]["cells"]
    counts = Counter(cell["type"] for cell in cells.values())
    bram = ["SPX9", "SDPX9B", "DPX9B", "SP", "SDP", "DP"]
    return {"sha256": sha(path), "cells_by_type": dict(sorted(counts.items())),
            "MULT18X18": counts["MULT18X18"], "BSRAM": sum(counts[k] for k in bram),
            "RAM16SDP4": counts["RAM16SDP4"],
            "explicit_DFF_cells": sum(n for k, n in counts.items() if k.startswith("DFF"))}


def profile_run(profile, fifo, directory, suite):
    spec = PARAMETERS[profile]
    key = profile + ("-fifo" if fifo else "")
    folder = directory / key
    folder.mkdir(parents=True, exist_ok=True)
    result = {"profile": profile, "fifo": fifo, "physical_timing_pass": False,
              "timing_qualification": "requires independent model-coverage audit", "stages": {}, "resources": {}}
    for stage in ["core", "probe"]:
        top = "t_diag_probe" if stage == "probe" else "t_diag_fifo_resampler" if fifo else "t_diag_resampler"
        script = folder / (stage + "-synth.ys")
        target = folder / (stage + "-mapped.json")
        params = {"L": spec["L"], "INPUT_BITS": spec["input_bits"], "OUTPUT_SHIFT": spec["output_shift"],
                  "COEFF_FILE": f'"{SOURCE / ("coeff_" + profile + ".hex")}"'}
        if stage == "probe":
            params["USE_FIFO"] = int(fifo)
        script.write_text("read_verilog -sv " + " ".join(str(SOURCE / n) for n in ["resampler.sv", "fifo_resampler.sv", "probe.sv"]) + "\n" +
                          "chparam " + " ".join(f"-set {k} {v}" for k, v in params.items()) + f" {top}\n" +
                          f"synth_gowin -top {top} -family gw2a -json {target}\ncheck -assert\n")
        result["stages"][stage + "_synth"] = run([str(suite / "bin/yosys"), "-Q", "-T", "-s", str(script)], folder / (stage + "-synth.log"), 180)
        try:
            result["resources"][stage] = summarize(target, top)
        except Exception as exc:
            result["resources"][stage] = {"status": "BLOCKED", "reason": str(exc)}
    pins = folder / "pins.cst"
    pins.write_text('IO_LOC "clk" 4;\nIO_LOC "resetn" 87;\nIO_LOC "scan_enable" 16;\nIO_LOC "scan_in" 18;\nIO_LOC "signature" 17;\n' +
                    "".join(f'IO_PORT "{p}" IO_TYPE=LVCMOS33;\n' for p in ["clk", "resetn", "scan_enable", "scan_in", "signature"]))
    command = [str(suite / "bin/nextpnr-himbaechel"), "--json", str(folder / "probe-mapped.json"),
               "--device", "GW2AR-LV18QN88C8/I7", "--vopt", "family=GW2A-18C", "--vopt", f"cst={pins}",
               "--freq", str(1080 / 7), "--seed", "1", "--report", str(folder / "pnr.json"),
               "--detailed-timing-report", "--write", str(folder / "routed.json"), "--timing-allow-fail"]
    if result["stages"]["probe_synth"]["exit_code"] == 0:
        result["stages"]["place_and_route"] = run(command, folder / "pnr.log", 600)
    else:
        result["stages"]["place_and_route"] = {"exit_code": None, "command": command, "status": "BLOCKED", "reason": "probe synthesis failed"}
    try:
        result["resources"]["routed"] = summarize(folder / "routed.json", "top")
    except Exception as exc:
        result["resources"]["routed"] = {"status": "BLOCKED", "reason": str(exc)}
    log = (folder / "pnr.log").read_text() if (folder / "pnr.log").exists() else ""
    result["route_completed"] = result["stages"]["place_and_route"]["exit_code"] == 0 and "Routing complete." in log
    if (folder / "pnr.json").exists():
        report = json.loads((folder / "pnr.json").read_text())
        result["reported_fmax_NOT_physical_signoff"] = report.get("fmax")
        result["utilization"] = report.get("utilization")
    result["checks"] = [
        {"name": stage + "_exit", "status": "PASS" if item.get("exit_code") == 0 else "BLOCKED" if item.get("exit_code") is None else "FAIL"}
        for stage, item in result["stages"].items()]
    result["checks"].append({"name": "routing_completion", "status": "PASS" if result["route_completed"] else "FAIL"})
    for stage in ["core", "probe", "routed"]:
        item = result["resources"][stage]
        result["checks"].append({"name": stage + "_four_MULT18X18", "status": "BLOCKED" if "MULT18X18" not in item else "PASS" if item["MULT18X18"] == 4 else "FAIL"})
    result["artifacts"] = {}
    for path in folder.iterdir():
        if path.name.endswith("mapped.json") or path.name == "routed.json" or path.suffix == ".log":
            packed = path.with_suffix(path.suffix + ".gz")
            packed.write_bytes(gzip.compress(path.read_bytes(), mtime=0))
            result["artifacts"][packed.name] = {"sha256": sha(packed), "uncompressed_sha256": sha(path)}
            path.unlink()
    (folder / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return key, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    directory, suite = args.output.resolve(), args.suite.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    result = {"version": 2, "non_fail_fast": True, "source_status": "new reconstructed RTL", "profiles": {},
              "physical_timing_pass": False, "receiver_adoption": False,
              "source_sha256": {},
              "tool_versions": {}, "toolchain": {"release": "2026-10-04", "archive_sha256": "8a4708629b0f0afd5a1835aca8b44d224fec5f6e544c5fd22a060ea5514f83c9"}}
    for name in INPUT_FILES:
        path = SOURCE / name
        try:
            result["source_sha256"][str(path.relative_to(ROOT))] = sha(path)
        except Exception as exc:
            result["source_sha256"][str(path.relative_to(ROOT))] = {"status": "BLOCKED", "reason": str(exc)}
    for name, option in [("yosys", "-V"), ("nextpnr-himbaechel", "--version")]:
        try:
            proc = subprocess.run([str(suite / "bin" / name), option], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
            result["tool_versions"][name] = {"exit_code": proc.returncode, "output": proc.stdout.strip()}
        except Exception as exc:
            result["tool_versions"][name] = {"status": "BLOCKED", "reason": str(exc)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(profile_run, profile, fifo, directory, suite): profile + ("-fifo" if fifo else "")
                for profile in PARAMETERS for fifo in [False, True]}
        for job in as_completed(jobs):
            try:
                key, row = job.result()
            except Exception as exc:
                key, row = jobs[job], {"status": "BLOCKED", "reason": str(exc), "route_completed": False,
                    "checks": [{"name": name, "status": "BLOCKED", "reason": str(exc)} for name in PROFILE_CRITERIA]}
            result["profiles"][key] = row
            (directory / "cad-results.json").write_text(json.dumps(result, indent=2) + "\n")
            print(key, "route completed", row.get("route_completed"), flush=True)
    result["cad_completed"] = all(row.get("route_completed") for row in result["profiles"].values())
    for fifo in [False, True]:
        suffix = "-fifo" if fifo else ""
        baseline = result["profiles"]["baseline" + suffix].get("resources", {}).get("routed", {})
        residual = result["profiles"]["residual" + suffix].get("resources", {}).get("routed", {})
        result["comparison" + suffix] = {"baseline": baseline, "residual": residual,
            "DSP_saved": baseline.get("MULT18X18", 0) - residual.get("MULT18X18", 0) if "MULT18X18" in baseline and "MULT18X18" in residual else None,
            "same_quality_contract_verified": False}
    (directory / "cad-results.json").write_text(json.dumps(result, indent=2) + "\n")
    return int(not result["cad_completed"])


if __name__ == "__main__":
    raise SystemExit(main())
