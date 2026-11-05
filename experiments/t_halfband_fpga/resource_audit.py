#!/usr/bin/env python3
"""Independently recount the preserved v2 Gowin netlists; do not rerun CAD.

The CAD payloads and their recorded source hashes are retained evidence from
commit 8e865b0156bfb7ab941c9c25d81a1f58d2e0826b. This audit is newly executed
evidence, not a recovery of the lost November 4 audit implementation or bytes.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILES = ("baseline", "baseline-fifo", "residual", "residual-fifo")
STAGES = ("core", "probe", "routed")
SOURCE_FILES = ("run_cad.py", "coefficients.py", "resampler.sv", "fifo_resampler.sv",
                "probe.sv", "coeff_baseline.hex", "coeff_residual.hex")
BRAM_TYPES = {"SPX9", "SDPX9B", "DPX9B", "SP", "SDP", "DP"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def recount(data, top):
    netlist = json.loads(data)
    modules = netlist["modules"]
    # Yosys also retains primitive/ABC9 library definitions. Count only the
    # explicitly selected flattened design top, never the library modules.
    counts = Counter(cell["type"] for cell in modules[top]["cells"].values())
    return {"sha256": sha(data), "cells_by_type": dict(sorted(counts.items())),
            "MULT18X18": counts["MULT18X18"], "BSRAM": sum(counts[name] for name in BRAM_TYPES),
            "RAM16SDP4": counts["RAM16SDP4"],
            "explicit_DFF_cells": sum(n for kind, n in counts.items() if kind.startswith("DFF"))}


def evaluate(cad):
    checks, profiles, inputs = [], {}, {}

    def check(name, fn):
        try:
            value = fn()
            row = {"name": name, "status": "PASS" if value else "FAIL"}
        except Exception as exc:
            row = {"name": name, "status": "BLOCKED", "reason": f"{type(exc).__name__}: {exc}"}
        checks.append(row)

    summary_path = cad / "cad-results.json"
    try:
        raw = summary_path.read_bytes()
        summary = json.loads(raw)
        inputs["cad-results.json"] = sha(raw)
    except Exception as exc:
        summary = {"unavailable": f"{type(exc).__name__}: {exc}"}
    for name in SOURCE_FILES:
        relative = "experiments/t_halfband_fpga/" + name
        check("source_binding." + name,
              lambda relative=relative: sha((ROOT / relative).read_bytes()) == summary["source_sha256"][relative])

    for profile in PROFILES:
        row = profiles[profile] = {"resources": {}}
        try:
            raw = (cad / profile / "result.json").read_bytes()
            recorded = json.loads(raw)
            inputs[profile + "/result.json"] = sha(raw)
        except Exception as exc:
            recorded = {"unavailable": f"{type(exc).__name__}: {exc}"}
        check(profile + ".record_agrees_with_combined_result",
              lambda recorded=recorded, profile=profile: recorded == summary["profiles"][profile])
        for stage in STAGES:
            filename = "routed.json.gz" if stage == "routed" else stage + "-mapped.json.gz"
            path = cad / profile / filename
            key = profile + "." + stage
            decoded = None
            try:
                packed = path.read_bytes()
                decoded = gzip.decompress(packed)
                inputs[profile + "/" + filename] = sha(packed)
                top = ("top" if stage == "routed" else "t_diag_probe" if stage == "probe" else
                       "t_diag_fifo_resampler" if profile.endswith("-fifo") else "t_diag_resampler")
                resource = row["resources"][stage] = recount(decoded, top)
                checks.append({"name": key + ".mapped_json_readable", "status": "PASS"})
            except Exception as exc:
                resource = row["resources"][stage] = {"status": "BLOCKED", "reason": f"{type(exc).__name__}: {exc}"}
                checks.append({"name": key + ".mapped_json_readable", "status": "BLOCKED", "reason": resource["reason"]})
            check(key + ".gzip_hash_matches_recorded_artifact",
                  lambda profile=profile, filename=filename, recorded=recorded:
                  inputs[profile + "/" + filename] == recorded["artifacts"][filename]["sha256"])
            check(key + ".decoded_hash_matches_recorded_artifact",
                  lambda decoded=decoded, filename=filename, recorded=recorded:
                  sha(decoded) == recorded["artifacts"][filename]["uncompressed_sha256"])
            for field in ("sha256", "cells_by_type", "MULT18X18", "BSRAM", "RAM16SDP4", "explicit_DFF_cells"):
                check(key + ".recorded_resource_matches." + field,
                      lambda resource=resource, stage=stage, recorded=recorded, field=field:
                      resource[field] == recorded["resources"][stage][field])
            execution = "place_and_route" if stage == "routed" else stage + "_synth"
            check(key + ".recorded_exit_success", lambda execution=execution, recorded=recorded:
                  recorded["stages"][execution]["exit_code"] == 0)
        check(profile + ".routing_completed_in_retained_log", lambda profile=profile, recorded=recorded:
              recorded["route_completed"] is True and
              b"Routing complete." in gzip.decompress((cad / profile / "pnr.log.gz").read_bytes()))
        check(profile + ".retained_route_log_gzip_hash", lambda profile=profile, recorded=recorded:
              sha((cad / profile / "pnr.log.gz").read_bytes()) == recorded["artifacts"]["pnr.log.gz"]["sha256"])
        check(profile + ".retained_route_log_decoded_hash", lambda profile=profile, recorded=recorded:
              sha(gzip.decompress((cad / profile / "pnr.log.gz").read_bytes())) ==
              recorded["artifacts"]["pnr.log.gz"]["uncompressed_sha256"])
        for field in ("MULT18X18", "BSRAM"):
            check(profile + ".resource_mapping_retains." + field, lambda row=row, field=field:
                  len({row["resources"][stage][field] for stage in STAGES}) == 1)

    comparisons = {}
    for fifo in (False, True):
        suffix = "-fifo" if fifo else ""
        try:
            before = profiles["baseline" + suffix]["resources"]["routed"]
            after = profiles["residual" + suffix]["resources"]["routed"]
            comparisons["fifo" if fifo else "core"] = {
                "DSP_before": before["MULT18X18"], "DSP_after": after["MULT18X18"],
                "DSP_saved": before["MULT18X18"] - after["MULT18X18"],
                "BSRAM_before": before["BSRAM"], "BSRAM_after": after["BSRAM"]}
        except Exception as exc:
            comparisons["fifo" if fifo else "core"] = {"status": "BLOCKED", "reason": str(exc)}
    return {"schema_version": 1, "non_fail_fast": True,
            "evidence_origin": "Fresh independent recount of retained CAD; no synthesis or place-and-route rerun.",
            "retained_evidence_commit": "8e865b0156bfb7ab941c9c25d81a1f58d2e0826b",
            "source_sha256": {"experiments/t_halfband_fpga/resource_audit.py": sha(Path(__file__).read_bytes())},
            "input_sha256": inputs, "checks": checks, "profiles": profiles,
            "comparisons": comparisons, "physical_timing_pass": False,
            "status": "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cad", type=Path, default=ROOT / "reports/s3-t-preprocess-integration-v2/quality-fpga/cad")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.cad)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "checks": dict(Counter(c["status"] for c in result["checks"])),
                      "comparisons": result["comparisons"]}))
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
