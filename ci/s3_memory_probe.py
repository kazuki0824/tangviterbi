#!/usr/bin/env python3
"""Build an actual ESP-IDF ELF/map and preserve failed link evidence as data."""
import json
import os
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
app = root / "experiments/s3_memory_probe"
name = os.environ["PROBE_NAME"]
out = root / "build/s3-memory" / name
out.mkdir(parents=True, exist_ok=True)
command = ["idf.py", "-B", str(out / "idf"), "-DIDF_TARGET=esp32s3", "build"]
with (out / "build.log").open("w") as log:
    rc = subprocess.run(command, cwd=app, stdout=log, stderr=subprocess.STDOUT).returncode
log = (out / "build.log").read_text(errors="replace")
map_file = out / "idf/s3_memory_probe.map"
result = {"profile": name, "IDF_version": subprocess.check_output(
    ["idf.py", "--version"], text=True).strip(),
    "IDF_commit": subprocess.check_output(
        ["git", "-C", os.environ["IDF_PATH"], "rev-parse", "HEAD"], text=True).strip(),
    "build_exit_code": rc, "link_succeeded": rc == 0,
    "RF_reserved_range": ["0x3fcb0000", "0x3fce0000"],
    "scope": "Optimistic link-only static-buffer probe. No RF/PHY, dual-core FFT, application hot IRAM, DMA descriptors or full runtime stacks. Success is not a receiver memory fit.",
    "symbols": {}, "guard_errors": [line.strip() for line in log.splitlines()
                                      if "S3 RF ring overlaps" in line]}
if map_file.exists():
    text = map_file.read_text(errors="replace")
    symbols = ("_iram_start", "_iram_end", "_data_start", "_data_end", "_bss_start", "_bss_end",
               "rf_packed_queue", "link_staging", "fft_transfer_slots", "fft_twiddle_reservation")
    for symbol in symbols:
        matches = re.findall(r"^\s*(0x[0-9a-fA-F]+)\s+" + symbol + r"\b", text, re.M)
        if matches:
            result["symbols"][symbol] = matches[-1]
    if "_bss_end" in result["symbols"]:
        result["static_gap_to_RF_bytes"] = 0x3fcb0000 - int(result["symbols"]["_bss_end"], 16)
(out / "result.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
print("\n".join(log.splitlines()[-35:]))
# A known placement rejection is a completed measurement; unrelated build
# failures are infrastructure/source errors and must fail the workflow.
if rc and not result["guard_errors"]:
    raise SystemExit(rc)
