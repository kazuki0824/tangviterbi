#!/usr/bin/env python3
"""ISDB outer-code conventions over the bounded schedule experiment.

ARIB STD-B31 v2.2 section 3.3 and ITU-R BO.1408 section 2 use roots alpha^0
through alpha^15 and a shortened (255,239) code with 51 leading zero bytes.
This fixes conventions in the benchmark decoder; production RTL is untouched.
"""
import argparse
from pathlib import Path
from s3_rs_schedule import source as schedule_source, replace_once


def source(predecode=False):
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
    if predecode:
        # n and L remain unchanged between START and POST. Compute the
        # promote/overflow decision there, well before its consumers. Explicit
        # five-bit arithmetic preserves the degree-16 early-fail case.
        text = replace_once(text, "    reg [4:0] bm_n;", "    reg [3:0] bm_n;")
        text = replace_once(text, "    reg [4:0] omega_j;", "    reg [3:0] omega_j;")
        text = replace_once(text, "    reg [4:0] forney_k;", "    reg [3:0] forney_k;")
        text = replace_once(text, "    integer read_slot;", """    reg bm_promote, bm_degree_overflow;
    reg [4:0] bm_next_degree;
    always @(posedge clk) begin
        if (state == ST_BM_START) begin
            bm_promote <= ({1'b0, bm_l} << 1) <= {1'b0, bm_n};
            bm_next_degree <= {1'b0, bm_n} + 5'd1 - {1'b0, bm_l};
            bm_degree_overflow <= ({1'b0, bm_n} + 5'd1) > ({1'b0, bm_l} + 5'd8);
        end
    end
    integer read_slot;""")
        old = "((bm_l << 1) <= bm_n)"
        if text.count(old) != 2:
            raise ValueError("expected polynomial-copy and BM POST promote checks")
        text = text.replace(old, "(bm_promote)")
        text = replace_once(text, "bm_l <= bm_n + 1 - bm_l;", "bm_l <= bm_next_degree[3:0];")
        text = replace_once(text, """((({1'b0, bm_l} << 1) <= bm_n) &&
                        ((bm_n + 5'd1) > ({1'b0, bm_l} + 5'd8)))""",
                            "(bm_promote && bm_degree_overflow)")
        # Break the counter -> variable shift -> state mux -> selection FF
        # path. Each consumer follows at least one stable-counter cycle:
        # BM CHECK/POST follow START/DISC; Omega exit follows its product;
        # Chien starts after all 16 Omega coefficients have been computed.
        for old, new in (("9'd1 << bm_m", "bm_m_mask"),
                         ("16'd1 << bm_n", "bm_n_mask"),
                         ("16'd1 << (omega_j + 5'd1)", "omega_next_mask"),
                         ("9'd1 << bm_l", "degree_mask")):
            if old not in text:
                raise ValueError(f"missing selection decode: {old}")
            text = text.replace(old, new)
        text = replace_once(text, "    integer read_slot;", """    reg [8:0] bm_m_mask, degree_mask;
    reg [15:0] bm_n_mask, omega_next_mask;
    always @(posedge clk) begin
        bm_m_mask <= 9'd1 << bm_m;
        bm_n_mask <= 16'd1 << bm_n;
        omega_next_mask <= 16'd1 << (omega_j + 5'd1);
        degree_mask <= 9'd1 << bm_l;
    end
    integer read_slot;""")
    return text


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--predecode", action="store_true")
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(source(args.predecode))
