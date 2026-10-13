// Lossless native I10/Q10 unpacker after the two-port byte-order reassembler.
// 32-bit little-endian words, no page padding. Pages (4096 B) split 5-byte pairs.
// Flush/reset ONLY at a stopped epoch boundary. Not an RF demodulator.
module s3_iq10_unpack (
    input wire clk, resetn,
    input wire in_valid, output wire in_ready, input wire [31:0] in_data,
    output wire out_valid, input wire out_ready,
    output wire signed [9:0] out_i, out_q
);
    reg [63:0] reservoir;
    reg [6:0] count;
    wire pop = out_valid && out_ready;
    wire [6:0] remaining = count - (pop ? 7'd20 : 7'd0);
    assign out_valid = count >= 20;
    assign in_ready = remaining <= 32;
    wire push = in_valid && in_ready;
    assign out_i = reservoir[9:0];
    assign out_q = reservoir[19:10];
    wire [63:0] retained = pop ? (reservoir >> 20) : reservoir;
    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin reservoir <= 0; count <= 0; end
        else begin
            count <= remaining + (push ? 7'd32 : 7'd0);
            reservoir <= retained | (push ? ({32'd0, in_data} << remaining) : 64'd0);
        end
    end
endmodule
