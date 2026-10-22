"""Audit the public Gowin reference archive without redistributing vendor IP.

Usage: python experiments/sdram_reference_audit.py ARCHIVE EXTRACTED_SDRC_DIR
The result is provenance and clock consistency, not SDRAM qualification.
"""
import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path
import re


def audit(archive, root):
    paths = ["docs/Readme.txt", "project/SDRAM_Controller_top.gprj",
             "project/src/SDRAM_Controller_top.sdc", "project/src/gw_pll/gw_pll.v",
             "project/src/gw_pll/gw_pll.ipc", "tb/tb.v", "simulation/vcs.sh",
             "simulation/prim_sim.v",
             "project/src/SDRAM_controller_top_SIP/SDRAM_controller_top_SIP.ipc"]
    sources = {p: (root / p).read_text() for p in paths}
    pll = sources[paths[3]]
    def value(name):
        return int(re.search(r"defparam pll_inst\." + name + r" = (\d+);", pll)[1])
    input_mhz = Fraction(re.search(r'FCLKIN = "([\d.]+)"', pll)[1])
    pll_mhz = input_mhz * (value("FBDIV_SEL") + 1) / (value("IDIV_SEL") + 1)
    sdc = sources[paths[2]]
    period = Fraction(re.search(r"create_clock .*?-period ([\d.]+)", sdc)[1])
    multipliers = re.findall(r"-multiply_by (\d+)", sdc)
    sdc_mhz = [1000 / period * int(m) for m in multipliers]
    assert len(sdc_mhz) == 2
    return {
        "archive_url": "https://www.gowinsemi.com/upload/database_doc/2058/document/64f5457822ba5.rar",
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files_sha256": {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
        "readme_device": re.search(r"Object device:(\S+)", sources[paths[0]])[1],
        "pll_input_MHz": float(input_mhz),
        "pll_idiv_sel": value("IDIV_SEL"), "pll_fbdiv_sel": value("FBDIV_SEL"),
        "pll_output_MHz": float(pll_mhz),
        "sdc_generated_MHz": [float(x) for x in sdc_mhz],
        "pll_matches_sdc": all(pll_mhz == x for x in sdc_mhz),
        "clock_underconstraint_percent": float((pll_mhz / sdc_mhz[0] - 1) * 100),
        "sdc_has_input_output_delays": bool(re.search(r"set_(?:input|output)_delay", sdc)),
        "memory_model_status": "No independent SDRAM timing model found in archive inspection; tb connects only DUT, prim_sim contains FPGA primitives.",
        "qualified_for_QN88": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.archive, args.root), indent=2))
