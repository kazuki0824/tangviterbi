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
p.add_argument("--pack-only", action="store_true")
a = p.parse_args()

report = {}
rp = Path(a.report)
if rp.exists():
    try:
        report = json.loads(rp.read_text())
    except Exception:
        report = {}

pnr_text = Path(a.pnr_log).read_text(errors="replace")

# A partial JSON report can include pre-route clock estimates. Accept achieved
# clock values only after the router explicitly completed, including a routed
# design that subsequently failed timing. Never substitute target MHz.
fmax = None
routed_log = pnr_text.partition("Routing complete")[2]
if routed_log and not a.pack_only:
    achieved = [
        float(clock["achieved"])
        for clock in report.get("fmax", {}).values()
        if isinstance(clock, dict)
        and isinstance(clock.get("achieved"), (int, float))
        and not isinstance(clock.get("achieved"), bool)
        and 0 < clock["achieved"] <= 5000
    ]
    if achieved:
        fmax = min(achieved)
    else:
        clocks = {}
        for clock, value in re.findall(
            r"Max frequency for clock '([^']+)':\s*([0-9]+(?:\.[0-9]+)?)\s*MHz",
            routed_log,
        ):
            clocks[clock] = float(value)
        if clocks:
            fmax = min(clocks.values())

packed_rows = re.findall(
    r"Info:\s+([A-Za-z0-9_]+):\s+(\d+)/\s*(\d+)\s+\d+%",
    pnr_text,
)

def resource_lines():
    # Use one comparable accounting stage for successful and failed jobs.
    # Final report utilization can count placed LUT/ALU/RAM overlap differently.
    if packed_rows:
        yield from packed_rows
        return
    util = report.get("utilization") if isinstance(report, dict) and not a.pack_only else None
    if isinstance(util, dict):
        for key, value in util.items():
            if isinstance(value, dict):
                used = value.get("used", value.get("utilized", "?"))
                avail = value.get("available", value.get("total", "?"))
                yield key, used, avail
        return

status = "PASS" if a.exit_code == 0 else "FAIL"
margin = "unknown"
if fmax is not None:
    margin = "PASS" if fmax >= 110.0 else "FAIL"

print(f"# {a.board} / {a.variant}")
print()
controller = "none" if a.variant != "mem" else (
    "HyperRAM x8" if a.board == "4k" else "PSRAM 2 x8 channels"
)
blocks = {"viterbi-only": "Viterbi", "rs-only": "RS"}.get(a.variant, "Viterbi + RS")
print(f"- Blocks: {blocks}; controller: **{controller}**")
print("- Scope: protocol RTL only; DDR PHY, initialization and calibration excluded")
if a.pack_only:
    print(f"- Synthesis/packing: **{status}**")
    print("- P&R: **not run (diagnostic)**")
else:
    print(f"- P&R at 110 MHz: **{status}**")
    print(f"- Placement/routing completed: **{'yes' if routed_log else 'no'}**")
print(f"- 100.8 MHz throughput criterion: **{'unknown' if fmax is None else ('PASS' if fmax >= 100.8 else 'FAIL')}**")
print(f"- 110 MHz timing criterion: **{margin}**")
if fmax is not None:
    print(f"- extracted routed Fmax: **{fmax:.2f} MHz**")
print()
rows = list(resource_lines())
if packed_rows:
    print("Resource counts below are packed utilization before placement.")
    print()
print("| Resource | Used | Available |")
print("|---|---:|---:|")
if rows:
    for key, used, avail in rows:
        print(f"| {key} | {used} | {avail} |")
else:
    print("| see report.json | — | — |")
