#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--board", required=True)
p.add_argument("--variant", required=True)
p.add_argument("--report", required=True)
p.add_argument("--synth-log", required=True)
p.add_argument("--pnr-log", required=True)
p.add_argument("--exit-code", type=int, required=True)
a = p.parse_args()

report = {}
rp = Path(a.report)
if rp.exists():
    try:
        report = json.loads(rp.read_text())
    except Exception:
        report = {}

def walk(obj, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, path + (str(k),))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, path + (str(i),))
    else:
        yield path, obj

flat = list(walk(report))
pnr_text = Path(a.pnr_log).read_text(errors="replace")

# Use the slowest achieved clock, never the requested/target frequency.
fmax = None
for path, val in flat:
    if isinstance(val, (int, float)) and "achieved" in ".".join(path).lower():
        # Usually MHz in current nextpnr report JSON.
        if 1 <= float(val) <= 5000:
            fmax = min(float(val), fmax if fmax is not None else float(val))

if fmax is None:
    clocks = {}
    for clock, value in re.findall(
        r"Max frequency for clock '([^']+)':\s*([0-9]+(?:\.[0-9]+)?)\s*MHz",
        pnr_text,
    ):
        clocks[clock] = float(value)
    # Pre-route timing cannot be reported as routed Fmax after placement fails.
    if clocks and "Routing complete" in pnr_text:
        fmax = min(clocks.values())

def resource_lines():
    util = report.get("utilization") if isinstance(report, dict) else None
    if isinstance(util, dict):
        for key, value in util.items():
            if isinstance(value, dict):
                used = value.get("used", value.get("utilized", "?"))
                avail = value.get("available", value.get("total", "?"))
                yield key, used, avail
        return
    # nextpnr emits packed utilization before placement, including on overflow.
    # This remains useful when there is no report.json because P&R failed.
    for key, used, avail in re.findall(
        r"Info:\s+([A-Za-z0-9_]+):\s+(\d+)/\s*(\d+)\s+\d+%",
        pnr_text,
    ):
        yield key, used, avail

status = "PASS" if a.exit_code == 0 else "FAIL"
margin = "unknown"
if fmax is not None:
    margin = "PASS" if fmax >= 110.0 else "FAIL"

print(f"# {a.board} / {a.variant}")
print()
controller = "none" if a.variant == "core" else (
    "HyperRAM x8" if a.board == "4k" else "PSRAM 2 x8 channels"
)
print(f"- Blocks: Viterbi + RS; controller: **{controller}**")
print("- Scope: protocol RTL only; DDR PHY, initialization and calibration excluded")
print(f"- P&R: **{status}**")
print(f"- 110 MHz timing criterion: **{margin}**")
if fmax is not None:
    print(f"- extracted routed Fmax: **{fmax:.2f} MHz**")
print()
rows = list(resource_lines())
if rows and not report.get("utilization"):
    print("Resource counts below are packed utilization before placement.")
    print()
print("| Resource | Used | Available |")
print("|---|---:|---:|")
if rows:
    for key, used, avail in rows:
        print(f"| {key} | {used} | {avail} |")
else:
    print("| see report.json | — | — |")
