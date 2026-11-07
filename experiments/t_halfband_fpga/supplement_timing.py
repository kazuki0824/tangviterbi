#!/usr/bin/env python3
"""Route the retained residual probe with the fixed 2026-11-03 CAD suite.

The four retained 2026-10-04 resource results remain unchanged. This is a fresh
supplemental route of their exact residual probe and pins, followed by model
coverage inspection. Timing failure is a candidate finding, not a tool failure.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).resolve().parent
COMMIT = "a2c6479977d64d312686d853a93941744fdbeacf"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def evaluate(suite, source, output, cache):
    folder = output / "residual-fifo"; folder.mkdir(parents=True, exist_ok=True)
    result = {"schema_version": 1, "evidence_origin": "Fresh supplemental route and coverage inspection",
              "non_fail_fast": True, "physical_timing_pass": False, "checks": [], "input_sha256": {},
              "source_sha256": {}, "toolchain": {"release": "2026-11-03", "nextpnr_commit": COMMIT,
                "archive_url": "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2026-11-03/oss-cad-suite-linux-x64-20261103.tgz",
                "archive_sha256": "f991f2b5a8204028100cf3ad2d14d97c005ce14b903b50edf71399da99b417ed"}}
    def check(name, fn):
        try: result["checks"].append({"name": name, "status": "PASS" if fn() else "FAIL"})
        except Exception as exc: result["checks"].append({"name": name, "status": "BLOCKED", "reason": f"{type(exc).__name__}: {exc}"})
    for name in ("supplement_timing.py", "timing_coverage.py"):
        try: result["source_sha256"]["experiments/t_halfband_fpga/" + name] = sha((SOURCE / name).read_bytes())
        except Exception as exc: result["source_sha256"]["experiments/t_halfband_fpga/" + name] = {"status": "BLOCKED", "reason": str(exc)}
    # These are generated files belonging to this output directory. Clear only
    # them so a missing tool/input cannot masquerade as a fresh successful run.
    for name in ("pnr.log", "pnr.log.gz", "pnr.json", "routed.json", "routed.json.gz", "probe-mapped.json"):
        (folder / name).unlink(missing_ok=True)
    available = {}
    for name in ("probe-mapped.json.gz", "pins.cst"):
        try:
            data = (source / name).read_bytes(); (folder / name).write_bytes(data)
            result["input_sha256"][name] = sha(data); available[name] = True
            if name.endswith(".gz"):
                (folder / "probe-mapped.json").write_bytes(gzip.decompress(data))
            result["checks"].append({"name": "input_available." + name, "status": "PASS"})
        except Exception as exc:
            available[name] = False
            result["checks"].append({"name": "input_available." + name, "status": "BLOCKED", "reason": str(exc)})
    command = [str(suite / "bin/nextpnr-himbaechel"), "--json", str(folder / "probe-mapped.json"),
               "--device", "GW2AR-LV18QN88C8/I7", "--vopt", "family=GW2A-18C", "--vopt", f"cst={folder / 'pins.cst'}",
               "--freq", str(1080 / 7), "--seed", "1", "--report", str(folder / "pnr.json"),
               "--detailed-timing-report", "--write", str(folder / "routed.json"), "--timing-allow-fail"]
    result["place_and_route"] = {"command": command}
    try:
        if not all(available.values()):
            raise RuntimeError("One or more route inputs are unavailable")
        with (folder / "pnr.log").open("w") as log:
            proc = subprocess.run(command, cwd=SOURCE, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        result["place_and_route"]["exit_code"] = proc.returncode
    except Exception as exc: result["place_and_route"].update(status="BLOCKED", reason=str(exc))
    check("place_and_route_exit", lambda: result["place_and_route"]["exit_code"] == 0)
    check("route_completion_log", lambda: "Routing complete." in (folder / "pnr.log").read_text())
    try:
        data = (folder / "routed.json").read_bytes()
        cells = json.loads(data)["modules"]["top"]["cells"]
        counts = Counter(c["type"] for c in cells.values())
        result["resources"] = {"cells_by_type": dict(sorted(counts.items())), "MULT18X18": counts["MULT18X18"],
            "BSRAM": sum(counts[k] for k in ("SPX9", "SDPX9B", "DPX9B", "SP", "SDP", "DP")),
            "RAM16SDP4": counts["RAM16SDP4"], "explicit_DFF_cells": sum(v for k, v in counts.items() if k.startswith("DFF"))}
        result["checks"].append({"name": "routed_resources_readable", "status": "PASS"})
    except Exception as exc:
        result["resources"] = {"status": "BLOCKED", "reason": str(exc)}
        result["checks"].append({"name": "routed_resources_readable", "status": "BLOCKED", "reason": str(exc)})
    check("routed_four_DSP", lambda: result["resources"]["MULT18X18"] == 4)
    check("routed_three_BSRAM", lambda: result["resources"]["BSRAM"] == 3)
    try:
        pnr = json.loads((folder / "pnr.json").read_text())
        if not pnr["fmax"]:
            raise ValueError("No modeled clock results were reported")
        if not all(math.isfinite(x[k]) and x[k] > 0 for x in pnr["fmax"].values() for k in ("achieved", "constraint")):
            raise ValueError("A modeled clock result is nonfinite or nonpositive")
        result["reported_fmax_NOT_physical_signoff"] = pnr["fmax"]
        result["modeled_clock_results"] = {name: {**x, "status": "PASS" if x["achieved"] >= x["constraint"] else "REJECT"}
                                            for name, x in pnr["fmax"].items()}
        result["modeled_target_timing"] = "PASS" if all(x["achieved"] >= x["constraint"] for x in pnr["fmax"].values()) else "REJECT"
        result["checks"].append({"name": "modeled_clock_result_readable", "status": "PASS"})
    except Exception as exc:
        result["modeled_target_timing"] = "UNVERIFIED"
        result["checks"].append({"name": "modeled_clock_result_readable", "status": "BLOCKED", "reason": str(exc)})
    for name in ("pnr.log", "routed.json"):
        path = folder / name
        if path.exists():
            path.with_suffix(path.suffix + ".gz").write_bytes(gzip.compress(path.read_bytes(), mtime=0)); path.unlink()
    (folder / "probe-mapped.json").unlink(missing_ok=True)
    coverage = [sys.executable, str(SOURCE / "timing_coverage.py"), "--suite", str(suite),
                "--source-cache", str(cache), "--commit", COMMIT, "--cad", str(output),
                "--profiles", "residual-fifo", "--output", str(output / "timing")]
    result["coverage_run"] = {"command": coverage}
    try:
        with (output / "coverage.log").open("w") as log:
            proc = subprocess.run(coverage, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        result["coverage_run"]["exit_code"] = proc.returncode
    except Exception as exc: result["coverage_run"].update(status="BLOCKED", reason=str(exc))
    check("coverage_inspection_exit", lambda: result["coverage_run"]["exit_code"] == 0)
    result["artifacts"] = {}
    for relative in ("residual-fifo/probe-mapped.json.gz", "residual-fifo/pins.cst", "residual-fifo/pnr.json",
                     "residual-fifo/pnr.log.gz", "residual-fifo/routed.json.gz", "timing/timing-coverage.json.gz"):
        try: result["artifacts"][relative] = {"sha256": sha((output / relative).read_bytes())}
        except Exception as exc: result["artifacts"][relative] = {"status": "BLOCKED", "reason": str(exc)}
    result["status"] = "PASS" if all(c["status"] == "PASS" for c in result["checks"]) else "FAIL"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True); parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--source-cache", type=Path, required=True)
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    result = evaluate(args.suite.resolve(), args.input.resolve(), args.output.resolve(), args.source_cache.resolve())
    (args.output / "supplement-results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "modeled_target_timing": result["modeled_target_timing"],
                      "checks": dict(Counter(c["status"] for c in result["checks"]))}))
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
