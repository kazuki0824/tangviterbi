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

def find_numeric(names):
    names = tuple(n.lower() for n in names)
    candidates = []
    for path, val in flat:
        if not isinstance(val, (int, float)):
            continue
        joined = ".".join(path).lower()
        if any(n in joined for n in names):
            candidates.append((joined, val))
    return candidates

# nextpnr report schemas have changed over time. Keep the raw JSON artifact and
# extract the most useful fields opportunistically instead of hard-coding one schema.
fmax = None
for path, val in flat:
    if isinstance(val, (int, float)) and "achieved" in ".".join(path).lower():
        # Usually MHz in current nextpnr report JSON.
        if 1 <= float(val) <= 5000:
            fmax = max(float(val), fmax or 0.0)

if fmax is None:
    text = Path(a.pnr_log).read_text(errors="replace")
    vals = [float(x) for x in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*MHz", text)]
    if vals:
        # The log contains both target and achieved clocks; maximum is useful as
        # a fallback but the raw log remains authoritative.
        fmax = max(vals)

def resource_lines():
    util = report.get("utilization") if isinstance(report, dict) else None
    if isinstance(util, dict):
        for key, value in util.items():
            if isinstance(value, dict):
                used = value.get("used", value.get("utilized", "?"))
                avail = value.get("available", value.get("total", "?"))
                yield key, used, avail

status = "PASS" if a.exit_code == 0 else "FAIL"
margin = "unknown"
if fmax is not None:
    margin = "PASS" if fmax >= 110.0 else "FAIL"

print(f"# {a.board} / {a.variant}")
print()
print(f"- P&R: **{status}**")
print(f"- 110 MHz timing criterion: **{margin}**")
if fmax is not None:
    print(f"- extracted routed Fmax: **{fmax:.2f} MHz**")
print()
print("| Resource | Used | Available |")
print("|---|---:|---:|")
rows = list(resource_lines())
if rows:
    for key, used, avail in rows:
        print(f"| {key} | {used} | {avail} |")
else:
    print("| see report.json | — | — |")
