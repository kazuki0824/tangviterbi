`timescale 1ns/1ps
module gf256_tb;
    reg [7:0] a, b;
    wire [7:0] y;
    reg [15:0] polynomial;
    integer ia, ib, bit_index;
    gf256_mul dut(a, b, y);
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
        $finish;
    end
endmodule
