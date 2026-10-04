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
p.add_argument("--seed", type=int)
a = p.parse_args()
performance = json.loads(Path(__file__).with_name("performance.json").read_text())
target_mhz = performance["target_clock_mhz"]
minimum_viterbi_mhz = (performance["trellis_steps_per_second"] *
                       performance["viterbi_cycles_per_step"] / 1e6)

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
    margin = "PASS" if fmax >= target_mhz else "FAIL"

print(f"# {a.board} / {a.variant}")
print()
controller = "PSRAM 2 x8 channels" if a.variant == "mem" else "none"
blocks = {"viterbi-only": "Viterbi", "rs-only": "RS"}.get(a.variant, "Viterbi + RS")
print(f"- Blocks: {blocks}; controller: **{controller}**")
print("- Scope: protocol RTL only; DDR PHY, initialization and calibration excluded")
if a.pack_only:
    print(f"- Synthesis/packing: **{status}**")
    print("- P&R: **not run (diagnostic)**")
else:
    print(f"- P&R at {target_mhz:g} MHz: **{status}**")
    print(f"- Placement/routing completed: **{'yes' if routed_log else 'no'}**")
if a.seed is not None:
    seed_scope = "Configured seed (packing only)" if a.pack_only else "Placement/routing seed"
    print(f"- {seed_scope}: **{a.seed}**")
print(f"- {minimum_viterbi_mhz:g} MHz Viterbi clock criterion: **{'unknown' if fmax is None else ('PASS' if fmax >= minimum_viterbi_mhz else 'FAIL')}**")
print("- End-to-end sustained throughput: **not measured by the sizing harness**")
print(f"- {target_mhz:g} MHz timing criterion: **{margin}**")
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
