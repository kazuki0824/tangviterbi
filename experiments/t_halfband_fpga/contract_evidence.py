#!/usr/bin/env python3
"""Record the scope of available original-filter and diagnostic-filter evidence.

This is a bounded review of named repository sources, not a proof that no
receiver-quality specification exists anywhere. Readable evidence is separate
from an accepted coefficient/rounding/MER/CN/BER contract, which is not supplied
by these sources. Missing inputs never hide the remaining review conditions.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    "reports/s3-preprocess-break-even/original-fir-model.json": "Recovered original cycle/tap-count model, including its explicit filter-contract scope",
    "experiments/t_preprocess_capacity/accx_wrapper.h": "Original fractional-FIR comparison candidate API and trial rounding contract",
    "experiments/t_preprocess_capacity/halfband31.h": "Halfband candidate API and its explicit receiver-quality limitation",
    "experiments/t_halfband_fpga/coefficients.py": "Diagnostic coefficient reconstruction and mathematical generator scope",
    "reports/s3-t-preprocess-integration/README.md": "Retained historical technical observations and previously unresolved quality equivalence",
}


def evaluate():
    rows, checks, contents = [], [], {}
    pattern = re.compile(r"receiver|受信|MER|C/N|BER|filter_contract|contract|Kaiser|係数|丸め", re.I)
    for name, role in SOURCES.items():
        try:
            data = (ROOT / name).read_bytes(); text = data.decode()
            contents[name] = text
            rows.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(), "role": role,
                         "relevant_lines": [{"line": n, "text": line[:600]} for n, line in enumerate(text.splitlines(), 1) if pattern.search(line)]})
            checks.append({"name": "source_readable." + name, "status": "PASS"})
        except Exception as exc:
            rows.append({"path": name, "role": role, "status": "BLOCKED", "reason": str(exc)})
            checks.append({"name": "source_readable." + name, "status": "BLOCKED", "reason": str(exc)})
    predicates = [
        ("original_model_states_coefficient_contract_is_unspecified", lambda:
         "not a coefficient-bound quality acceptance contract" in json.loads(contents["reports/s3-preprocess-break-even/original-fir-model.json"])["filter_contract_status"]),
        ("fractional_FIR_header_calls_output_contract_trial", lambda:
         "Output trial contract" in contents["experiments/t_preprocess_capacity/accx_wrapper.h"]),
        ("halfband_header_disclaims_accepted_receiver_quality", lambda:
         "not an accepted receiver-quality contract" in contents["experiments/t_preprocess_capacity/halfband31.h"]),
    ]
    for name, fn in predicates:
        try: checks.append({"name": name, "status": "PASS" if fn() else "FAIL"})
        except Exception as exc: checks.append({"name": name, "status": "BLOCKED", "reason": str(exc)})
    return {"schema_version": 1, "evidence_origin": "Fresh scoped source review; no claim to restore lost report bytes",
            "source_sha256": {str(Path(__file__).resolve().relative_to(ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            "non_fail_fast": True, "sources": rows, "checks": checks,
            "status": "PASS" if all(c["status"] == "PASS" for c in checks) else "FAIL",
            "receiver_quality_equivalence": "UNVERIFIED",
            "missing_normative_inputs": ["Accepted original filter coefficients and per-phase response requirements",
                "Accepted receiver rounding, scale, saturation and output sample timing contract",
                "Accepted receiver test vectors plus MER, C/N and BER limits under defined channels"],
            "scope": "Only the listed sources were inspected. No assertion is made that another unreviewed source cannot specify the contract.",
            "diagnostic_evaluation_meaning": "Diagnostic frequency and integer tests verify the chosen candidate; they do not certify original-receiver equivalence.",
            "receiver_adoption": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); result = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"status": result["status"], "checks": dict(Counter(c["status"] for c in result["checks"])),
                      "receiver_quality_equivalence": result["receiver_quality_equivalence"]}))
    return int(result["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
