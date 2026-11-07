#!/usr/bin/env python3
"""Evaluate the diagnostic T filter, not unspecified receiver-quality equivalence.

Fresh implementation of all-phase response, rational interpolation images and
integer cascade checks. It does not claim to recover lost analysis-file bytes.
The only acceptance limits below are mathematical consistency/error bounds;
there is no invented MER, C/N or BER requirement for the original receiver.
"""
from __future__ import annotations

import argparse
import cmath
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

from coefficients import PARAMETERS, ROOT, SOURCE, decode_words, generate
from run_stream import oracle

PASS_EDGE = 39 / 14 + 0.1
STOP_EDGE = 8 - PASS_EDGE
HB_PATH = ROOT / "experiments/t_preprocess_capacity/halfband31.c"
INPUTS = [SOURCE / n for n in ("quality.py", "coefficients.py", "run_stream.py", "coeff_baseline.hex", "coeff_residual.hex")] + [HB_PATH]
PROFILE_NAMES = ("zero", "positive-impulse", "negative-impulse", "positive-DC", "negative-DC",
                 "alternating", "square", "random-full", "random-sign", "tone-0.5MHz", "tone-pass-edge", "tone-stop-edge")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def finite_json(value, issues, path=""):
    """Preserve every diagnostic even for malformed/zero coefficient inputs."""
    if isinstance(value, float) and not math.isfinite(value):
        issues.append({"path": path, "reason": "Nonfinite numeric diagnostic", "value": str(value)})
        return None
    if isinstance(value, dict):
        return {key: finite_json(item, issues, path + "." + key if path else key) for key, item in value.items()}
    if isinstance(value, list):
        return [finite_json(item, issues, f"{path}[{index}]") for index, item in enumerate(value)]
    return value


def halfband_coefficients():
    body = re.search(r"hb31_coefficients\[31\]\s*=\s*\{(.*?)\}", HB_PATH.read_text(), re.S)
    if body is None:
        raise ValueError("Cannot locate the declared halfband31 coefficient table")
    result = np.array([int(x.strip()) for x in body.group(1).split(",") if x.strip()], dtype=np.int64)
    if result.shape != (31,):
        raise ValueError("Expected exactly 31 halfband coefficients")
    return result


def response(coeff, freq, fs):
    return (coeff / 32768) @ np.exp(-2j * np.pi * np.arange(coeff.shape[-1])[:, None] * freq / fs)


def db(magnitude):
    # This display floor does not alter extrema used for pass/stop measurements.
    return 20 * np.log10(np.maximum(magnitude, 1e-16))


def ideal_phases(profile):
    spec = PARAMETERS[profile]; count = spec["L"]
    t = np.arange(32 * count) / count - (32 * count - 1) / (2 * count)
    prototype = (7.2 / spec["fs_mhz"]) * np.sinc(7.2 / spec["fs_mhz"] * t) * np.kaiser(32 * count, 8.6)
    rows = prototype.reshape(32, count).T.copy()
    return rows / rows.sum(axis=1)[:, None]


