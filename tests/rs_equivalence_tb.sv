`timescale 1ns/1ps
module rs_equivalence_tb;
    reg clk = 0;
    always #5 clk = ~clk;
    reg resetn = 0;
    reg in_valid = 0;
    reg [7:0] in_byte = 0;
    wire ready, ref_ready, valid, ref_valid, fail, ref_fail;
    wire [7:0] data_out, ref_out;
    reg [31:0] rng = 32'h18a726bd;
    integer epoch, cycle, accepted, emitted;
    rs204_188_compact dut(clk, resetn, in_valid, ready, in_byte, valid, data_out, fail);
    rs204_188_compact_reference ref_dut(clk, resetn, in_valid, ref_ready, in_byte, ref_valid, ref_out, ref_fail);
    always @(negedge clk) begin
        if (resetn) begin
            if ({ready, valid, fail} !== {ref_ready, ref_valid, ref_fail})
                $fatal(1, "control mismatch epoch=%0d cycle=%0d", epoch, cycle);
            if (valid && data_out !== ref_out)
                $fatal(1, "output mismatch epoch=%0d byte=%0d: %h != %h", epoch, emitted, data_out, ref_out);
        end
    end
    initial begin
        // Zero, eight-root, noisy, and stalled blocks; some run consecutively
        // without resetting the decoder so block reset/prefetch are exercised.
        // The added blocks vary 1..8 injected symbols with three byte values.
        for (epoch = 0; epoch < 48; epoch = epoch + 1) begin
            if ((epoch % 3) == 0) begin
                @(negedge clk); resetn = 0; in_valid = 0;
                repeat (3) @(negedge clk);
                resetn = 1;
            end
            accepted = 0; emitted = 0;
            for (cycle = 0; cycle < 9000 && emitted < 188; cycle = cycle + 1) begin
                @(negedge clk);
                rng = {rng[30:0], rng[31] ^ rng[21] ^ rng[1] ^ rng[0]};
                in_valid = (accepted < 204) && ((rng & 7) != 0);
                if (epoch >= 24)
                    in_byte = (accepted < (1 + epoch % 8)) ?
                              ((epoch < 32) ? 8'h01 : (epoch < 40) ? 8'h53 : 8'ha7) : 0;
                else if ((epoch % 6) == 0) in_byte = 0;
                else if ((epoch % 6) == 1) in_byte = (accepted < 8) ? 1 : 0;
                else in_byte = rng[15:8];
                @(posedge clk);
                if (in_valid && ready) accepted = accepted + 1;
                #1;
                if (valid) emitted = emitted + 1;
            end
            if (emitted != 188 || accepted != 204)
                $fatal(1, "incomplete block epoch=%0d", epoch);
            @(negedge clk); in_valid = 0;
            repeat (3) @(posedge clk);
        end
        // Abort processing in multiple phases and restart with a clean block.
        for (epoch = 0; epoch < 12; epoch = epoch + 1) begin
            @(negedge clk); resetn = 0; in_valid = 0;
            repeat (2) @(negedge clk);
            resetn = 1;
            for (cycle = 0; cycle < 400 + epoch * 490; cycle = cycle + 1) begin
                @(negedge clk);
                rng = {rng[30:0], rng[31] ^ rng[21] ^ rng[1] ^ rng[0]};
                in_valid = ready; in_byte = rng[15:8];
            end
            @(negedge clk); resetn = 0; in_valid = 0;
            repeat (2) @(negedge clk);
            resetn = 1;
            repeat (4) @(posedge clk);
        end
        $display("PASS: RS cycle-exact equivalence, 48 blocks (including 1..8 injected symbols) and 12 reset interruptions");
        $finish;
    end
endmodule
