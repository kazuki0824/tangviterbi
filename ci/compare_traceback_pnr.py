"""Run identical Gowin P&R probe for baseline and experimental 64/64 traceback."""
import argparse
import sys
from pathlib import Path
from ci import three_context_k7_evidence as evidence
from experiments.three_context_k7 import generate

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--variant", choices=("baseline", "window", "coole-scheduled", "bm-staged", "bm-delta", "32acs"), required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    if args.variant == "32acs":
        source = (ROOT / "rtl/three_context_k7_32acs.sv").read_text()
        evidence.generate = lambda split_banks=True: source.replace("module three_context_k7_32acs #(", "module three_context_k7 #(", 1)
    elif args.variant == "bm-delta":
        source = (ROOT / "rtl/three_context_k7_bm_delta.sv").read_text()
        assert "module three_context_k7_bm_delta #(" in source
        evidence.generate = lambda split_banks=True: source.replace("module three_context_k7_bm_delta #(", "module three_context_k7 #(", 1)
    elif args.variant == "bm-staged":
        source = (ROOT / "rtl/three_context_k7_bm_staged.sv").read_text()
        assert "module three_context_k7_bm_staged #(" in source
        candidate = source.replace("module three_context_k7_bm_staged #(", "module three_context_k7 #(", 1)
        evidence.generate = lambda split_banks=True: candidate
    elif args.variant == "coole-scheduled":
        source = (ROOT / "rtl/three_context_k7_coole_scheduled.sv").read_text()
        assert "module three_context_k7_coole_scheduled #(" in source
        candidate = source.replace("module three_context_k7_coole_scheduled #(", "module three_context_k7 #(", 1)
        evidence.generate = lambda split_banks=True: candidate
    elif args.variant == "window":
        source = (ROOT / "rtl/three_context_k7_window.sv").read_text()
        assert "module three_context_k7_window #(" in source
        candidate = source.replace("module three_context_k7_window #(", "module three_context_k7 #(", 1)
        evidence.generate = lambda split_banks=True: candidate
    else:
        evidence.generate = generate
    sys.argv = ["three_context_k7_evidence.py", "--output", args.output, "--frequency", "108"]
    evidence.main()

if __name__ == "__main__":
    main()