def frequency(profile, coeff, hb, output):
    spec = PARAMETERS[profile]; phases = spec["L"]; fs = spec["fs_mhz"]
    grids = {"pass": np.linspace(0, PASS_EDGE, 4097), "stop": np.linspace(STOP_EDGE, 8, 4097),
             "full": np.linspace(0, 8, 16385)}
    gain = {}
    for name, grid in grids.items():
        h = response(coeff, grid, fs)
        if profile == "residual":
            h *= response(hb, grid, 16)
        gain[name] = np.abs(h)
    f = grids["pass"]
    h = response(coeff, f, fs)
    # Relative to the desired tone at output time m*M/L. phase = m*M mod L.
    corrected = h * np.exp(-2j * np.pi * np.arange(phases)[:, None] * f / (phases * fs))
    order = (np.arange(phases) * 63) % phases
    images = np.fft.fft(corrected[order], axis=0) / phases
    ratios = np.abs(images[1:]) / np.abs(images[0])
    delay = np.real(response(coeff * np.arange(32), f, fs) / h) / fs
    delay += np.arange(phases)[:, None] / (phases * fs)
    if profile == "residual":
        delay += np.real(response(hb * np.arange(31), f, 16) / response(hb, f, 16)) / 16

    direct_error = 0.0
    image_error = 0.0
    probes = np.array([0.0, 0.5, PASS_EDGE / 2, PASS_EDGE, 3.6, 4.0, STOP_EDGE, 7.0, 8.0])
    matrix = response(coeff, probes, fs)
    if profile == "residual":
        matrix *= response(hb, probes, 16)
    for phase in range(phases):
        for j, freq in enumerate(probes):
            direct = sum(int(c) * cmath.exp(-2j * math.pi * k * freq / fs)
                         for k, c in enumerate(coeff[phase])) / 32768
            if profile == "residual":
                cosine_sum = int(hb[15]) + 2 * sum(int(hb[k]) * math.cos(2 * math.pi * (15-k) * freq / 16)
                                                 for k in range(15))
                direct *= cosine_sum / 32768 * cmath.exp(-2j * math.pi * 15 * freq / 16)
            direct_error = max(direct_error, abs(direct - matrix[phase, j]))
    # Independent tone evaluation followed by a direct DFT of L output samples.
    # Start after history fill; this uses actual rational anchors, not corrected[].
    for freq in (0.0, 0.5, PASS_EDGE / 2, PASS_EDGE):
        sequence = []
        for m in range(2 * phases, 3 * phases):
            anchor, phase = divmod(m * 63, phases)
            y = sum(int(c) * cmath.exp(2j * math.pi * freq * (anchor - k) / fs)
                    for k, c in enumerate(coeff[phase])) / 32768
            sequence.append(y * cmath.exp(-2j * math.pi * freq * m * 63 / (phases * fs)))
        direct = np.array([sum(sequence[n] * cmath.exp(-2j * math.pi * r * n / phases)
                               for n in range(phases)) / phases for r in range(phases)])
        phase_h = response(coeff, np.array([freq]), fs)[:, 0]
        reference = np.fft.fft((phase_h * np.exp(-2j * np.pi * np.arange(phases) * freq / (phases * fs)))[order]) / phases
        image_error = max(image_error, float(np.max(np.abs(direct - reference))))
    ideal = ideal_phases(profile)
    filename = profile + "-frequency-envelope.csv.gz"
    table = "frequency_MHz,minimum_all_phase_dB,maximum_all_phase_dB\n" + "".join(
        f"{freq:.12g},{low:.12g},{high:.12g}\n" for freq, low, high in
        zip(grids["full"], db(gain["full"].min(axis=0)), db(gain["full"].max(axis=0))))
    packed = gzip.compress(table.encode(), mtime=0); (output / filename).write_bytes(packed)
    return {"phase_count": phases, "taps_per_phase": 32, "input_rate_MHz": fs,
            "raw_input_rate_MHz": 16, "output_rate_MHz": 512 / 63,
            "pass_edge_MHz": PASS_EDGE, "stop_edge_MHz": STOP_EDGE,
            "grid_points": {name: len(grid) for name, grid in grids.items()},
            "pass_ripple_peak_to_peak_dB": float(20 * np.log10(gain["pass"].max() / gain["pass"].min())),
            "minimum_stop_attenuation_dB": float(-20 * np.log10(gain["stop"].max())),
            "maximum_rational_image_dBc": float(20 * np.log10(ratios.max())),
            "images_per_frequency": phases - 1,
            "nominal_prototype_group_delay_us": (32 * phases - 1) / (2 * phases * fs) + (15 / 16 if profile == "residual" else 0),
            "quantized_all_phase_pass_group_delay_us": [float(delay.min()), float(delay.max())],
            "direct_frequency_max_complex_error": float(direct_error),
            "direct_tone_DFT_max_complex_error": image_error,
            "coefficient_quantization_max_error_Q15_units": float(np.max(np.abs(coeff - 32768 * ideal))),
            "coefficient_quantization_max_phase_L1_error": float(np.abs(coeff / 32768 - ideal).sum(axis=1).max()),
            "artifact": {"path": filename, "sha256": sha(packed), "uncompressed_sha256": sha(table.encode())}}


def stimuli(name, n=2048):
    x = np.zeros((n, 2), dtype=np.int64); t = np.arange(n)
    if name == "positive-impulse": x[0] = [511, -512]
    elif name == "negative-impulse": x[63] = [-512, 511]
    elif name == "positive-DC": x[:] = 511
    elif name == "negative-DC": x[:] = -512
    elif name == "alternating": x[:] = np.where(t[:, None] % 2 == np.array([0, 1]), 511, -512)
    elif name == "square": x[:] = np.where(t[:, None] % 16 < 8, 511, -512)
    elif name in ("random-full", "random-sign"):
        rng = np.random.default_rng(0xA55A)
        x[:] = rng.integers(-512, 512, size=x.shape) if name == "random-full" else rng.choice([-512, 511], size=x.shape)
    elif name.startswith("tone-"):
        freq = {"tone-0.5MHz": 0.5, "tone-pass-edge": PASS_EDGE, "tone-stop-edge": STOP_EDGE}[name]
        x[:] = np.rint(511 * np.column_stack((np.cos(2*np.pi*freq*t/16), np.sin(2*np.pi*freq*t/16)))).astype(np.int64)
    return x


