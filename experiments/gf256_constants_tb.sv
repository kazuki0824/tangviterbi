`timescale 1ns/1ps
module gf256_tb;
    reg [7:0] a, b;
    wire [7:0] y;
    reg [15:0] polynomial;
    integer ia, ib, bit_index, power;
    reg [15:0] alpha;
    gf256_mul dut(a, b, y);
    rs204_188_compact decoder(.clk(1'b0), .resetn(1'b0), .in_valid(1'b0), .in_byte(8'd0));
    initial begin
        // Independent carryless polynomial product followed by long division
        // by x^8+x^4+x^3+x^2+1 (0x11d), for every operand pair.
        for (ia = 0; ia < 256; ia = ia + 1)
            for (ib = 0; ib < 256; ib = ib + 1) begin
                a = ia; b = ib;
                polynomial = 0;
                for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1)
                    if (ib & (1 << bit_index)) polynomial = polynomial ^ (ia << bit_index);
                for (bit_index = 14; bit_index >= 8; bit_index = bit_index - 1)
                    if (polynomial[bit_index]) polynomial = polynomial ^ (16'h11d << (bit_index - 8));
                #1;
                if (y !== polynomial[7:0])
                    $fatal(1, "GF mismatch: %h * %h = %h, expected %h", a, b, y, polynomial[7:0]);
            end
        $display("PASS: all 65536 GF(256) products against polynomial division");
        // Check all 16 constant syndrome transforms against the same independent
        // polynomial oracle. Alpha powers are derived here by long division.
        alpha = 1;
        for (power = 1; power <= 16; power = power + 1) begin
            alpha = alpha << 1;
            if (alpha[8]) alpha = alpha ^ 16'h11d;
            if (decoder.alpha_factor(power) !== alpha[7:0])
                $fatal(1, "alpha factor mismatch at power %0d", power);
            for (ia = 0; ia < 256; ia = ia + 1) begin
                polynomial = 0;
                for (bit_index = 0; bit_index < 8; bit_index = bit_index + 1)
                    if (alpha[bit_index]) polynomial = polynomial ^ (ia << bit_index);
                for (bit_index = 14; bit_index >= 8; bit_index = bit_index - 1)
                    if (polynomial[bit_index]) polynomial = polynomial ^ (16'h11d << (bit_index - 8));
                if (decoder.gf_constant(ia[7:0], alpha[7:0]) !== polynomial[7:0])
                    $fatal(1, "constant GF mismatch at power %0d input %0d", power, ia);
            end
        end
        $display("PASS: all 4096 constant syndrome products and 16 alpha powers");
        $finish;
    end
endmodule
