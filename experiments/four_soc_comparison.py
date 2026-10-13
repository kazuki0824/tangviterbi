"""Reproducible comparison inputs; analytical screens never certify a receiver.

All ownerships and every RF representation remain in the output. Separate T/S
images take the maximum per-mode selected-stage resource, not the sum or a
stage-by-stage shared netlist. Board wiring, PHY, memory, timing and drivers are
deliberately unknown until evidenced, rather than assigned zero cost.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOC = {"C5": (240, 1), "S31": (320, 2), "S3": (240, 2), "C61": (160, 1)}
CAP = {"logic_sites_estimate": 8640, "FF": 6480, "BSRAM": 26, "DSP18": 20}
NODES = {
    "T": ("FIR", "sync", "FFT", "equalize_demap", "time_deinterleave", "Viterbi", "RS", "TS"),
    "S": ("FIR", "sync", "TC8PSK", "frame_deinterleave", "RS", "TS"),
}
UNKNOWN = (
    "whole_FPGA_top_PNR_STA", "simultaneous_internal_external_memory",
    "per_core_WCET_RF_IRQ_and_buffer_lifetimes", "implemented_stage_quality",
    "performance_then_communication_assignment", "fixed_wiring_and_NOR_switch",
    "end_to_end_independent_RF_to_TS",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def load_inputs(path):
    with gzip.open(path, "rt") as stream:
        return json.load(stream)


def validate(inputs):
    """Reject incomplete, duplicated or mismatched finite comparison universes."""
    rows = inputs["ownerships"]
    by_id = {r["id"]: r for r in rows}
    modes = {r["id"]: r for r in inputs["mode_profiles"]}
    if len(by_id) != 1280 or len(rows) != 1280 or len(modes) != 1280:
        raise ValueError("expected 1280 unique ownerships and profile groups")
    if set(by_id) != set(modes):
        raise ValueError("ownership/profile identity mismatch")
    for soc, standard in itertools.product(SOC, NODES):
        subset = [r for r in rows if r["SoC"] == soc and r["standard"] == standard]
        signatures = {tuple(r["owners"][n] for n in NODES[standard]) for r in subset}
        expected = set(itertools.product(("SoC", "FPGA"), repeat=len(NODES[standard])))
        if len(subset) != len(expected) or signatures != expected:
            raise ValueError(f"missing/duplicate ownership: {soc}/{standard}")
    checked = 0
    for ident, group in modes.items():
        row = by_id[ident]
        if any(group[k] != row[k] for k in ("SoC", "standard", "owners")):
            raise ValueError("profile ownership mismatch: " + ident)
        keys = set()
        scenarios = set()
        for p in group["profiles"]:
            key = (p["high"], p["FPGA_MHz"], p["RF_format"])
            if key in keys:
                raise ValueError("duplicate cost profile: " + ident)
            keys.add(key)
            scenarios.add(key[:2])
            rf = row.get("RF_partial_capture_budget_in_sum")
            total = sum(v["known_model_Mcycles_per_s"][int(p["high"])]
                        for v in p["CPU_stage_models"].values()
                        if v["resource"] not in ("ACS_lanes", "TC_ACS_lanes"))
            total += rf["Mcycles_per_s"] if rf else 0
            if not math.isclose(total, p["CPU_Mcycles_s_before_boundary_drivers"], abs_tol=1e-7):
                raise ValueError("CPU accounting mismatch: " + ident)
            checked += 1
        if scenarios != {(h, f) for h in (False, True) for f in (100, 125)}:
            raise ValueError("missing scenario: " + ident)
    return by_id, modes, checked


def selected_resources(profile):
    return {k: sum(v[k] for v in profile["FPGA_stage_estimates"].values()) for k in CAP}


def separate_images(t, s):
    return {k: max(t[k], s[k]) for k in CAP}


def profile_metrics(row, p):
    clock, cores = SOC[row["SoC"]]
    cpu = max(max(p["CPU_pinned_Mcycles_s"]), p["CPU_Mcycles_s_before_boundary_drivers"] / cores) / clock
    res = selected_resources(p)
    required = max(p["stage_required_MHz"].values(), default=0)
    screen = cpu <= 1 and all(res[k] <= CAP[k] for k in CAP) and required <= p["FPGA_MHz"]
    return {
        "key": [row["id"], p["high"], p["FPGA_MHz"], p["RF_format"]],
        "ideal_divisible_CPU_utilization_before_boundary_drivers": cpu,
        "selected_stage_resources_estimate": res,
        "stage_required_MHz_model": required,
        "declared_model_screen_pass": screen,
        "performance_verified": False, "communication_assignment": None,
        "whole_resources": None, "per_core_WCET": None,
        "unknown": list(UNKNOWN),
    }


def frontier(records):
    """Pareto comparisons of explicit model axes, retaining equivalent owners."""
    vectors = defaultdict(list)
    for r in records:
        res = r["separate_image_selected_resource_max"]
        vector = tuple(res[k] / CAP[k] for k in CAP) + (r["minimum_model_CPU_utilization"],)
        vectors[vector].append(r["pair"])
    surviving = []
    for v in sorted(vectors):
        if not any(all(a <= b for a, b in zip(w, v)) and any(a < b for a, b in zip(w, v)) for w in surviving):
            surviving = [w for w in surviving if not (all(a <= b for a, b in zip(v, w)) and any(a < b for a, b in zip(v, w)))]
            surviving.append(v)
    return [{"normalized_axes": list(v), "equivalent_pairs": sorted(vectors[v])} for v in surviving]


def compare(inputs):
    by_id, modes, checked = validate(inputs)
    metrics = []
    groups = defaultdict(list)
    counts = Counter()
    for row in inputs["ownerships"]:
        for p in modes[row["id"]]["profiles"]:
            m = profile_metrics(row, p)
            metrics.append(m)
            groups[(row["id"], p["high"], p["FPGA_MHz"])].append(m)
            counts[(row["SoC"], row["standard"])] += 1
    pairs, scenarios = [], []
    for soc in SOC:
        t_ids = sorted(r["id"] for r in by_id.values() if r["SoC"] == soc and r["standard"] == "T")
        s_ids = sorted(r["id"] for r in by_id.values() if r["SoC"] == soc and r["standard"] == "S")
        for high, freq in itertools.product((False, True), (100, 125)):
            eligible = []
            for ti, si in itertools.product(t_ids, s_ids):
                t, s = groups[(ti, high, freq)], groups[(si, high, freq)]
                # RF transport alternatives must not silently change FPGA arithmetic.
                for alternatives in (t, s):
                    if len({canonical(x["selected_stage_resources_estimate"]) for x in alternatives}) != 1:
                        raise ValueError("RF profiles need distinct resource pair accounting")
                res = separate_images(t[0]["selected_stage_resources_estimate"], s[0]["selected_stage_resources_estimate"])
                tp = [x for x in t if x["declared_model_screen_pass"]]
                sp = [x for x in s if x["declared_model_screen_pass"]]
                record = {
                    "pair": [ti, si], "scenario": [high, freq],
                    "separate_image_selected_resource_max": res,
                    "minimum_model_CPU_utilization": max(min(x["ideal_divisible_CPU_utilization_before_boundary_drivers"] for x in t), min(x["ideal_divisible_CPU_utilization_before_boundary_drivers"] for x in s)),
                    "declared_model_screen_pass": bool(tp and sp),
                    "T_RF_profiles": [x["key"][-1] for x in t], "S_RF_profiles": [x["key"][-1] for x in s],
                    "performance_verified": False, "communication_assignment": None,
                }
                pairs.append(record)
                if tp and sp:
                    eligible.append(record)
            scenarios.append({"SoC": soc, "high": high, "FPGA_MHz": freq,
                              "ownership_pairs": len(t_ids) * len(s_ids),
                              "declared_model_screen_pairs": len(eligible),
                              "model_only_Pareto_frontier": frontier(eligible),
                              "confirmed_feasible_pairs": 0})
    return {
        "schema": 1, "provenance": inputs["provenance"],
        "input_semantic_sha256": hashlib.sha256(canonical(inputs)).hexdigest(),
        "comparison_contract": {
            "image_architecture": "exclusive_T_S_external_NOR_reload",
            "RF_policy": "native samples; no added software decimation or requantization",
            "CPU": "legacy analytic cost scenarios, ideally divisible unpinned work, not WCET",
            "FPGA": "legacy selected-stage sizing including unvalidated FEC anchors, not whole resources or proven bounds",
            "screen_failure": "does not eliminate ownerships or alternative implementations",
            "axes": list(CAP) + ["CPU_utilization"],
            "communication": "allocate only after evidenced performance; all current assignments are null",
            "wiring_memory_switch": "not inferred from resource maxima; fixed pin union and simultaneous memory still unknown",
            "S3_module": "original N8R8; N16R8 SDK evidence retained as scoped reference, not N8R8 certification",
        },
        "coverage": {"ownerships": len(by_id), "cost_profiles": checked,
                     "distinct_ownership_pairs": len(pairs) // 4, "scenario_pair_records": len(pairs)},
        "groups": [{"SoC": s, "standard": st, "ownerships": 2 ** len(NODES[st]), "cost_profiles": counts[(s, st)]} for s, st in itertools.product(SOC, NODES)],
        "profiles": metrics, "pairs": pairs, "scenarios": scenarios,
        "hypothesis_comparison_ready": True,
        "best_candidate_certifiable": False, "complete_estimate": False,
        "performance_stage_completed": False, "receiver_adopted": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", type=Path, default=ROOT / "reports/four-soc-comparison/inputs.json.gz")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/four-soc-comparison/comparison.json.gz")
    args = parser.parse_args()
    result = compare(load_inputs(args.inputs))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(gzip.compress(canonical(result), mtime=0))
    summary = {k: result[k] for k in ("schema", "provenance", "input_semantic_sha256", "comparison_contract", "coverage", "groups", "scenarios", "hypothesis_comparison_ready", "best_candidate_certifiable", "complete_estimate", "performance_stage_completed", "receiver_adopted")}
    summary["files"] = {str(p.relative_to(ROOT)): {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in (args.inputs, args.output)}
    args.output.with_name("summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result["coverage"]))


if __name__ == "__main__":
    main()
