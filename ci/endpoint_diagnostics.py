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
                        "target_110mhz_margin_ns": 1000 / 110 + float(slack),
                        "endpoint_loc": path["path"][-1]["to"]["loc"],
                        "launch": path["path"][0]["from"],
                        "reported_path_sum_ns": sum(totals.values()),
                        "segment_totals_ns": totals, "complete_path": path})
    if len({(r["cell"], r["port"]) for r in records}) != 32:
        raise ValueError("Duplicate diagnostic endpoints")
    return records


def compare_routed_semantics(reference, candidate):
    """Match every named net bit, cell pin and route despite renamed numeric IDs."""
    if reference["modules"].keys() != candidate["modules"].keys():
        raise ValueError("Routed module names differ")
    counts = {}
    for module, a in reference["modules"].items():
        b = candidate["modules"][module]
        for field in ("attributes", "ports", "cells", "netnames"):
            if a[field].keys() != b[field].keys():
                raise ValueError(f"Routed {module} {field} names differ")
        bit_map, reverse = {}, {}
        for name, net in a["netnames"].items():
            peer = b["netnames"][name]
            if {k: v for k, v in net.items() if k != "bits"} != {
                    k: v for k, v in peer.items() if k != "bits"}:
                raise ValueError(f"Routed net metadata/path differs: {module}/{name}")
            if len(net["bits"]) != len(peer["bits"]):
                raise ValueError(f"Routed net width differs: {module}/{name}")
            for src, dst in zip(net["bits"], peer["bits"]):
                if isinstance(src, int) and isinstance(dst, int):
                    if ((src in bit_map and bit_map[src] != dst) or
                            (dst in reverse and reverse[dst] != src)):
                        raise ValueError(f"Conflicting routed bit identity: {module}/{name}")
                    bit_map[src] = dst
                    reverse[dst] = src
                elif src != dst:
                    raise ValueError(f"Routed constant differs: {module}/{name}")

        def remap(bits):
            if any(isinstance(x, int) and x not in bit_map for x in bits):
                raise ValueError(f"Unnamed connected bit: {module}")
            return [bit_map[x] if isinstance(x, int) else x for x in bits]

        if a["attributes"] != b["attributes"]:
            raise ValueError(f"Routed module attributes differ: {module}")
        for name, net in a["netnames"].items():
            if remap(net["bits"]) != b["netnames"][name]["bits"]:
                raise ValueError(f"Routed net connectivity differs: {module}/{name}")
        for field in ("ports", "cells"):
            for name, item in a[field].items():
                peer = b[field][name]
                key = "bits" if field == "ports" else "connections"
                if {k: v for k, v in item.items() if k != key} != {
                        k: v for k, v in peer.items() if k != key}:
                    raise ValueError(f"Routed placement/logic/port differs: {module}/{name}")
                if field == "ports":
                    equal = remap(item[key]) == peer[key]
                else:
                    equal = (item[key].keys() == peer[key].keys() and
                             all(remap(bits) == peer[key][pin]
                                 for pin, bits in item[key].items()))
                if not equal:
                    raise ValueError(f"Routed pin connectivity differs: {module}/{name}")
        counts[module] = {"mapped_bits": len(bit_map), "cells": len(a["cells"]),
                          "nets": len(a["netnames"])}
    return counts


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
            physical[name] = routed
        checksums = {name: re.findall(r"Checksum: 0x([0-9a-f]+)", log)
                     for name, log in logs.items()}
        if any(len(c) != 3 for c in checksums.values()):
            raise ValueError("Missing physical P&R checksums")
        counts = compare_routed_semantics(physical["official"], physical["control"])
        if counts != compare_routed_semantics(physical["official"], physical["diagnostic"]):
            raise ValueError("Routed module counts differ")
        if checksums["control"] != checksums["diagnostic"]:
            raise ValueError(f"Compiled/diagnostic checksum changed: {checksums}")
        if checksums["official"][:2] != checksums["control"][:2]:
            raise ValueError(f"Packing or placement checksum changed: {checksums}")
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
        period = 1000 / next(iter(reports["official"]["fmax"].values()))["achieved"]
        if abs(period + records[0]["engine_setup_slack_ns"]) > 0.002:
            raise ValueError("Top endpoint period does not reproduce official Fmax")
        summary = {"variant": variant, "physical_checksums": checksums,
                   "routed_semantics_equal_after_bit_id_mapping": True,
                   "routed_semantic_counts": counts,
                   "reference_routed_json_sha256": hashlib.sha256(
                       (case / "official.routed.json").read_bytes()).hexdigest(),
                   "official_control_diagnostic_timing_equal": True,
                   "netlist_sha256": hashlib.sha256((case / "build/design.json").read_bytes()).hexdigest(),
                   "exit_codes": exits, "fmax": reports["official"]["fmax"], "endpoints": records}
        (case / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(json.dumps({"variant": variant, "fmax": summary["fmax"], "endpoints": len(records),
                          "physical_checksums": summary["physical_checksums"],
                          "routed_semantic_counts": counts}), flush=True)
        return summary

    with ThreadPoolExecutor(max_workers=2) as pool:
        summaries = list(pool.map(measure, ("core-32acs-rsconst", "mem-32acs-rsconst")))
    (output / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")


if __name__ == "__main__":
    main()