def raw_reference(raw, coeff, hb, profile):
    spec = PARAMETERS[profile]
    if profile == "baseline":
        kernels = coeff; divisor = 1024; decimation = 1
    else:
        upsampled = np.zeros((64, 63), dtype=np.int64); upsampled[:, ::2] = coeff
        kernels = np.array([np.convolve(row, hb) for row in upsampled])
        divisor = 1024 * 32768; decimation = 2
    count = ((len(raw) // decimation) * spec["L"] + 62) // 63
    result = []
    for m in range(count):
        anchor, phase = divmod(m * 63, spec["L"]); anchor *= decimation
        length = min(anchor + 1, kernels.shape[1])
        result.append((kernels[phase, :length] @ raw[anchor - np.arange(length)]) / divisor)
    return np.asarray(result), kernels, divisor


def quantization(profile, coeff, hb, name):
    raw = stimuli(name)
    intermediate = raw
    hb_error = None
    hb_saturation = 0
    if profile == "residual":
        sums = np.column_stack([np.convolve(raw[:, lane], hb)[:len(raw):2] for lane in (0, 1)])
        shifted = sums >> 10
        intermediate = np.clip(shifted, -32768, 32767)
        hb_saturation = int(np.count_nonzero(shifted != intermediate))
        # Scalar signed integer convolution is independent of numpy.convolve.
        direct = np.array([[sum(int(hb[k]) * int(raw[2*n-k, lane]) for k in range(min(31, 2*n+1))) >> 10
                            for lane in (0, 1)] for n in range(len(raw)//2)], dtype=np.int64)
        hb_error = int(np.abs(intermediate - np.clip(direct, -32768, 32767)).max())
    actual = oracle(intermediate, PARAMETERS[profile])
    linear, kernels, divisor = raw_reference(raw, coeff, hb, profile)
    floor_bound = 1.0 if profile == "baseline" else 1.0 + float(np.abs(coeff).sum(axis=1).max()) / 32768
    error = actual - linear
    maximum = float(np.abs(error).max())
    rms = float(np.sqrt(np.mean(error ** 2)))
    return {"raw_samples": len(raw), "output_samples": len(actual), "halfband_scalar_max_error": hb_error,
            "halfband_saturated_values": hb_saturation, "maximum_linear_reference_error_LSB": maximum,
            "rms_linear_reference_error_LSB": rms, "strict_floor_error_bound_LSB": floor_bound,
            "input_sha256": sha(raw.astype('<i2').tobytes()),
            "integer_output_sha256": sha(actual.astype('<i2').tobytes()),
            "linear_reference_definition": "Exact Q15 coefficients, direct raw-input composite convolution, no intermediate floors",
            "all_intermediate_within_signed16": bool(np.all((intermediate >= -32768) & (intermediate <= 32767)))}


def evaluate(output):
    output.mkdir(parents=True, exist_ok=True)
    checks, freq, quant, inputs = [], {}, {}, {}
    def check(name, fn):
        try: checks.append({"name": name, "status": "PASS" if fn() else "FAIL"})
        except Exception as exc: checks.append({"name": name, "status": "BLOCKED", "reason": f"{type(exc).__name__}: {exc}"})
    for path in INPUTS:
        key = str(path.relative_to(ROOT))
        try: inputs[key] = sha(path.read_bytes())
        except Exception as exc: inputs[key] = {"status": "BLOCKED", "reason": str(exc)}
    try: hb = halfband_coefficients()
    except Exception as exc: hb = None; hb_error = str(exc)
    check("halfband.31_coefficients", lambda: hb.shape == (31,))
    check("halfband.signed16_coefficients", lambda: bool(np.all((hb >= -32768) & (hb <= 32767))))
    check("halfband.symmetric", lambda: bool(np.array_equal(hb, hb[::-1])))
    check("halfband.odd_taps_zero_except_center", lambda: bool(np.all(np.delete(hb[1::2], 7) == 0)))
    check("halfband.shift10_no_saturation_for_arbitrary_signed10", lambda: (512 * int(np.abs(hb).sum()) + 1023) // 1024 < 32768)
    for profile, spec in PARAMETERS.items():
        try: coeff = decode_words((SOURCE / f"coeff_{profile}.hex").read_bytes(), spec["L"])
        except Exception: coeff = None
        check(profile + ".table_equals_independent_generator", lambda profile=profile, coeff=coeff: bool(np.array_equal(coeff, generate(profile))))
        check(profile + ".all_phase_DC_sums_Q15", lambda coeff=coeff: bool(np.all(coeff.sum(axis=1) == 32768)))
        try: freq[profile] = frequency(profile, coeff, hb, output)
        except Exception as exc: freq[profile] = {"status": "BLOCKED", "reason": f"{type(exc).__name__}: {exc}"}
        for name, key, threshold in (("direct_frequency", "direct_frequency_max_complex_error", 1e-12),
                                     ("direct_tone_DFT", "direct_tone_DFT_max_complex_error", 1e-11)):
            check(profile + "." + name, lambda profile=profile, key=key, threshold=threshold: freq[profile][key] < threshold)
        for key in ("pass_ripple_peak_to_peak_dB", "minimum_stop_attenuation_dB", "maximum_rational_image_dBc"):
            check(profile + ".finite_metric." + key, lambda profile=profile, key=key: math.isfinite(freq[profile][key]))
        try:
            _, kernels, divisor = raw_reference(np.zeros((128, 2), dtype=np.int64), coeff, hb, profile)
            floor_bound = 1.0 if profile == "baseline" else 1 + float(np.abs(coeff).sum(axis=1).max()) / 32768
            bounds = {"linear_raw_signed10_bound_LSB": 512 * int(np.abs(kernels).sum(axis=1).max()) / divisor,
                      "floor_error_strict_bound_LSB": floor_bound}
            bounds["integer_cascade_abs_strict_bound_LSB"] = bounds["linear_raw_signed10_bound_LSB"] + floor_bound
        except Exception as exc: bounds = {"status": "BLOCKED", "reason": str(exc)}
        quant[profile] = {"bounds": bounds, "profiles": {}}
        check(profile + ".arbitrary_signed10_cascade_cannot_saturate", lambda bounds=bounds: bounds["integer_cascade_abs_strict_bound_LSB"] < 32767)
        for name in PROFILE_NAMES:
            try: row = quant[profile]["profiles"][name] = quantization(profile, coeff, hb, name)
            except Exception as exc: row = quant[profile]["profiles"][name] = {"status": "BLOCKED", "reason": f"{type(exc).__name__}: {exc}"}
            check(profile + "." + name + ".floor_error_bound", lambda row=row: row["maximum_linear_reference_error_LSB"] < row["strict_floor_error_bound_LSB"] + 1e-9)
            if profile == "residual":
                check(profile + "." + name + ".no_halfband_saturation", lambda row=row: row["halfband_saturated_values"] == 0)
                check(profile + "." + name + ".halfband_scalar_oracle", lambda row=row: row["halfband_scalar_max_error"] == 0)
    result = {"schema_version": 1, "evidence_origin": "Freshly regenerated diagnostic evaluation; not recovered lost output bytes.",
            "non_fail_fast": True, "numpy_version": np.__version__, "source_sha256": inputs,
            "assumptions": {"pass_edge_MHz": PASS_EDGE, "stop_edge_MHz": STOP_EDGE, "halfband_shift": 10,
                "residual_shift": 15, "baseline_shift": 10, "coefficient_design": "32 taps/phase, cutoff3.6MHz, Kaiser beta8.6, Q15 per-phase DC normalization",
                "stopband_definition": "Per-tone response over [8-pass_edge,8]MHz at original16MHz input; not a receiver MER/CN/BER criterion",
                "response_display_floor_dB": -320},
            "halfband_coefficient_summary": None if hb is None else {
                "sum_Q15": int(hb.sum()), "DC_gain": int(hb.sum()) / 32768,
                "absolute_sum_Q15": int(np.abs(hb).sum()),
                "note": "Use the checked-in table as-is; its DC sum is not forced to exactly32768."},
            "frequency": freq, "quantization": quant, "checks": checks,
            "status": "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL",
            "same_quality_receiver_contract": "UNVERIFIED", "receiver_MER_CN_BER_equivalence": "UNVERIFIED",
            "receiver_adoption": False}
    issues = []
    result = finite_json(result, issues)
    result["nonfinite_diagnostics"] = issues
    result["checks"].append({"name": "all_numeric_diagnostics_finite", "status": "FAIL" if issues else "PASS"})
    result["status"] = "PASS" if all(c["status"] == "PASS" for c in result["checks"]) else "FAIL"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); result = evaluate(args.output)
    (args.output / "quality-results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "checks": dict(Counter(c["status"] for c in result["checks"])),
                      "frequency": {p: {k: v for k, v in row.items() if k.endswith("dB") or k.endswith("dBc")} for p, row in result["frequency"].items()}}))
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
