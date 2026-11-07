#!/usr/bin/env python3
"""Exercise concrete missing-input/tool and invalid-coefficient audit regressions.

Each scenario and each assertion is listed even after another fails. Temporary
copies are isolated from retained evidence and removed after the test.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).resolve().parent
DEFAULT = ROOT / "reports/s3-t-preprocess-integration-v2/quality-fpga"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def evaluate(evidence, retained):
    cases, checks = [], []
    def run(name, criteria, fn):
        try:
            values, details = fn()
            rows = [{"name": name + "." + key, "status": "PASS" if values[key] else "FAIL"} for key in criteria]
        except Exception as exc:
            rows = [{"name": name + "." + key, "status": "BLOCKED", "reason": f"{type(exc).__name__}: {exc}"} for key in criteria]
            details = {}
        cases.append({"name": name, "checks": rows, "details": details,
                      "status": "PASS" if all(x["status"] == "PASS" for x in rows) else "FAIL"})
        checks.extend(rows)

    def missing_netlist():
        audit = module("resource_negative", SOURCE / "resource_audit.py")
        before = audit.evaluate(retained)
        with tempfile.TemporaryDirectory(prefix="fpga-negative-", dir=SOURCE) as temp:
            copied = Path(temp) / "cad"; shutil.copytree(retained, copied)
            (copied / "baseline/core-mapped.json.gz").unlink()
            after = audit.evaluate(copied)
        values = {"all_condition_names_retained": [x["name"] for x in before["checks"]] == [x["name"] for x in after["checks"]],
                  "missing_stage_BLOCKED": next(x for x in after["checks"] if x["name"] == "baseline.core.mapped_json_readable")["status"] == "BLOCKED"}
        for profile in ("baseline-fifo", "residual", "residual-fifo"):
            values[profile + "_still_PASS"] = all(x["status"] == "PASS" for x in after["checks"] if x["name"].startswith(profile + "."))
        return values, {"conditions": len(after["checks"]), "counts": dict(Counter(x["status"] for x in after["checks"]))}
    run("one_retained_netlist_missing", ["all_condition_names_retained", "missing_stage_BLOCKED", "baseline-fifo_still_PASS", "residual_still_PASS", "residual-fifo_still_PASS"], missing_netlist)

    def no_evidence():
        audit = module("fpga_empty_negative", ROOT / "ci/t_halfband_fpga_audit.py")
        before = audit.evaluate(evidence, retained)
        with tempfile.TemporaryDirectory(prefix="fpga-negative-", dir=SOURCE) as temp:
            after = audit.evaluate(Path(temp), retained)
        return {"control_evidence_PASS": before["status"] == "PASS",
                "all_condition_names_retained": [x["name"] for x in before["checks"]] == [x["name"] for x in after["checks"]],
                "not_marked_complete": after["evaluation_completed"] is False,
                "decision_UNVERIFIED": after["candidate_decision"] == "UNVERIFIED"}, {"counts": after["counts"]}
    run("all_evidence_missing", ["control_evidence_PASS", "all_condition_names_retained", "not_marked_complete", "decision_UNVERIFIED"], no_evidence)

    def missing_reports():
        audit = module("fpga_multi_negative", ROOT / "ci/t_halfband_fpga_audit.py")
        before = audit.evaluate(evidence, retained)
        with tempfile.TemporaryDirectory(prefix="fpga-negative-", dir=SOURCE) as temp:
            copied = Path(temp) / "evidence"; shutil.copytree(evidence, copied)
            for relative in ("stream/stream-results.json", "quality/quality-results.json", "timing/timing-coverage.json.gz"):
                (copied / relative).unlink()
            after = audit.evaluate(copied, retained)
        values = {"all_condition_names_retained": [x["name"] for x in before["checks"]] == [x["name"] for x in after["checks"]]}
        for prefix in ("stream.", "quality.", "timing.pinned."):
            selected = [x for x in after["checks"] if x["name"].startswith(prefix)]
            values[prefix + "all_BLOCKED"] = bool(selected) and all(x["status"] == "BLOCKED" for x in selected)
        for prefix in ("resource.", "contract.", "timing.current."):
            selected = [x for x in after["checks"] if x["name"].startswith(prefix)]
            values[prefix + "still_PASS"] = bool(selected) and all(x["status"] == "PASS" for x in selected)
        return values, {"counts": after["counts"]}
    run("three_independent_reports_missing", ["all_condition_names_retained", "stream.all_BLOCKED", "quality.all_BLOCKED", "timing.pinned.all_BLOCKED", "resource.still_PASS", "contract.still_PASS", "timing.current.still_PASS"], missing_reports)

    def zero_coefficients():
        with tempfile.TemporaryDirectory(prefix="fpga-negative-", dir=SOURCE) as temp:
            fixture = Path(temp); dest = fixture / "experiments/t_halfband_fpga"; dest.mkdir(parents=True)
            for name in ("quality.py", "coefficients.py", "run_stream.py", "coeff_baseline.hex", "coeff_residual.hex"):
                shutil.copy2(SOURCE / name, dest / name)
            hb = fixture / "experiments/t_preprocess_capacity/halfband31.c"; hb.parent.mkdir(parents=True)
            shutil.copy2(ROOT / "experiments/t_preprocess_capacity/halfband31.c", hb)
            (dest / "coeff_residual.hex").write_text("00000000\n" * 1024)
            proc = subprocess.run([sys.executable, str(dest / "quality.py"), "--output", str(fixture / "result")],
                                  cwd=fixture, text=True, capture_output=True, timeout=90)
            def invalid(value): raise ValueError("Nonstandard JSON literal: " + value)
            after = json.loads((fixture / "result/quality-results.json").read_text(), parse_constant=invalid)
        before = json.loads((evidence / "quality/quality-results.json").read_text())
        return {"exit_nonzero": proc.returncode != 0,
                "all_condition_names_retained": [x["name"] for x in before["checks"]] == [x["name"] for x in after["checks"]],
                "strict_JSON_emitted": True, "nonfinite_values_explained": bool(after["nonfinite_diagnostics"]),
                "independent_baseline_PASS": all(x["status"] == "PASS" for x in after["checks"] if x["name"].startswith("baseline."))}, {
                    "conditions": len(after["checks"]), "nonfinite_diagnostics": after["nonfinite_diagnostics"]}
    run("zero_residual_coefficients", ["exit_nonzero", "all_condition_names_retained", "strict_JSON_emitted", "nonfinite_values_explained", "independent_baseline_PASS"], zero_coefficients)

    def missing_tools():
        with tempfile.TemporaryDirectory(prefix="fpga-negative-", dir=SOURCE) as temp:
            root = Path(temp); out = root / "stream"
            proc = subprocess.run([sys.executable, str(SOURCE / "run_stream.py"), "--suite", str(root / "absent-suite"), "--output", str(out)],
                                  text=True, capture_output=True, timeout=60)
            after = json.loads((out / "stream-results.json").read_text())
        before = json.loads((evidence / "stream/stream-results.json").read_text())
        return {"exit_nonzero": proc.returncode != 0,
                "all_compile_profiles_present": set(after["compile"]) == set(before["compile"]),
                "all_scenarios_present": [x["name"] for x in after["cases"]] == [x["name"] for x in before["cases"]],
                "every_criterion_BLOCKED": len(after["cases"]) == 9 and all(len(x["checks"]) == 8 and all(c["status"] == "BLOCKED" for c in x["checks"]) for x in after["cases"]),
                "capacity_summary_UNVERIFIED": after["unthrottled_2_and_8_frame_capacity"] == "UNVERIFIED",
                "design_summary_BLOCKED": after["design_verification"] == "BLOCKED"}, {
                    "scenarios": len(after["cases"]), "criteria": sum(len(x["checks"]) for x in after["cases"])}
    run("RTL_tools_missing", ["exit_nonzero", "all_compile_profiles_present", "all_scenarios_present", "every_criterion_BLOCKED", "capacity_summary_UNVERIFIED", "design_summary_BLOCKED"], missing_tools)

    paths = [SOURCE / x for x in ("verify_non_fail_fast.py", "resource_audit.py", "quality.py", "coefficients.py", "run_stream.py", "coeff_baseline.hex", "coeff_residual.hex")]
    paths += [ROOT / "ci/t_halfband_fpga_audit.py", ROOT / "experiments/t_preprocess_capacity/halfband31.c"]
    bindings = {}
    for path in paths:
        try: bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception as exc: bindings[str(path.relative_to(ROOT))] = {"status": "BLOCKED", "reason": str(exc)}
    return {"schema_version": 1, "non_fail_fast": True, "source_sha256": bindings, "cases": cases, "checks": checks,
            "status": "PASS" if all(x["status"] == "PASS" for x in checks) else "FAIL"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT)
    parser.add_argument("--retained-cad", type=Path, default=DEFAULT / "cad")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); result = evaluate(args.evidence.resolve(), args.retained_cad.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "scenarios": len(result["cases"]), "checks": dict(Counter(x["status"] for x in result["checks"]))}))
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
