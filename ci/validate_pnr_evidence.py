#!/usr/bin/env python3
"""Verify CAD evidence without conflating an expected timing miss with a broken CI run.

A zero exit code means that a measurement was completed and honestly reported,
not that an FPGA design met timing. Only the six historically measured 9K
110-MHz experiments may report a timing miss without failing this CI job.
Every other CAD failure remains a failing check.
"""
import argparse
from pathlib import Path
import re
import sys

EXPECTED_TIMING_MISSES = frozenset({
    "core-only", "mem", "core-32acs", "mem-32acs",
    "core-32acs-rsconst", "mem-32acs-rsconst",
})
ERROR_CLOCK = re.compile(
    r"^ERROR: Max frequency for clock '[^']+': "
    r"([0-9]+(?:\.[0-9]+)?) MHz \(FAIL at ([0-9]+(?:\.[0-9]+)?) MHz\)$"
)
ROUTED_CLOCK = re.compile(
    r"^(?:Info|ERROR): Max frequency for clock '[^']+': "
    r"([0-9]+(?:\.[0-9]+)?) MHz \((?:PASS|FAIL) at ([0-9]+(?:\.[0-9]+)?) MHz\)$"
)


def verify(board, variant, target_mhz, outcome, pnr_text, summary):
    """Raise ValueError for tool failures, missing proof, or mislabeled timing data."""
    if outcome not in ("success", "failure"):
        raise ValueError("P&R step outcome missing or invalid")
    if target_mhz <= 0:
        raise ValueError("invalid frequency")
    if not pnr_text.strip() or not summary.strip():
        raise ValueError("CAD log or reported summary missing")

    is_pack_only = variant in ("viterbi-only", "viterbi-32acs", "rs-only")
    if outcome == "success":
        required = (
            "P&R: **not run (diagnostic)**" if is_pack_only
            else f"P&R at {target_mhz:g} MHz: **PASS**"
        )
        if required not in summary:
            raise ValueError("successful CAD command lacks a matching success summary")
        if not is_pack_only and "Routing complete" not in pnr_text:
            raise ValueError("successful routed result lacks routing completion")
        return "PASS: CAD command and report completed; performance follows the report"

    if board != "9k" or variant not in EXPECTED_TIMING_MISSES or target_mhz != 110:
        raise ValueError("unexpected CAD failure; cannot waive fit, clock or tool errors")
    if is_pack_only:
        raise ValueError("packing-only diagnostics cannot claim routed timing failure")

    routed_start = pnr_text.rfind("Routing complete")
    if routed_start < 0:
        raise ValueError("CAD did not finish routing; not a timing-only miss")
    routed_text = pnr_text[routed_start:]
    errors = [line.strip() for line in pnr_text.splitlines()
              if re.search(r"(?:^|\s)(?:ERROR|Error|error|FATAL|Fatal):", line)]
    if not errors:
        raise ValueError("nonzero CAD status has no routed timing error")
    measured = []
    for line in errors:
        match = ERROR_CLOCK.fullmatch(line)
        if not match or line not in routed_text:
            raise ValueError("CAD error was not an exclusively post-route timing violation")
        achieved, constrained = map(float, match.groups())
        if constrained != target_mhz or achieved <= 0 or achieved >= constrained:
            raise ValueError("timing failure has inconsistent clock values")
        measured.append(achieved)
    if not any(ROUTED_CLOCK.fullmatch(line.strip()) for line in routed_text.splitlines()):
        raise ValueError("routed clock result missing")

    if (f"P&R at {target_mhz:g} MHz: **FAIL**" not in summary
            or f"{target_mhz:g} MHz timing criterion: **FAIL**" not in summary
            or "Placement/routing completed: **yes**" not in summary
            or f"extracted routed Fmax: **{min(measured):.2f} MHz**" not in summary):
        raise ValueError("reported result differs from measured routed timing failure")
    return (f"MEASURED TIMING MISS: {board}/{variant} routed at "
            f"{min(measured):.2f} MHz vs {target_mhz:g} MHz constraint; "
            "receiver timing NOT certified")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--target-mhz", required=True, type=float)
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--pnr-log", type=Path, default=Path("build/pnr.log"))
    parser.add_argument("--summary", type=Path, default=Path("build/summary.md"))
    args = parser.parse_args()
    try:
        message = verify(args.board, args.variant, args.target_mhz, args.outcome,
                         args.pnr_log.read_text(), args.summary.read_text())
    except (OSError, ValueError) as exc:
        print(f"CAD evidence invalid: {exc}", file=sys.stderr)
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
