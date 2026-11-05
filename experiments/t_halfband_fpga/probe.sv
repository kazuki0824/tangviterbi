// Identical scan wrapper for both comparison profiles; this is a resource and
// timing probe, not the receiver's SPI transport or integrated ADC interface.
module t_diag_probe #(
    parameter integer INPUT_BITS = 16,
    parameter integer L = 64,
    parameter integer OUTPUT_SHIFT = 15,
    parameter integer USE_FIFO = 1,
    parameter COEFF_FILE = "coeff_residual.hex"
) (input wire clk, resetn, scan_enable, scan_in, output reg signature);
    reg [2*INPUT_BITS-1:0] input_shift;
    wire in_ready, out_valid;
    wire signed [15:0] out_i, out_q;
    always @(posedge clk) begin
        if (!resetn) begin input_shift <= 0; signature <= 0; end
        else begin
            if (scan_enable && in_ready) input_shift <= {input_shift[2*INPUT_BITS-2:0], scan_in};
            if (out_valid) signature <= ^{out_i, out_q, signature};
        end
    end
    generate if (USE_FIFO) begin: g_fifo
        t_diag_fifo_resampler #(.INPUT_BITS(INPUT_BITS),.L(L),
            .OUTPUT_SHIFT(OUTPUT_SHIFT),.COEFF_FILE(COEFF_FILE)) dut (
            .clk(clk),.resetn(resetn),.in_valid(scan_enable),.in_ready(in_ready),
            .in_i(input_shift[INPUT_BITS-1:0]),.in_q(input_shift[2*INPUT_BITS-1:INPUT_BITS]),
            .out_valid(out_valid),.out_ready(1'b1),.out_i(out_i),.out_q(out_q));
    end else begin: g_core
        t_diag_resampler #(.INPUT_BITS(INPUT_BITS),.L(L),
            .OUTPUT_SHIFT(OUTPUT_SHIFT),.COEFF_FILE(COEFF_FILE)) dut (
            .clk(clk),.resetn(resetn),.in_valid(scan_enable),.in_ready(in_ready),
            .in_i(input_shift[INPUT_BITS-1:0]),.in_q(input_shift[2*INPUT_BITS-1:INPUT_BITS]),
            .out_valid(out_valid),.out_ready(1'b1),.out_i(out_i),.out_q(out_q));
    end endgenerate
endmodule
