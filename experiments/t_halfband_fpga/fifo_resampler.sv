// Reconstructed v2: 512 total buffered complex samples, including the front
// register. The source must observe in_ready, or a refused sample is lost.
module t_diag_fifo_resampler #(
    parameter integer INPUT_BITS = 16,
    parameter integer L = 64,
    parameter integer OUTPUT_SHIFT = 15,
    parameter COEFF_FILE = "coeff_residual.hex"
) (
    input wire clk, resetn,
    input wire in_valid,
    output wire in_ready,
    input wire signed [INPUT_BITS-1:0] in_i, in_q,
    output wire out_valid,
    input wire out_ready,
    output wire signed [15:0] out_i, out_q
);
    reg [2*INPUT_BITS-1:0] fifo [0:511];
    reg [8:0] write_pos, read_pos;
    reg [9:0] count;
    reg [2*INPUT_BITS-1:0] front;
    reg front_valid;
    wire core_ready;
    assign in_ready = resetn && count < 512;
    wire push = in_valid && in_ready;
    wire pop = front_valid && core_ready;
    wire fetch = (!front_valid || core_ready) && count > (front_valid ? 1 : 0);
    always @(posedge clk) begin
        if (push) fifo[write_pos] <= {in_q, in_i};
        if (fetch) front <= fifo[read_pos];
        if (!resetn) begin
            write_pos <= 0; read_pos <= 0; count <= 0; front_valid <= 0;
        end else begin
            if (push) write_pos <= write_pos + 1'b1;
            if (fetch) begin read_pos <= read_pos + 1'b1; front_valid <= 1; end
            else if (pop) front_valid <= 0;
            case ({push, pop})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
            endcase
        end
    end
    t_diag_resampler #(.INPUT_BITS(INPUT_BITS), .L(L),
       .OUTPUT_SHIFT(OUTPUT_SHIFT), .COEFF_FILE(COEFF_FILE)) core (
       .clk(clk), .resetn(resetn), .in_valid(front_valid), .in_ready(core_ready),
       .in_i(front[INPUT_BITS-1:0]), .in_q(front[2*INPUT_BITS-1:INPUT_BITS]),
       .out_valid(out_valid), .out_ready(out_ready), .out_i(out_i), .out_q(out_q));
endmodule
