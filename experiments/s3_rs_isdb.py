#!/usr/bin/env python3
"""ISDB outer-code conventions over the bounded schedule experiment.

ARIB STD-B31 v2.2 section 3.3 and ITU-R BO.1408 section 2 use roots alpha^0
through alpha^15 and a shortened (255,239) code with 51 leading zero bytes.
This fixes conventions in the benchmark decoder; production RTL is untouched.
"""
import argparse
from pathlib import Path
from s3_rs_schedule import source as schedule_source, replace_once


def source():
    text = schedule_source()
    text = replace_once(text, "alpha_factor(slot+1)", "alpha_factor(slot)")
    text = replace_once(text, "    localparam ST_BLOCK_RESET    = 6'd28;",
                        "    localparam ST_BLOCK_RESET    = 6'd28;\n    localparam ST_INV_ADDRESS    = 6'd29;")
    text = replace_once(text, """wire [7:0] inverse_address = (state == ST_FORNEY_D2) ?
        (feedback_y ^ lambda_q) : bval;""", """wire [7:0] inverse_address = (state == ST_INV_ADDRESS) ?
        coefficient_y : bval;""")
    text = replace_once(text, """            ST_BM_COEF: begin
                coefficient_next_a""", """            ST_FORNEY_D2: begin
                // For first root b=0, magnitude = Omega(x)/(Lambda'(x)*x).
                coefficient_next_a = feedback_y ^ lambda_q;
                coefficient_next_b = error_x_q;
            end
            ST_BM_COEF: begin
                coefficient_next_a""")
    text = replace_once(text, """                ST_INV_SQUARE: begin
                    state <= inv_mode""", """                ST_INV_ADDRESS: state <= ST_INV_SQUARE;
                ST_INV_SQUARE: begin
                    state <= inv_mode""")
    text = replace_once(text, """                    inv_mode <= 1'b1;
                    state <= ST_INV_SQUARE;""", """                    inv_mode <= 1'b1;
                    state <= ST_INV_ADDRESS;""")
    text = replace_once(text, """                ST_CHIEN_INIT: begin
                    chien_x <= 8'd1;""", """                ST_CHIEN_INIT: begin
                    // Byte j is coefficient x^(203-j), hence locator root
                    // alpha^(j-203) = alpha^(j+52) in the 255-element group.
                    chien_x <= alpha_factor(52);""")
    text = replace_once(text, "feedback_next_a = lambda_q; feedback_next_b = 1;",
                        "feedback_next_a = lambda_q; feedback_next_b = alpha_factor(52);")
    return text


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(source())
