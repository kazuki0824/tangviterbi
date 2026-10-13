#!/usr/bin/env python3
"""Build the prior zero-DSP RS anchor and a shared-multiplier area candidate.

Keep these out of the adopted clock benchmark. Both derive from the same
constant-syndrome decoder and preserve its input/output cycle schedule.
"""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(shared=False):
    original = (ROOT / "experiments/rs_syndrome_constants.sv").read_text()
    gf = (ROOT / "experiments/gf256_boolean.sv").read_text()
    result = gf + original[original.index("endmodule") + len("endmodule"):]
    if not shared:
        return result
    replacements = {
        "gf256_mul u_coefficient_mul(.a(coefficient_a), .b(coefficient_b), .y(coefficient_y));\n"
        "    gf256_mul u_feedback_mul(.a(feedback_a), .b(feedback_b), .y(feedback_y));":
            "// Only these states consume the coefficient product. Other\n"
            "    // states consume feedback or neither product. Keep the operand\n"
            "    // register banks separate to avoid merging their wide next muxes.\n"
            "    wire coefficient_active = (state == ST_BM_DISC) ||\n"
            "        (state == ST_BM_COEF) || (state == ST_BM_UPDATE) ||\n"
            "        (state == ST_OMEGA_ACC);\n"
            "    wire [7:0] shared_y;\n"
            "    gf256_mul u_shared_mul(\n"
            "        .a(coefficient_active ? coefficient_a : feedback_a),\n"
            "        .b(coefficient_active ? coefficient_b : feedback_b), .y(shared_y));\n"
            "    assign coefficient_y = shared_y;\n"
            "    assign feedback_y = shared_y;",
    }
    for old, new in replacements.items():
        if result.count(old) != 1:
            raise ValueError("upstream RS source changed: expected one replacement")
        result = result.replace(old, new)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shared", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(source(args.shared))
