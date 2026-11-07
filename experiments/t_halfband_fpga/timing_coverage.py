#!/usr/bin/env python3
"""Inspect actual Gowin chipdb models and routed datapath endpoint coverage.

The v6 packed layouts are read from the exact nextpnr source commit. Model
absence is a negative coverage finding, not a parser/test failure. A recorded
headline Fmax is never promoted to full physical timing sign-off.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import lzma
from pathlib import Path
import re
import struct
import subprocess
import urllib.request

import msgpack

ROOT = Path(__file__).resolve().parents[2]
COMMIT = "e2fe86b3ce6feaa3f09d8db5c0971c1cda3fc641"
CURRENT_COMMIT = "a2c6479977d64d312686d853a93941744fdbeacf"
PINNED = {
    COMMIT: {"release": "2026-10-04", "archive_sha256": "8a4708629b0f0afd5a1835aca8b44d224fec5f6e544c5fd22a060ea5514f83c9",
             "chipdb_sha256": "28e74084da573c220ace2dd9ca381abf0f31db6be6599b81761dfc2416b4e8a3"},
    CURRENT_COMMIT: {"release": "2026-11-03", "archive_sha256": "f991f2b5a8204028100cf3ad2d14d97c005ce14b903b50edf71399da99b417ed",
                     "chipdb_sha256": "91ffbfb0831b48cad86179b07cb95f74c897ed804b244717f36977d50508f6c6"},
}
SOURCE_NAMES = ("himbaechel/chipdb.h", "common/kernel/relptr.h", "himbaechel/arch.cc",
                "himbaechel/uarch/gowin/gowin.cc", "himbaechel/uarch/gowin/gowin.h",
                "himbaechel/uarch/gowin/gowin_arch_gen.py", "himbaechel/uarch/gowin/constids.inc")
MODEL_TYPES = ("MULT18X18", "LUT1", "LUT2", "LUT3", "LUT4")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def sources(cache, commit):
    marker = cache / "commit.txt"
    try:
        cache.mkdir(parents=True, exist_ok=True)
        correct_cache = marker.exists() and marker.read_text().strip() == commit
    except OSError:
        correct_cache = False
    result, contents = [], {}
    for name in SOURCE_NAMES:
        url = f"https://raw.githubusercontent.com/YosysHQ/nextpnr/{commit}/{name}"
        try:
            path = cache / name
            if not correct_cache or not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(urllib.request.urlopen(url, timeout=30).read())
            data = path.read_bytes(); contents[name] = data.decode()
            result.append({"name": name, "url": url, "sha256": sha(data), "status": "PASS"})
        except Exception as exc:
            result.append({"name": name, "url": url, "status": "BLOCKED", "reason": str(exc)})
    if all(row["status"] == "PASS" for row in result):
        try:
            marker.write_text(commit + "\n")
        except OSError:
            # A read-only cache can still provide every inspected source.
            pass
    return result, contents


class ChipDB:
    """Read little-endian v6 RelPtr/RelSlice structures, with bounds checks."""
    def __init__(self, binary, constids):
        self.data = binary.read_bytes()
        self.root = self.pointer(0)
        header = [self.integer(self.root + n) for n in (0, 4, 8, 12)]
        if header[:2] != [0x00CA7CA7, 6]:
            raise ValueError(f"Unsupported chipdb magic/version: {header[:2]}")
        self.dimensions = header[2:]
        extra = self.pointer(self.root + 76)
        known = self.integer(extra)
        self.ids = [""] + re.findall(r"^X\(([^)]+)\)", constids, re.M)
        if len(self.ids) != known:
            raise ValueError("constids source count does not match chipdb known_id_count")
        self.ids.extend(self.string(self.pointer(p)) for p in self.slice(extra + 4, 4))

    def integer(self, pos):
        if not 0 <= pos <= len(self.data) - 4:
            raise ValueError("Integer field lies outside chipdb")
        return struct.unpack_from("<i", self.data, pos)[0]

    def pointer(self, pos):
        target = pos + self.integer(pos)
        if not 0 <= target < len(self.data):
            raise ValueError("Relative pointer lies outside chipdb")
        return target

    def slice(self, pos, stride):
        count = self.integer(pos + 4); target = self.pointer(pos)
        if not 0 <= count <= 1000000 or target + stride * count > len(self.data):
            raise ValueError("Invalid chipdb relative slice")
        return [target + stride * n for n in range(count)]

    def string(self, pos):
        return self.data[pos:self.data.index(0, pos)].decode()

    def name(self, pos):
        index = self.integer(pos)
        if not 0 <= index < len(self.ids):
            raise ValueError("Unknown chipdb constid index")
        return self.ids[index]

    def inventory(self):
        grades = {}
        # ChipInfo.speed_grades offset68; SpeedGradePOD size32; cell_types offset20.
        for speed in self.slice(self.root + 68, 32):
            models = {}
            for cell in self.slice(speed + 20, 12):
                pins = {}
                # CellTimingPOD size12; CellPinTimingPOD size24. Comb/reg arcs20/56 bytes.
                for pin in self.slice(cell + 4, 24):
                    pins[self.name(pin)] = {
                        "flags": self.integer(pin + 4),
                        "comb_inputs": [self.name(arc) for arc in self.slice(pin + 8, 20)],
                        "register_clocks": [self.name(arc) for arc in self.slice(pin + 16, 56)]}
                models[self.name(cell)] = pins
            grades[self.name(speed)] = {"model_count": len(models), "models": models,
                                       "selected_models_present": {name: name in models for name in MODEL_TYPES}}
        if not grades:
            raise ValueError("No speed-grade timing models decoded")
        return {"sha256": sha(self.data), "schema_version": 6, "dimensions": self.dimensions,
                "speed_grades": grades}


def group_endpoints(cells, report, kind):
    prefix = "p[iq][01]" if kind == "products" else "a[iq][01]"
    selected = {name: cell for name, cell in cells.items()
                if cell["type"].startswith("DFF") and re.search(r"(?:^|\.)" + prefix + r"_DFF", name)}
    if not selected:
        raise ValueError(f"No {kind} registers identified in routed design")
    endpoints = {(p["cell"], p["port"]) for net in report["detailed_net_timings"] for p in net["endpoints"]}
    drivers = {}
    for name, cell in cells.items():
        for port, direction in cell["port_directions"].items():
            if direction != "output":
                continue
            for bit in cell["connections"][port]:
                if isinstance(bit, int):
                    drivers.setdefault(bit, []).append({"cell": name, "port": port, "type": cell["type"]})
    members = []
    for name, cell in sorted(selected.items()):
        members.append({"cell": name, "type": cell["type"], "D_endpoint_recorded": (name, "D") in endpoints,
                        "CE_endpoint_recorded": (name, "CE") in endpoints,
                        "D_drivers": [driver for bit in cell["connections"]["D"] for driver in drivers.get(bit, [])]})
    return {"register_count": len(members), "D_endpoints_recorded": sum(m["D_endpoint_recorded"] for m in members),
            "CE_endpoints_recorded": sum(m["CE_endpoint_recorded"] for m in members), "members": members}


def evaluate(suite, cache, cad, profiles, commit):
    checks = []
    result = {"schema_version": 1, "evidence_origin": "Fresh chipdb/source/endpoint inspection, not recovered old report bytes",
              "non_fail_fast": True, "nextpnr_commit": commit,
              "toolchain": PINNED.get(commit, {}),
              "source_sha256": {"experiments/t_halfband_fpga/timing_coverage.py": sha(Path(__file__).read_bytes())},
              "profiles": {}, "physical_timing_pass": False}
    def check(name, fn):
        try: checks.append({"name": name, "status": "PASS" if fn() else "FAIL"})
        except Exception as exc: checks.append({"name": name, "status": "BLOCKED", "reason": f"{type(exc).__name__}: {exc}"})
    source_rows, contents = sources(cache, commit); result["sources"] = source_rows
    for row in source_rows:
        checks.append({"name": "source." + row["name"], "status": row["status"],
                       **({"reason": row["reason"]} if "reason" in row else {})})
    try:
        proc = subprocess.run([str(suite / "bin/nextpnr-himbaechel"), "--version"], text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        result["tool_version"] = {"exit_code": proc.returncode, "output": proc.stdout.strip()}
    except Exception as exc: result["tool_version"] = {"status": "BLOCKED", "reason": str(exc)}
    check("tool_version_command_success", lambda: result["tool_version"]["exit_code"] == 0)
    check("binary_version_matches_inspected_source_commit", lambda: commit[:8] in result["tool_version"]["output"])
    check("source_packed_chipinfo_layout", lambda: "struct ChipInfoPOD" in contents["himbaechel/chipdb.h"])
    check("source_database_version6", lambda: "static constexpr int database_version = 6" in contents["himbaechel/arch.cc"])
    check("source_lookup_uses_cell_type", lambda: "ci->timing_index = get_cell_timing_idx(ci->type)" in contents["himbaechel/arch.cc"])
    check("source_missing_model_ignores_timing_port", lambda: bool(re.search(
        r"get_port_timing_class_default.*?if \(cell->timing_index == -1\)\s*return TMG_IGNORE;",
        contents["himbaechel/arch.cc"], re.S)))
    check("source_missing_model_has_no_default_delay", lambda: bool(re.search(
        r"get_cell_delay_default.*?if \(cell->timing_index == -1\)\s*return false;",
        contents["himbaechel/arch.cc"], re.S)))
    check("gowin_header_does_not_override_default_cell_timing", lambda: not re.search(
        r"getCellDelay|getPortTimingClass|getPortClockingInfo", contents["himbaechel/uarch/gowin/gowin.h"]))
    try:
        binary = suite / "share/nextpnr/himbaechel/gowin/chipdb-GW2A-18C.bin"
        result["chipdb"] = ChipDB(binary, contents["himbaechel/uarch/gowin/constids.inc"]).inventory()
        checks.append({"name": "actual_chipdb_inventory", "status": "PASS"})
    except Exception as exc:
        result["chipdb"] = {"status": "BLOCKED", "reason": str(exc)}
        checks.append({"name": "actual_chipdb_inventory", "status": "BLOCKED", "reason": str(exc)})
    check("target_speed_grade_is_present", lambda: "C8/I7" in result["chipdb"]["speed_grades"])
    check("chipdb_hash_matches_pinned_suite", lambda: result["chipdb"]["sha256"] == result["toolchain"]["chipdb_sha256"])
    try:
        path = suite / "lib/python3.11/site-packages/apycula/GW2A-18C.msgpack.xz"
        packed = path.read_bytes()
        db = msgpack.unpackb(lzma.decompress(packed), raw=False, strict_map_key=False, use_list=False)
        result["apicula_source_model_inventory"] = {"sha256": sha(packed), "groups_by_speed_grade":
            {name: sorted(groups) for name, groups in db["timing"].items()}}
        checks.append({"name": "apicula_source_inventory", "status": "PASS"})
    except Exception as exc:
        result["apicula_source_model_inventory"] = {"status": "BLOCKED", "reason": str(exc)}
        checks.append({"name": "apicula_source_inventory", "status": "BLOCKED", "reason": str(exc)})
    for profile in profiles:
        row = result["profiles"][profile] = {}
        cells = report = None
        try:
            packed = (cad / profile / "routed.json.gz").read_bytes()
            cells = json.loads(gzip.decompress(packed))["modules"]["top"]["cells"]
            row["routed_gzip_sha256"] = sha(packed)
            row["cells_by_type"] = dict(sorted(Counter(c["type"] for c in cells.values()).items()))
            checks.append({"name": profile + ".routed_netlist_readable", "status": "PASS"})
        except Exception as exc: checks.append({"name": profile + ".routed_netlist_readable", "status": "BLOCKED", "reason": str(exc)})
        try:
            data = (cad / profile / "pnr.json").read_bytes(); report = json.loads(data)
            row["pnr_json_sha256"] = sha(data); row["reported_fmax_NOT_physical_signoff"] = report["fmax"]
            row["critical_paths"] = [{"delay_ns": sum(segment["delay"] for segment in p["path"]),
                "from": p["path"][0]["from"], "to": p["path"][-1]["to"]} for p in report["critical_paths"]]
            checks.append({"name": profile + ".pnr_report_readable", "status": "PASS"})
        except Exception as exc: checks.append({"name": profile + ".pnr_report_readable", "status": "BLOCKED", "reason": str(exc)})
        for kind in ("products", "accumulators"):
            try:
                row[kind] = group_endpoints(cells, report, kind)
                checks.append({"name": profile + "." + kind + ".endpoints_inspected", "status": "PASS"})
            except Exception as exc:
                row[kind] = {"status": "BLOCKED", "reason": str(exc)}
                checks.append({"name": profile + "." + kind + ".endpoints_inspected", "status": "BLOCKED", "reason": str(exc)})
            expected = 160 if kind == "accumulators" else 4 * (26 if profile.startswith("baseline") else 32)
            check(profile + "." + kind + ".all_expected_registers_found",
                  lambda row=row, kind=kind, expected=expected: row[kind]["register_count"] == expected)
    result["checks"] = checks
    result["status"] = "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL"
    result["missing_models_by_speed_grade"] = {name: [k for k in MODEL_TYPES if k not in grade["models"]]
        for name, grade in result["chipdb"].get("speed_grades", {}).items()}
    result["coverage_gate"] = "FAIL" if result["missing_models_by_speed_grade"].get("C8/I7") else "UNVERIFIED"
    result["endpoint_interpretation"] = "D endpoints and model inventory must be considered together. Endpoint presence alone is not proof of every arc; CE coverage does not imply D coverage."
    result["vendor_STA"] = {"executed": False, "physical_timing_status": "UNVERIFIED",
        "required_evidence": "A supported full DSP/datapath timing model and routed STA at the target constraint; no guessed DSP delay is substituted."}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True); parser.add_argument("--source-cache", type=Path, required=True)
    parser.add_argument("--cad", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--commit", default=COMMIT)
    parser.add_argument("--profiles", nargs="+", default=["baseline", "baseline-fifo", "residual", "residual-fifo"])
    args = parser.parse_args()
    result = evaluate(args.suite.resolve(), args.source_cache.resolve(), args.cad.resolve(), args.profiles, args.commit)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "timing-coverage.json.gz").write_bytes(gzip.compress((json.dumps(result, indent=2) + "\n").encode(), mtime=0))
    print(json.dumps({"status": result["status"], "coverage_gate": result["coverage_gate"],
                      "checks": dict(Counter(c["status"] for c in result["checks"])),
                      "missing_models": result["missing_models_by_speed_grade"]}))
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
