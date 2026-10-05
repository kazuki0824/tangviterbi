"""Compare official/control/diagnostic P&R before accepting extra setup paths."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess


def run_pnr(command, cwd, output):
    env = dict(os.environ)
    env.pop("NEXTPNR_ENDPOINT_DIAGNOSTICS", None)
    with output.open("w") as log:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=log,
                                stderr=subprocess.STDOUT, timeout=900)
    text = output.read_text()
    if result.returncode not in (0, 1) or "Routing complete" not in text:
        raise RuntimeError(f"P&R did not complete: {output}, exit {result.returncode}")
    return text, result.returncode


def collect_endpoints(log, report):
    final = log.partition("Routing complete")[2]
    matches = re.findall(
        r"Endpoint diagnostic rank=(\d+) cell=(\S+) port=(\S+) setup_slack_ns=([-\d.eE]+)",
        final,
    )
    if len(matches) != 32:
        raise ValueError(f"Expected 32 final endpoint records, got {len(matches)}")
    paths = {}
    for path in report["critical_paths"]:
        endpoint = path["path"][-1]["to"]
        paths[(endpoint["cell"], endpoint["port"])] = path
    records = []
    for rank, cell, port, slack in matches:
        path = paths[(cell, port)]
        totals = {}
        for segment in path["path"]:
            totals[segment["type"]] = totals.get(segment["type"], 0) + segment["delay"]
        records.append({"rank": int(rank), "cell": cell, "port": port,
                        "engine_setup_slack_ns": float(slack),
                        "endpoint_loc": path["path"][-1]["to"]["loc"],
                        "launch": path["path"][0]["from"],
                        "reported_path_sum_ns": sum(totals.values()),
                        "segment_totals_ns": totals, "complete_path": path})
    if len({(r["cell"], r["port"]) for r in records}) != 32:
        raise ValueError("Duplicate diagnostic endpoints")
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--instrumented-nextpnr", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("build/endpoint-diagnostics"))
    args = parser.parse_args()
    repo = Path.cwd()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    instrumented = args.instrumented_nextpnr.resolve()
    official = shutil.which("nextpnr-himbaechel")
    if not official:
        raise RuntimeError("Pinned OSS CAD Suite is not on PATH")

    def measure(variant):
        label = variant.split("-")[0]
        case = output / variant
        case.mkdir(exist_ok=True)
        for folder in ("rtl", "ci", "constraints", "experiments"):
            shutil.copytree(repo / folder, case / folder, dirs_exist_ok=True)
        (case / "build").mkdir(exist_ok=True)
        # Frequency is a nextpnr constraint, not part of this synthesis script.
        script = repo / "reports/survivor-prefetch" / f"{label}-65-seed1.synth.ys"
        if not script.is_file():
            raise FileNotFoundError(f"Missing recorded synthesis script: {script}")
        with (case / "synth.log").open("w") as log:
            subprocess.run(["yosys", "-s", str(script)], cwd=case, stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=900)
        common = ["--json", "build/design.json", "--device", "GW1NR-LV9QN88PC6/I5",
                  "--vopt", "family=GW1N-9C", "--vopt", "cst=constraints/tangnano9k.cst",
                  "--freq", "110", "--seed", "1"]
        modes = (("official", official), ("control", str(instrumented)),
                 ("diagnostic", str(instrumented)))
        logs, reports, exits, physical = {}, {}, {}, {}
        for name, binary in modes:
            report_path = case / f"{name}.json"
            routed_path = case / f"{name}.routed.json"
            command = [binary, *common, "--report", str(report_path),
                       "--write", str(routed_path), "--detailed-timing-report"]
            logs[name], exits[name] = run_pnr(command, case, case / f"{name}.log")
            reports[name] = json.loads(report_path.read_text())
            routed = json.loads(routed_path.read_text())
            physical[name] = {module: {field: data[field] for field in ("ports", "cells", "netnames")}
                              for module, data in routed["modules"].items()}
        checksums = {name: re.findall(r"Checksum: 0x([0-9a-f]+)", log)
                     for name, log in logs.items()}
        if any(len(c) != 3 for c in checksums.values()):
            raise ValueError("Missing physical P&R checksums")
        if not physical["official"] == physical["control"] == physical["diagnostic"]:
            raise ValueError(f"Routed cells/nets/ports differ: {checksums}")
        if checksums["control"] != checksums["diagnostic"]:
            raise ValueError(f"Compiled/diagnostic checksum changed: {checksums}")
        for key in ("fmax", "utilization", "detailed_net_timings"):
            if not reports["official"][key] == reports["control"][key] == reports["diagnostic"][key]:
                raise ValueError(f"Diagnostic changed {key}")
        if not (reports["official"]["critical_paths"] ==
                reports["control"]["critical_paths"][:1] ==
                reports["diagnostic"]["critical_paths"][:1]):
            raise ValueError("Instrumented run changed the primary critical path")
        if reports["control"]["critical_paths"] != reports["diagnostic"]["critical_paths"]:
            raise ValueError("Diagnostic and compiled control paths differ")
        records = collect_endpoints(logs["diagnostic"], reports["diagnostic"])
        canonical = json.dumps(physical["official"], sort_keys=True, separators=(",", ":"))
        summary = {"variant": variant, "physical_checksums": checksums,
                   "routed_cells_nets_ports_equal": True,
                   "routed_cells_nets_ports_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
                   "official_control_diagnostic_timing_equal": True,
                   "netlist_sha256": hashlib.sha256((case / "build/design.json").read_bytes()).hexdigest(),
                   "exit_codes": exits, "fmax": reports["official"]["fmax"], "endpoints": records}
        (case / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps({"variant": variant, "fmax": summary["fmax"], "endpoints": len(records),
                          "physical_checksums": summary["physical_checksums"],
                          "physical_sha256": summary["routed_cells_nets_ports_sha256"]}), flush=True)
        return summary

    with ThreadPoolExecutor(max_workers=2) as pool:
        summaries = list(pool.map(measure, ("core-32acs-rsconst", "mem-32acs-rsconst")))
    (output / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")


if __name__ == "__main__":
    main()
