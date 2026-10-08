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
p.add_argument("--target-clock-mhz", type=float)
p.add_argument("--acs-lanes", type=int)
p.add_argument("--rs-syndrome-cycles", type=int)
p.add_argument("--rs-label", default="current")
p.add_argument("--with-viterbi", type=int, choices=(0, 1))
p.add_argument("--with-rs", type=int, choices=(0, 1))
p.add_argument("--with-mem", type=int, choices=(0, 1))
a = p.parse_args()

performance = json.loads(Path(__file__).with_name("performance.json").read_text())
target_mhz = performance["target_clock_mhz"] if a.target_clock_mhz is None else a.target_clock_mhz
acs_lanes = a.acs_lanes or performance["acs_lanes"]
if performance["states"] % acs_lanes:
    raise SystemExit("ACS lane count must divide the 64-state trellis")
viterbi_cycles = performance["states"] // acs_lanes
rs_syndrome_cycles = (
    performance["rs_syndrome_cycles_per_byte"]
    if a.rs_syndrome_cycles is None else a.rs_syndrome_cycles
)

with_viterbi = (0 if a.variant == "rs-only" else 1) if a.with_viterbi is None else a.with_viterbi
with_rs = (0 if a.variant in ("viterbi-only", "viterbi-32acs") else 1) if a.with_rs is None else a.with_rs
with_mem = a.variant.startswith("mem") if a.with_mem is None else bool(a.with_mem)

isdb_t_steps = performance["trellis_steps_per_second"]
isdb_s_steps = performance.get("isdb_s_trellis_steps_per_second")

minimum_viterbi_mhz = isdb_t_steps * viterbi_cycles / 1e6
minimum_viterbi_isdb_s_mhz = (
    None if isdb_s_steps is None else isdb_s_steps * viterbi_cycles / 1e6
)
rs_bound = (
    performance["rs_codeword_bytes"] * (1 + rs_syndrome_cycles)
    + performance["rs_other_bound_cycles"]
)

def rs_minimum(step_rate):
    return rs_bound * step_rate / (performance["rs_codeword_bytes"] * 8 * 1e6)

minimum_rs_mhz = rs_minimum(isdb_t_steps)
minimum_rs_isdb_s_mhz = None if isdb_s_steps is None else rs_minimum(isdb_s_steps)

def shared_floor(viterbi_floor, rs_floor):
    enabled = []
    if with_viterbi:
        enabled.append(viterbi_floor)
    if with_rs:
        enabled.append(rs_floor)
    return max(enabled) if enabled else 0.0

clock_floor = shared_floor(minimum_viterbi_mhz, minimum_rs_mhz)
clock_floor_isdb_s = (
    None if isdb_s_steps is None
    else shared_floor(minimum_viterbi_isdb_s_mhz, minimum_rs_isdb_s_mhz)
)

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

def criterion(floor):
    if fmax is None:
        return "unknown"
    return "PASS" if fmax >= floor else "FAIL"

status = "PASS" if a.exit_code == 0 else "FAIL"
margin = "unknown"
if fmax is not None:
    margin = "PASS" if fmax >= target_mhz else "FAIL"

print(f"# {a.board} / {a.variant}")
print()
controller = "PSRAM 2 x8 channels" if with_mem else "none"
if with_viterbi and with_rs:
    blocks = "Viterbi + RS"
elif with_viterbi:
    blocks = "Viterbi"
elif with_rs:
    blocks = "RS"
else:
    blocks = "none"
print(f"- Blocks: {blocks}; controller: **{controller}**")
if with_viterbi:
    print(f"- Viterbi architecture: **{acs_lanes} ACS / {viterbi_cycles} clocks per trellis step**")
if with_rs:
    print(f"- RS syndrome schedule: **{rs_syndrome_cycles} cycles/input byte ({a.rs_label})**")
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

if with_viterbi:
    print(f"- {minimum_viterbi_mhz:g} MHz Viterbi clock criterion: **{criterion(minimum_viterbi_mhz)}**")
    if minimum_viterbi_isdb_s_mhz is not None:
        print(
            f"- ISDB-S Viterbi clock criterion: **{minimum_viterbi_isdb_s_mhz:.2f} MHz "
            f"({criterion(minimum_viterbi_isdb_s_mhz)})**"
        )
if with_rs:
    print(f"- Conservative RS service bound: **{rs_bound} clocks/block**")
    print(f"- Minimum RS clock from cycle budget: **{minimum_rs_mhz:.2f} MHz**")
    if minimum_rs_isdb_s_mhz is not None:
        print(f"- ISDB-S minimum RS clock from cycle budget: **{minimum_rs_isdb_s_mhz:.2f} MHz**")
print(f"- Minimum shared clock from cycle budgets: **{clock_floor:.2f} MHz**")
print(f"- Hard throughput clock criterion: **{criterion(clock_floor)}**")
if clock_floor_isdb_s is not None:
    print(f"- ISDB-S minimum shared clock from cycle budgets: **{clock_floor_isdb_s:.2f} MHz**")
    print(f"- ISDB-S hard throughput clock criterion: **{criterion(clock_floor_isdb_s)}**")
print("- End-to-end sustained throughput: **not measured by the sizing harness**")
print(f"- {target_mhz:g} MHz timing criterion: **{margin}**")
if target_mhz != performance["target_clock_mhz"]:
    print(f"- {performance['target_clock_mhz']:g} MHz margin target criterion: **{criterion(performance['target_clock_mhz'])}**")
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
