#!/usr/bin/env python3
"""Latency experiments over the frozen decoder; not an ARIB-qualified decoder.

Use a synchronous inverse ROM and overlap Chien root detection/position update
with the final Horner step. Keep the existing decoder's byte/fail semantics.
"""
import argparse
from pathlib import Path
from s3_rs_area import source as area_source


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"expected one source anchor: {old[:100]!r}")
    return text.replace(old, new)


def multiply(a, b):
    product = 0
    for _ in range(8):
        if b & 1:
            product ^= a
        a = ((a << 1) ^ (0x11d if a & 128 else 0)) & 255
        b >>= 1
    return product


def inverse(a):
    # Match exponentiation x**254, including the reference's zero -> zero.
    value = 1
    for _ in range(254):
        value = multiply(value, a)
    return value


def source(chien=True, bounded=True):
    text = area_source()
    text = replace_once(text, """if (!resetn) begin
                lambda[slot] <= 8'd0;
                bpoly[slot] <= 8'd0;
                temp_poly[slot] <= 8'd0;
            end else begin""", "if (resetn) begin")
    text = replace_once(text, """for (slot=0; slot<9; slot=slot+1) begin : g_polynomial
        always @(posedge clk or negedge resetn)""", """for (slot=0; slot<9; slot=slot+1) begin : g_polynomial
        always @(posedge clk)""")
    rom = """
    // Registered read, no asynchronous reset: infer one Gowin BSRAM ROM.
    reg [7:0] inverse_rom [0:255];
    reg [7:0] inverse_q;
    wire [7:0] inverse_address = (state == ST_FORNEY_D2) ?
        (feedback_y ^ lambda_q) : bval;
    initial begin
""" + "".join(f"        inverse_rom[{i}] = 8'h{inverse(i):02x};\n" for i in range(256)) + """    end
    always @(posedge clk) inverse_q <= inverse_rom[inverse_address];
"""
    # Recent Icarus rejects continuous-initializer forward references. Emit
    # the ROM after all FSM/operand declarations, before executable processes.
    text = replace_once(text, "    integer read_slot;", rom + "\n    integer read_slot;")
    start = text.index("                ST_INV_SQUARE: begin\n                    inv_acc")
    end = text.index("                ST_BM_COEF: begin", start)
    text = text[:start] + """                ST_INV_SQUARE: begin
                    state <= inv_mode ? ST_FORNEY_MAG : ST_BM_COEF;
                end

""" + text[end:]
    text = replace_once(text, """                if (!inv_exponent_bit(inv_bit) && !inv_mode) begin
                    coefficient_next_a = discrepancy; coefficient_next_b = feedback_y;
                end""", """                if (!inv_mode) begin
                    coefficient_next_a = discrepancy; coefficient_next_b = inverse_q;
                end""")
    text = replace_once(text, """                if (inv_exponent_bit(inv_bit)) begin
                    feedback_next_a = feedback_y; feedback_next_b = bval;
                end else if (inv_mode) begin
                    feedback_next_a = omega_value; feedback_next_b = feedback_y;
                end""", """                if (inv_mode) begin
                    feedback_next_a = omega_value; feedback_next_b = inverse_q;
                end""")
    # Selection -> q -> consumption needs two cycles; start BM prefetch in CHECK.
    text = replace_once(text, "lambda_select <= ((bm_n == 15) && (discrepancy == 0)) ? 9'd1 : 9'd2;",
                        "lambda_select <= (discrepancy != 0) ? (9'd1 << bm_m) : ((bm_n == 15) ? 9'd1 : 9'd2);")
    if bounded:
        # bm_l is only four bits. Check the prospective degree at five-bit
        # width BEFORE writing it; degree 16 must not wrap to zero. This
        # intentionally defines an early-fail path absent in the old decoder.
        old = """                    if (bm_n == 5'd15)
                        state <= ST_OMEGA_INIT;
                    else begin
                        bm_n <= bm_n + 5'd1;
                        state <= ST_BM_START;
                    end
                end

                ST_OMEGA_INIT:"""
        new = """                    if ((({1'b0, bm_l} << 1) <= bm_n) &&
                        ((bm_n + 5'd1) > ({1'b0, bm_l} + 5'd8))) begin
                        // Uncorrectable degree: no correction has touched RAM.
                        block_fail <= 1'b1;
                        out_index <= 8'd0;
                        out_primed <= 1'b0;
                        state <= ST_OUTPUT;
                    end else if (bm_n == 5'd15)
                        state <= ST_OMEGA_INIT;
                    else begin
                        bm_n <= bm_n + 5'd1;
                        state <= ST_BM_START;
                    end
                end

                ST_OMEGA_INIT:"""
        text = replace_once(text, old, new)
    if not chien:
        return text
    text = replace_once(text, "    reg [7:0] chien_acc;", "    reg [7:0] chien_acc;\n    reg [7:0] chien_top;")
    text = replace_once(text, "    integer read_slot;", """
    wire chien_finish = ((state == ST_CHIEN_EVAL) && (chien_k == 0)) ||
                         (state == ST_CHIEN_CHECK);
    wire [7:0] chien_result = (state == ST_CHIEN_CHECK) ?
        chien_acc : (feedback_y ^ lambda_q);
    // Captured before the first position; no extra coefficient-array mux.
    always @(posedge clk)
        if (state == ST_CHIEN_INIT) chien_top <= lambda_q;
    integer read_slot;""")
    start = text.index("            ST_CHIEN_INIT, ST_CHIEN_EVAL: begin")
    end = text.index("            ST_FORNEY_INIT, ST_FORNEY_WRITE:", start)
    text = text[:start] + """            ST_CHIEN_INIT: begin
                lambda_select <= (bm_l <= 1) ? 9'd1 : (lambda_select >> 1);
            end
            ST_CHIEN_EVAL: begin
                // q receives lambda[0] during k=1; simultaneously select
                // the first coefficient of the next position for k=0.
                if (bm_l <= 1) lambda_select <= 9'd1;
                else if (chien_k == 1) lambda_select <= (9'd1 << bm_l) >> 1;
                else lambda_select <= lambda_select >> 1;
            end
            ST_CHIEN_CHECK: lambda_select <= 9'd1;
""" + text[end:]
    text = replace_once(text, "(state == ST_CHIEN_CHECK) && (chien_acc == 0)",
                        "chien_finish && (chien_result == 0)")
    text = replace_once(text, """            ST_CHIEN_EVAL: begin
                feedback_next_a = feedback_y ^ lambda_q; feedback_next_b = chien_x;
            end
            ST_CHIEN_CHECK: begin
                feedback_next_a = chien_x; feedback_next_b = 8'h02;
            end
            ST_CHIEN_NEXT: begin
                feedback_next_a = lambda_q; feedback_next_b = feedback_y;
            end""", """            ST_CHIEN_EVAL: begin
                if (chien_k == 0) begin
                    feedback_next_a = chien_top;
                    feedback_next_b = gf_xtime(chien_x);
                end else begin
                    feedback_next_a = feedback_y ^ lambda_q;
                    feedback_next_b = chien_x;
                end
            end""")
    start = text.index("                ST_CHIEN_EVAL: begin\n                    chien_acc")
    end = text.index("                ST_FORNEY_INIT: begin", start)
    text = text[:start] + """                ST_CHIEN_EVAL, ST_CHIEN_CHECK: begin
                    if (chien_finish) begin
                        if ((chien_result == 0) && (error_count < 8))
                            error_count <= error_count + 4'd1;
                        chien_x <= gf_xtime(chien_x);
                        if (chien_pos == 8'd203) state <= ST_FORNEY_INIT;
                        else begin
                            chien_pos <= chien_pos + 8'd1;
                            chien_acc <= chien_top;
                            chien_k <= (bm_l == 0) ? 0 : (bm_l - 1'b1);
                            state <= (bm_l == 0) ? ST_CHIEN_CHECK : ST_CHIEN_EVAL;
                        end
                    end else begin
                        chien_acc <= feedback_y ^ lambda_q;
                        chien_k <= chien_k - 4'd1;
                    end
                end

""" + text[end:]
    return text


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--inverse-only", action="store_true")
    parser.add_argument("--unbounded-reference-semantics", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(source(not args.inverse_only, not args.unbounded_reference_semantics))
