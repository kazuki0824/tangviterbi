#!/usr/bin/env python3
"""Execute v2 RTL with externally scheduled ingress and a direct integer oracle.

An overflow is a valid negative capacity finding, separate from arithmetic and
ready/valid correctness. Every scenario and every criterion is reported.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np

from coefficients import PARAMETERS, SOURCE, generate

CLOCK_MHZ = Fraction(1080, 7)
INPUT_FILES = ["run_stream.py", "coefficients.py", "resampler.sv", "fifo_resampler.sv", "stream_tb.sv",
               "coeff_baseline.hex", "coeff_residual.hex"]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stimuli(count, bits):
    """Full-range complex inputs include impulses, edges, DC and random data."""
    rng = np.random.default_rng(0x5A17 + bits)
    low, high = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    samples = rng.integers(low, high + 1, size=(count, 2), dtype=np.int64)
    samples[:64] = 0
    samples[0] = [high, low]
    samples[64:128] = [high, high]
    samples[128:192] = [low, low]
    samples[192:256:2] = [high, low]
    samples[193:256:2] = [low, high]
    return samples


def oracle(samples, spec):
    # Independent of RTL control, circular RAM layout and pipeline state:
    # evaluate the rational output time and direct 32-term convolution.
    coeff = generate("baseline" if spec["L"] == 32 else "residual")
    result = []
    for m in range((len(samples) * spec["L"] + 62) // 63):
        anchor, phase = divmod(m * 63, spec["L"])
        k = min(anchor + 1, 32)
        accum = coeff[phase, :k] @ samples[anchor - np.arange(k)]
        shifted = accum >> spec["output_shift"]
        result.append(np.clip(shifted, -32768, 32767))
    return np.array(result, dtype=np.int64)


def ceil_fraction(value):
    return -(-value.numerator // value.denominator)


def schedule(count, rate_mhz, frame_period_us=None):
    return [ceil_fraction(CLOCK_MHZ * (
        Fraction(n // 4096) * frame_period_us + Fraction(n % 4096, 1) / rate_mhz
        if frame_period_us else Fraction(n, 1) / rate_mhz)) for n in range(count)]


def load_rows(path, columns):
    rows = [list(map(int, line.split())) for line in path.read_text().splitlines() if line]
    return np.array(rows, dtype=np.int64).reshape(-1, columns)


def run_case(case, compiled, directory, vvp):
    folder = directory / case["name"]
    folder.mkdir(parents=True, exist_ok=True)
    spec = PARAMETERS[case["profile"]]
    samples = stimuli(case["samples"], spec["input_bits"])
    times = schedule(len(samples), Fraction(case["rate_mhz"]), case.get("period_us"))
    (folder / "input.hex").write_text("".join(f"{((int(q) & 65535) << 16) | (int(i) & 65535):08x}\n" for i, q in samples))
    (folder / "due.hex").write_text("".join(f"{x:08x}\n" for x in times))
    # Enough to drain all data even when deterministic output stalls are enabled.
    timeout = max(times[-1] + 25000, len(samples) * (65 if case.get("stall") else 40))
    command = [str(vvp), str(compiled), f"+N={len(samples)}", f"+TIMEOUT={timeout}",
               f"+BACKPRESSURE={int(case.get('backpressure', False))}", f"+STALL={int(case.get('stall', False))}"]
    for arg, name in [("INPUT", "input.hex"), ("DUE", "due.hex"), ("ACCEPTED", "accepted.txt"),
                      ("OUTPUT", "output.txt"), ("STATUS", "status.json")]:
        command.append(f"+{arg}={folder / name}")
    checks = []
    run = subprocess.run(command, cwd=SOURCE, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    (folder / "simulation.log").write_text(run.stdout)
    checks.append({"name": "simulation_exit", "status": "PASS" if run.returncode == 0 else "FAIL"})
    status = json.loads((folder / "status.json").read_text())
    accepted = load_rows(folder / "accepted.txt", 4)
    output = load_rows(folder / "output.txt", 3)
    expected = oracle(accepted[:, 2:], spec)
    same_count = len(output) == len(expected)
    errors = np.abs(output[:min(len(output), len(expected)), 1:] - expected[:min(len(output), len(expected))])
    all_offered = status["offered"] == len(samples)
    conditions = {"all_stimuli_offered": all_offered,
                  "accepted_input_is_ordered_subsequence": bool(np.array_equal(accepted[:, 2:], samples[accepted[:, 1]])),
                  "output_count_matches_integer_oracle": same_count,
                  "every_output_matches_integer_oracle": same_count and bool(np.all(errors == 0)),
                  "output_stable_while_stalled": status["stable_failures"] == 0,
                  "fifo_bound_512_and_drained": status["max_fifo"] <= 512 and status["final_fifo"] == 0,
                  "lossless_input_capacity": status["lost"] == 0 and status["accepted"] == len(samples)}
    checks.extend({"name": name, "status": "PASS" if ok else "FAIL"} for name, ok in conditions.items())
    status["first_lost_sample_one_based"] = status["first_lost_index_zero_based"] + 1 if status["lost"] else None
    status["first_lost_time_us"] = float(Fraction(status["first_lost_cycle"], 1) / CLOCK_MHZ) if status["lost"] else None
    status["maximum_oracle_error"] = int(errors.max()) if errors.size else None
    status["expected_output_count"] = len(expected)
    # Raw transactions remain inspectable; deterministic gzip avoids huge text commits.
    artifacts = {}
    for name in ["input.hex", "due.hex", "accepted.txt", "output.txt"]:
        path = folder / name
        data = path.read_bytes()
        packed = path.with_suffix(path.suffix + ".gz")
        packed.write_bytes(gzip.compress(data, mtime=0))
        artifacts[packed.name] = {"sha256": digest(packed), "uncompressed_sha256": hashlib.sha256(data).hexdigest()}
        path.unlink()
    return {**case, "clock_mhz": float(CLOCK_MHZ), "timeout_cycles": timeout,
            "status": status, "checks": checks, "artifacts": artifacts,
            "capacity": "PASS" if conditions["lossless_input_capacity"] else "REJECT",
            "design_verification": "PASS" if all(x["status"] == "PASS" for x in checks if x["name"] != "lossless_input_capacity") else "FAIL"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    cases = [
        {"name": "residual-periodic-8", "profile": "residual", "fifo": True, "samples": 32768, "rate_mhz": 10, "period_us": 512},
        {"name": "residual-back-to-back-2", "profile": "residual", "fifo": True, "samples": 8192, "rate_mhz": 10},
        {"name": "residual-back-to-back-8", "profile": "residual", "fifo": True, "samples": 32768, "rate_mhz": 10},
        {"name": "residual-continuous-8M", "profile": "residual", "fifo": True, "samples": 8192, "rate_mhz": 8},
        {"name": "baseline-continuous-16M", "profile": "baseline", "fifo": True, "samples": 8192, "rate_mhz": 16},
        {"name": "residual-core-stalled", "profile": "residual", "fifo": False, "samples": 4096, "rate_mhz": 100, "backpressure": True, "stall": True},
        {"name": "baseline-core-stalled", "profile": "baseline", "fifo": False, "samples": 4096, "rate_mhz": 100, "backpressure": True, "stall": True},
        {"name": "residual-fifo-stalled", "profile": "residual", "fifo": True, "samples": 4096, "rate_mhz": 100, "backpressure": True, "stall": True},
        {"name": "baseline-fifo-stalled", "profile": "baseline", "fifo": True, "samples": 4096, "rate_mhz": 100, "backpressure": True, "stall": True},
    ]
    result = {"version": 2, "rtl_source_status": "reconstructed new v2", "non_fail_fast": True,
              "oracle": "mathematically generated coefficients; direct rational-index convolution, shift and saturation",
              "compile": {}, "cases": [], "physical_timing_pass": False, "source_sha256": {}}
    for name in INPUT_FILES:
        path = SOURCE / name
        try:
            result["source_sha256"][str(path.relative_to(SOURCE.parents[1]))] = digest(path)
        except Exception as exc:
            result["source_sha256"][str(path.relative_to(SOURCE.parents[1]))] = {"status": "BLOCKED", "reason": str(exc)}
    for profile in PARAMETERS:
        for fifo in [False, True]:
            spec = PARAMETERS[profile]
            key = f"{profile}-{'fifo' if fifo else 'core'}"
            executable = directory / (key + ".vvp")
            command = [str(args.suite / "bin/iverilog"), "-g2012", "-s", "stream_tb", "-o", str(executable)]
            for name, value in [("INPUT_BITS", spec["input_bits"]), ("L", spec["L"]), ("OUTPUT_SHIFT", spec["output_shift"]),
                                ("USE_FIFO", int(fifo)), ("COEFF_FILE", f'"coeff_{profile}.hex"')]:
                command += [f"-Pstream_tb.{name}={value}"]
            command += ["resampler.sv", "fifo_resampler.sv", "stream_tb.sv"]
            try:
                run = subprocess.run(command, cwd=SOURCE, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
                (directory / (key + "-compile.log")).write_text(run.stdout)
                result["compile"][key] = {"exit_code": run.returncode, "command": command}
            except Exception as exc:
                result["compile"][key] = {"exit_code": 125, "command": command, "status": "BLOCKED", "reason": str(exc)}
    for case in cases:
        key = f"{case['profile']}-{'fifo' if case['fifo'] else 'core'}"
        try:
            if result["compile"][key]["exit_code"]:
                raise RuntimeError("RTL compilation failed")
            row = run_case(case, directory / (key + ".vvp"), directory, args.suite / "bin/vvp")
        except Exception as exc:
            names = ["simulation_exit", "all_stimuli_offered", "accepted_input_is_ordered_subsequence",
                     "output_count_matches_integer_oracle", "every_output_matches_integer_oracle",
                     "output_stable_while_stalled", "fifo_bound_512_and_drained", "lossless_input_capacity"]
            row = {**case, "error": str(exc), "capacity": "BLOCKED", "design_verification": "BLOCKED",
                   "checks": [{"name": name, "status": "BLOCKED", "reason": str(exc)} for name in names]}
        result["cases"].append(row)
        (directory / "stream-results.json").write_text(json.dumps(result, indent=2) + "\n")
        print(case["name"], row["design_verification"], row["capacity"], flush=True)
    design_states = [row["design_verification"] for row in result["cases"]]
    result["design_verification"] = ("FAIL" if "FAIL" in design_states else
                                     "PASS" if all(state == "PASS" for state in design_states) else "BLOCKED")
    burst_states = [row["capacity"] for row in result["cases"] if "back-to-back" in row["name"]]
    result["unthrottled_2_and_8_frame_capacity"] = ("UNVERIFIED" if any(state not in ("PASS", "REJECT") for state in burst_states)
                                                 else "REJECT" if "REJECT" in burst_states else "PASS")
    (directory / "stream-results.json").write_text(json.dumps(result, indent=2) + "\n")
    for binary in directory.glob("*.vvp"):
        binary.unlink()
    return int(result["design_verification"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
