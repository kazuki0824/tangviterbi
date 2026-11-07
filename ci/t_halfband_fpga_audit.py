#!/usr/bin/env python3
"""Audit the bounded T FPGA candidate and every independently listed evidence condition.

PASS means evidence is consistent. It does not mean the candidate is adopted:
DSP saving, burst capacity, modeled timing and receiver-quality gates are
reported separately. This is a newly implemented technical audit.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "reports/s3-t-preprocess-integration-v2/quality-fpga"
PROFILES = ("baseline", "baseline-fifo", "residual", "residual-fifo")
SOURCE = "experiments/t_halfband_fpga/"
RESOURCE_FIELDS = ("sha256", "cells_by_type", "MULT18X18", "BSRAM", "RAM16SDP4", "explicit_DFF_cells")
CAD_SOURCES = ("run_cad.py", "coefficients.py", "resampler.sv", "fifo_resampler.sv", "probe.sv", "coeff_baseline.hex", "coeff_residual.hex")
STREAM_CASES = ("residual-periodic-8", "residual-back-to-back-2", "residual-back-to-back-8", "residual-continuous-8M",
                "baseline-continuous-16M", "residual-core-stalled", "baseline-core-stalled", "residual-fifo-stalled", "baseline-fifo-stalled")
BURSTS = ("residual-back-to-back-2", "residual-back-to-back-8")
STREAM_CRITERIA = ("simulation_exit", "all_stimuli_offered", "accepted_input_is_ordered_subsequence", "output_count_matches_integer_oracle",
                   "every_output_matches_integer_oracle", "output_stable_while_stalled", "fifo_bound_512_and_drained", "lossless_input_capacity")
QUALITY_PROFILES = ("zero", "positive-impulse", "negative-impulse", "positive-DC", "negative-DC", "alternating", "square",
                    "random-full", "random-sign", "tone-0.5MHz", "tone-pass-edge", "tone-stop-edge")
CONTRACT_SOURCES = ("reports/s3-preprocess-break-even/original-fir-model.json", "experiments/t_preprocess_capacity/accx_wrapper.h",
                    "experiments/t_preprocess_capacity/halfband31.h", SOURCE + "coefficients.py", "reports/s3-t-preprocess-integration/README.md")
TIMING_SOURCES = ("himbaechel/chipdb.h", "common/kernel/relptr.h", "himbaechel/arch.cc", "himbaechel/uarch/gowin/gowin.cc",
                  "himbaechel/uarch/gowin/gowin.h", "himbaechel/uarch/gowin/gowin_arch_gen.py", "himbaechel/uarch/gowin/constids.inc")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resource_criteria():
    names = ["source_binding." + x for x in CAD_SOURCES]
    for profile in PROFILES:
        names.append(profile + ".record_agrees_with_combined_result")
        for stage in ("core", "probe", "routed"):
            stem = profile + "." + stage + "."
            names += [stem + k for k in ("mapped_json_readable", "gzip_hash_matches_recorded_artifact", "decoded_hash_matches_recorded_artifact")]
            names += [stem + "recorded_resource_matches." + k for k in RESOURCE_FIELDS]
            names.append(stem + "recorded_exit_success")
        names += [profile + "." + k for k in ("routing_completed_in_retained_log", "retained_route_log_gzip_hash", "retained_route_log_decoded_hash",
                                               "resource_mapping_retains.MULT18X18", "resource_mapping_retains.BSRAM")]
    return names


def quality_criteria():
    names = ["halfband." + x for x in ("31_coefficients", "signed16_coefficients", "symmetric", "odd_taps_zero_except_center", "shift10_no_saturation_for_arbitrary_signed10")]
    for profile in ("baseline", "residual"):
        names += [profile + "." + x for x in ("table_equals_independent_generator", "all_phase_DC_sums_Q15", "direct_frequency", "direct_tone_DFT")]
        names += [profile + ".finite_metric." + x for x in ("pass_ripple_peak_to_peak_dB", "minimum_stop_attenuation_dB", "maximum_rational_image_dBc")]
        names.append(profile + ".arbitrary_signed10_cascade_cannot_saturate")
        for signal in QUALITY_PROFILES:
            names.append(profile + "." + signal + ".floor_error_bound")
            if profile == "residual":
                names += [profile + "." + signal + "." + x for x in ("no_halfband_saturation", "halfband_scalar_oracle")]
    return names + ["all_numeric_diagnostics_finite"]


def timing_criteria(profiles):
    names = ["source." + x for x in TIMING_SOURCES]
    names += ["tool_version_command_success", "binary_version_matches_inspected_source_commit", "source_packed_chipinfo_layout", "source_database_version6",
              "source_lookup_uses_cell_type", "source_missing_model_ignores_timing_port", "source_missing_model_has_no_default_delay",
              "gowin_header_does_not_override_default_cell_timing", "actual_chipdb_inventory", "target_speed_grade_is_present",
              "chipdb_hash_matches_pinned_suite", "apicula_source_inventory"]
    for profile in profiles:
        names += [profile + ".routed_netlist_readable", profile + ".pnr_report_readable"]
        for group in ("products", "accumulators"):
            names += [profile + "." + group + ".endpoints_inspected", profile + "." + group + ".all_expected_registers_found"]
    return names


def evaluate(evidence, retained_cad):
    checks, cache = [], {}
    def load(relative):
        path = evidence / relative
        if relative not in cache:
            try:
                raw = path.read_bytes()
                if path.suffix == ".gz": raw = gzip.decompress(raw)
                def invalid(x): raise ValueError("Nonfinite JSON literal: " + x)
                cache[relative] = json.loads(raw, parse_constant=invalid)
            except Exception as exc: cache[relative] = exc
        if isinstance(cache[relative], Exception): raise cache[relative]
        return cache[relative]
    def check(name, fn):
        try:
            value = bool(fn()); checks.append({"name": name, "status": "PASS" if value else "FAIL"})
        except Exception as exc: checks.append({"name": name, "status": "BLOCKED", "reason": f"{type(exc).__name__}: {exc}"})
    def records(relative):
        return {row["name"]: row for row in load(relative)["checks"]}
    def report_checks(label, relative, names):
        check(label + ".criteria_exactly_enumerated", lambda: [c["name"] for c in load(relative)["checks"]] == names)
        for name in names:
            check(label + "." + name, lambda name=name: records(relative)[name]["status"] == "PASS")
    def source_bindings(label, relative, paths):
        check(label + ".source_keys_exactly_enumerated", lambda: set(load(relative)["source_sha256"]) == set(paths))
        for path in paths:
            check(label + ".source_hash." + path, lambda path=path: load(relative)["source_sha256"][path] == digest(ROOT / path))

    coefficient = "coefficient-recovery.json"
    coeff_names = [profile + "." + key for profile in ("baseline", "residual") for key in
        ("original_sha256", "checked_in_hex_equals_recovered", "new_generator_equals_original_hex", "all_phase_dc_sums_Q15", "signed16_coefficients")]
    report_checks("coefficients", coefficient, coeff_names)
    for profile in ("baseline", "residual"):
        check("coefficients." + profile + ".current_HEX_matches_recovered_hash", lambda profile=profile:
              digest(ROOT / SOURCE / ("coeff_" + profile + ".hex")) == load(coefficient)["profiles"][profile]["recovery"]["hex_sha256"])
        check("coefficients." + profile + ".original_BRAM_hash_bound", lambda profile=profile:
              digest(ROOT / load(coefficient)["profiles"][profile]["recovery"]["source"]) == load(coefficient)["profiles"][profile]["recovery"]["source_gzip_sha256"])

    resource = "resource-audit.json"
    report_checks("resource", resource, resource_criteria())
    source_bindings("resource", resource, [SOURCE + "resource_audit.py"])
    resource_inputs = ["cad-results.json"] + [p + "/result.json" for p in PROFILES] + [p + "/" + n for p in PROFILES for n in ("core-mapped.json.gz", "probe-mapped.json.gz", "routed.json.gz")]
    check("resource.input_hash_keys_complete", lambda: set(load(resource)["input_sha256"]) == set(resource_inputs))
    for relative in resource_inputs:
        check("resource.input_hash." + relative, lambda relative=relative: load(resource)["input_sha256"][relative] == digest(retained_cad / relative))
    for profile in PROFILES:
        for stage in ("core", "probe", "routed"):
            filename = "routed.json.gz" if stage == "routed" else stage + "-mapped.json.gz"
            top = "top" if stage == "routed" else "t_diag_probe" if stage == "probe" else "t_diag_fifo_resampler" if profile.endswith("-fifo") else "t_diag_resampler"
            def counts(profile=profile, filename=filename, top=top):
                d = json.loads(gzip.decompress((retained_cad / profile / filename).read_bytes()))
                c = Counter(cell["type"] for cell in d["modules"][top]["cells"].values())
                return {"MULT18X18": c["MULT18X18"], "BSRAM": sum(c[t] for t in ("SPX9", "SDPX9B", "DPX9B", "SP", "SDP", "DP")),
                        "RAM16SDP4": c["RAM16SDP4"], "explicit_DFF_cells": sum(n for t, n in c.items() if t.startswith("DFF"))}
            for field in ("MULT18X18", "BSRAM", "RAM16SDP4", "explicit_DFF_cells"):
                check("resource.live_count." + profile + "." + stage + "." + field,
                      lambda profile=profile, stage=stage, field=field, counts=counts:
                      counts()[field] == load(resource)["profiles"][profile]["resources"][stage][field])
    for key, suffix in (("core", ""), ("fifo", "-fifo")):
        check("resource." + key + ".DSP_saving_arithmetic", lambda key=key, suffix=suffix:
              load(resource)["comparisons"][key]["DSP_saved"] == load(resource)["profiles"]["baseline"+suffix]["resources"]["routed"]["MULT18X18"] - load(resource)["profiles"]["residual"+suffix]["resources"]["routed"]["MULT18X18"])

    stream = "stream/stream-results.json"
    source_bindings("stream", stream, [SOURCE + x for x in ("run_stream.py", "coefficients.py", "resampler.sv", "fifo_resampler.sv", "stream_tb.sv", "coeff_baseline.hex", "coeff_residual.hex")])
    def case(name): return next(c for c in load(stream)["cases"] if c["name"] == name)
    check("stream.all_scenarios_enumerated", lambda: [c["name"] for c in load(stream)["cases"]] == list(STREAM_CASES))
    for name in STREAM_CASES:
        check("stream." + name + ".criteria_enumerated", lambda name=name: [x["name"] for x in case(name)["checks"]] == list(STREAM_CRITERIA))
        for criterion in STREAM_CRITERIA:
            expected = "FAIL" if criterion == "lossless_input_capacity" and name in BURSTS else "PASS"
            check("stream." + name + "." + criterion, lambda name=name, criterion=criterion, expected=expected:
                  next(x for x in case(name)["checks"] if x["name"] == criterion)["status"] == expected)
        check("stream." + name + ".zero_integer_oracle_error", lambda name=name: case(name)["status"]["maximum_oracle_error"] == 0)
        check("stream." + name + ".design_verification_pass", lambda name=name: case(name)["design_verification"] == "PASS")
        for artifact in ("input.hex.gz", "due.hex.gz", "accepted.txt.gz", "output.txt.gz"):
            path = evidence / "stream" / name / artifact
            check("stream." + name + ".gzip_hash." + artifact, lambda name=name, artifact=artifact, path=path:
                  digest(path) == case(name)["artifacts"][artifact]["sha256"])
            check("stream." + name + ".decoded_hash." + artifact, lambda name=name, artifact=artifact, path=path:
                  hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest() == case(name)["artifacts"][artifact]["uncompressed_sha256"])

    quality = "quality/quality-results.json"
    report_checks("quality", quality, quality_criteria())
    source_bindings("quality", quality, [SOURCE + x for x in ("quality.py", "coefficients.py", "run_stream.py", "coeff_baseline.hex", "coeff_residual.hex")] + ["experiments/t_preprocess_capacity/halfband31.c"])
    for profile in ("baseline", "residual"):
        check("quality." + profile + ".all_quantization_profiles", lambda profile=profile: list(load(quality)["quantization"][profile]["profiles"]) == list(QUALITY_PROFILES))
        check("quality." + profile + ".all_phases", lambda profile=profile: load(quality)["frequency"][profile]["phase_count"] == (32 if profile == "baseline" else 64))
        check("quality." + profile + ".all_images", lambda profile=profile: load(quality)["frequency"][profile]["images_per_frequency"] == (31 if profile == "baseline" else 63))
        for grid, n in (("pass", 4097), ("stop", 4097), ("full", 16385)):
            check("quality." + profile + ".grid." + grid, lambda profile=profile, grid=grid, n=n: load(quality)["frequency"][profile]["grid_points"][grid] == n)
        check("quality." + profile + ".expected_envelope_path", lambda profile=profile:
              load(quality)["frequency"][profile]["artifact"]["path"] == profile + "-frequency-envelope.csv.gz")
        check("quality." + profile + ".envelope_gzip_hash", lambda profile=profile:
              digest(evidence / "quality" / load(quality)["frequency"][profile]["artifact"]["path"]) == load(quality)["frequency"][profile]["artifact"]["sha256"])
        check("quality." + profile + ".envelope_decoded_hash", lambda profile=profile:
              hashlib.sha256(gzip.decompress((evidence / "quality" / load(quality)["frequency"][profile]["artifact"]["path"]).read_bytes())).hexdigest() == load(quality)["frequency"][profile]["artifact"]["uncompressed_sha256"])
    check("quality.receiver_equivalence_not_invented", lambda: load(quality)["receiver_MER_CN_BER_equivalence"] == "UNVERIFIED")

    contract = "quality/contract-evidence.json"
    contract_names = ["source_readable." + p for p in CONTRACT_SOURCES] + ["original_model_states_coefficient_contract_is_unspecified", "fractional_FIR_header_calls_output_contract_trial", "halfband_header_disclaims_accepted_receiver_quality"]
    report_checks("contract", contract, contract_names)
    source_bindings("contract", contract, [SOURCE + "contract_evidence.py"])
    for path in CONTRACT_SOURCES:
        check("contract.inspected_hash." + path, lambda path=path:
              next(x for x in load(contract)["sources"] if x["path"] == path)["sha256"] == digest(ROOT / path))
    check("contract.equivalence_unverified", lambda: load(contract)["receiver_quality_equivalence"] == "UNVERIFIED")

    for label, relative, profiles, cad in (("timing.pinned", "timing/timing-coverage.json.gz", PROFILES, retained_cad),
                                          ("timing.current", "cad-20261103/timing/timing-coverage.json.gz", ("residual-fifo",), evidence / "cad-20261103")):
        report_checks(label, relative, timing_criteria(profiles))
        source_bindings(label, relative, [SOURCE + "timing_coverage.py"])
        check(label + ".not_physical_signoff", lambda relative=relative: load(relative)["physical_timing_pass"] is False)
        check(label + ".all_source_names_enumerated", lambda relative=relative:
              [row["name"] for row in load(relative)["sources"]] == list(TIMING_SOURCES))
        for source_name in TIMING_SOURCES:
            check(label + ".source_url_pins_commit." + source_name, lambda relative=relative, source_name=source_name:
                  next(row for row in load(relative)["sources"] if row["name"] == source_name)["url"] ==
                  "https://raw.githubusercontent.com/YosysHQ/nextpnr/" + load(relative)["nextpnr_commit"] + "/" + source_name)
        for profile in profiles:
            check(label + "." + profile + ".routed_hash", lambda relative=relative, profile=profile, cad=cad:
                  load(relative)["profiles"][profile]["routed_gzip_sha256"] == digest(cad / profile / "routed.json.gz"))
            check(label + "." + profile + ".pnr_hash", lambda relative=relative, profile=profile, cad=cad:
                  load(relative)["profiles"][profile]["pnr_json_sha256"] == digest(cad / profile / "pnr.json"))
    supplement = "cad-20261103/supplement-results.json"
    report_checks("supplement", supplement, ["input_available.probe-mapped.json.gz", "input_available.pins.cst", "place_and_route_exit", "route_completion_log", "routed_resources_readable", "routed_four_DSP", "routed_three_BSRAM", "modeled_clock_result_readable", "coverage_inspection_exit"])
    source_bindings("supplement", supplement, [SOURCE + "supplement_timing.py", SOURCE + "timing_coverage.py"])
    for name in ("probe-mapped.json.gz", "pins.cst"):
        check("supplement.exact_retained_input." + name, lambda name=name:
              load(supplement)["input_sha256"][name] == digest(retained_cad / "residual-fifo" / name))
    for path in ("residual-fifo/probe-mapped.json.gz", "residual-fifo/pins.cst", "residual-fifo/pnr.json", "residual-fifo/pnr.log.gz", "residual-fifo/routed.json.gz", "timing/timing-coverage.json.gz"):
        check("supplement.artifact_hash." + path, lambda path=path: load(supplement)["artifacts"][path]["sha256"] == digest(evidence / "cad-20261103" / path))
    def clock(): return load("cad-20261103/residual-fifo/pnr.json")["fmax"]["g_fifo.dut.clk"]
    check("supplement.actual_clock_result_finite", lambda: math.isfinite(clock()["achieved"]))
    check("supplement.target_clock_1080_over7_MHz", lambda: math.isclose(clock()["constraint"], 1080/7, rel_tol=1e-6))
    check("supplement.modeled_clock_classification", lambda: load(supplement)["modeled_target_timing"] == ("REJECT" if clock()["achieved"] < clock()["constraint"] else "PASS"))

    def gate(fn):
        try: return fn()
        except Exception: return "UNVERIFIED"
    def burst_gate():
        values = [case(x)["capacity"] for x in BURSTS]
        if any(x not in ("PASS", "REJECT") for x in values): return "UNVERIFIED"
        if "REJECT" in values: return "REJECT"
        return "PASS" if all(x == "PASS" for x in values) else "UNVERIFIED"
    gates = {
        "same_structure_DSP_saving": gate(lambda: "PASS" if load(resource)["comparisons"]["fifo"]["DSP_saved"] > 0 else "REJECT"),
        "periodic_512us_frames": gate(lambda: case("residual-periodic-8")["capacity"] if case("residual-periodic-8")["capacity"] != "BLOCKED" else "UNVERIFIED"),
        "unthrottled_2_and_8_frame_capacity": gate(burst_gate),
        "modeled_current_clock_target": gate(lambda: load(supplement)["modeled_target_timing"]),
        "full_physical_STA": "UNVERIFIED", "original_receiver_quality": gate(lambda: load(contract)["receiver_quality_equivalence"])}
    counts = dict(Counter(row["status"] for row in checks)); passed = all(row["status"] == "PASS" for row in checks)
    return {"schema_version": 1, "non_fail_fast": True, "evaluation_completed": passed,
            "source_sha256": {"ci/t_halfband_fpga_audit.py": digest(Path(__file__))},
            "checks": checks, "counts": counts, "adoption_gates": gates, "receiver_adoption": False,
            "candidate_decision": "REJECT" if passed and "REJECT" in gates.values() else "UNVERIFIED",
            "scope": "Matched diagnostic FPGA candidate under the documented inputs and timing models. No universal ESP32-S3 impossibility claim.",
            "status": "PASS" if passed else "FAIL"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=DEFAULT)
    parser.add_argument("--retained-cad", type=Path, default=DEFAULT / "cad")
    args = parser.parse_args(); result = evaluate(args.evidence.resolve(), args.retained_cad.resolve())
    args.evidence.mkdir(parents=True, exist_ok=True)
    (args.evidence / "audit.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "counts": result["counts"], "candidate_decision": result["candidate_decision"], "receiver_adoption": result["receiver_adoption"]}))
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
