#!/usr/bin/env python3
"""Reconstruct the diagnostic coefficient tables from preserved BRAM data.

The two .hex files are byte-identical to the lost originals. This decoder and
the mathematical generator are new v2 source; no claim is made that the lost
Python generator itself was recovered.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).resolve().parent
OLD = ROOT / "reports/s3-t-preprocess-integration/quality-fpga"
PARAMETERS = {"baseline": {"L": 32, "fs_mhz": 16.0, "input_bits": 10, "output_shift": 10},
              "residual": {"L": 64, "fs_mhz": 8.0, "input_bits": 16, "output_shift": 15}}
EXPECTED = {"baseline": "ed4cc491e4718afb124966f28f8ee06a5ef9749eca6b71fff48118058d2cda98",
            "residual": "e7afd42839e5027a7a5230717b78cfd8a0871386bd4ea3474a9f1411bfe06620"}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def decode_words(data, phases):
    words = np.array([int(x, 16) for x in data.decode().split()], dtype=np.uint32).reshape(phases, 16)
    rows = np.empty((phases, 32), dtype=np.int64)
    rows[:, 0::2] = ((words & 65535).astype(np.int64) + 32768) % 65536 - 32768
    rows[:, 1::2] = ((words >> 16).astype(np.int64) + 32768) % 65536 - 32768
    return rows


def encode_words(rows):
    return "".join(f"{((int(row[k + 1]) & 65535) << 16) | (int(row[k]) & 65535):08x}\n"
                   for row in rows for k in range(0, 32, 2)).encode()


def generate(profile):
    spec = PARAMETERS[profile]
    phases = spec["L"]
    # A length 32*L windowed-sinc interpolation prototype, split into L phases.
    # Per-phase DC normalization and one integer correction keep every sum Q15.
    t = np.arange(32 * phases) / phases - (32 * phases - 1) / (2 * phases)
    h = (7.2 / spec["fs_mhz"]) * np.sinc(7.2 / spec["fs_mhz"] * t) * np.kaiser(32 * phases, 8.6)
    rows = []
    for p in range(phases):
        phase = h[p::phases].copy()
        phase /= phase.sum()
        integers = np.rint(phase * 32768).astype(np.int64)
        integers[np.argmax(np.abs(integers))] += 32768 - integers.sum()
        rows.append(integers)
    return np.array(rows)


def recover(profile):
    path = OLD / profile / "core-mapped.json.gz"
    compressed = path.read_bytes()
    netlist = json.loads(gzip.decompress(compressed))
    cells = netlist["modules"]["t_diag_resampler"]["cells"]
    brams = [(name, cell) for name, cell in sorted(cells.items()) if cell["type"] == "SPX9"]
    expected_blocks, expected_width = (1, 36) if profile == "baseline" else (2, 18)
    if len(brams) != expected_blocks:
        raise ValueError("unexpected coefficient BRAM count")
    vectors = []
    for _, cell in brams:
        params = cell["parameters"]
        width = int(params["BIT_WIDTH"], 2)
        if width != expected_width:
            raise ValueError("unexpected coefficient BRAM width")
        # Yosys gowin/brams_map.v init_slice_x9 maps consecutive 288-bit slices.
        image = sum(int(params[f"INIT_RAM_{i:02X}"].replace("x", "0"), 2) << (288 * i)
                    for i in range(64))
        vectors.append([(image >> (index * width)) & ((1 << width) - 1)
                        for index in range(18432 // width)])
    words = vectors[0] if profile == "baseline" else [lo | (hi << 18) for lo, hi in zip(*vectors)]
    data = "".join(f"{word & 0xffffffff:08x}\n" for word in words).encode()
    return data, {"source": str(path.relative_to(ROOT)), "source_gzip_sha256": sha256(compressed),
                  "SPX9_blocks": expected_blocks, "SPX9_width": expected_width,
                  "hex_sha256": sha256(data), "expected_original_sha256": EXPECTED[profile]}


def audit():
    checks, profiles = [], {}
    for name, spec in PARAMETERS.items():
        row = {**spec, "M": 63, "taps_per_phase": 32, "cutoff_mhz": 3.6, "kaiser_beta": 8.6}
        profiles[name] = row
        recovered = current = generated = fixed = None
        errors = {}
        try:
            recovered, provenance = recover(name)
            row["recovery"] = provenance
        except Exception as exc:
            errors["recovered"] = str(exc)
        try:
            current = (SOURCE / f"coeff_{name}.hex").read_bytes()
            fixed = decode_words(current, spec["L"])
            row["max_absolute_phase_sum"] = int(np.max(np.abs(fixed).sum(axis=1)))
        except Exception as exc:
            errors["fixed"] = str(exc)
        try:
            generated = encode_words(generate(name))
        except Exception as exc:
            errors["generated"] = str(exc)
        conditions = [
            ("original_sha256", ["recovered"], lambda: sha256(recovered) == EXPECTED[name]),
            ("checked_in_hex_equals_recovered", ["recovered", "fixed"], lambda: current == recovered),
            ("new_generator_equals_original_hex", ["generated"], lambda: sha256(generated) == EXPECTED[name]),
            ("all_phase_dc_sums_Q15", ["fixed"], lambda: bool(np.all(fixed.sum(axis=1) == 32768))),
            ("signed16_coefficients", ["fixed"], lambda: bool(np.all((fixed >= -32768) & (fixed <= 32767)))),
        ]
        for key, dependencies, test in conditions:
            missing = {dep: errors[dep] for dep in dependencies if dep in errors}
            check = {"name": f"{name}.{key}", "status": "BLOCKED" if missing else "PASS" if test() else "FAIL"}
            if missing:
                check["reason"] = missing
            checks.append(check)
    return {"version": 2, "non_fail_fast": True, "checks": checks,
            "status": "PASS" if all(x["status"] == "PASS" for x in checks) else "FAIL",
            "profiles": profiles, "numpy_version": np.__version__,
            "scope": "Diagnostic coefficients recovered exactly; original receiver quality contract is not supplied by these tables.",
            "generator_source_status": "new v2 mathematical generator verified against both original table hashes"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit()
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end="")
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
