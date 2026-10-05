`timescale 1ns/1ps
module rs_equivalence_tb;
    reg clk = 0;
    always #5 clk = ~clk;
    reg resetn = 0;
    reg in_valid = 0, ref_in_valid = 0;
    reg [7:0] in_byte = 0, ref_in_byte = 0;
    wire ready, ref_ready, valid, ref_valid, fail, ref_fail;
    wire [7:0] data_out, ref_out;
    reg [31:0] rng = 32'h18a726bd;
    reg [7:0] packet [0:203];
    reg [7:0] actual [0:187], expected [0:187];
    integer epoch, cycle, accepted, ref_accepted, emitted, ref_emitted, symbol, interruption;
    rs204_188_compact dut(clk, resetn, in_valid, ready, in_byte, valid, data_out, fail);
    rs204_188_compact_reference ref_dut(clk, resetn, ref_in_valid, ref_ready, ref_in_byte, ref_valid, ref_out, ref_fail);

    integer output_entries = 0;
    integer correction_reads = 0;
    reg [5:0] previous_state;
    always @(posedge clk) begin
        previous_state = dut.state;
        if (resetn && (previous_state == dut.ST_FORNEY_READ))
            correction_reads = correction_reads + 1;
        #1;
        if (resetn && (dut.state == dut.ST_OUTPUT) && (previous_state != dut.ST_OUTPUT)) begin
            case (previous_state)
                // Serialized RS uses state 1 for the final syndrome step;
                // constant-RS omits that state and enters directly from INPUT.
                dut.ST_INPUT, 6'd1: output_entries = output_entries | 1;
                dut.ST_FORNEY_INIT: output_entries = output_entries | 2;
                dut.ST_FORNEY_WRITE: output_entries = output_entries | 4;
                default: $fatal(1, "unexpected transition into output");
            endcase
        end
    end

    initial begin
        // Independent handshakes feed the same codeword to both decoders.
        // Different latency is permitted; byte count, byte order and fail are not.
        for (epoch = 0; epoch < 48; epoch = epoch + 1) begin
            if ((epoch % 4) == 0) begin
                @(negedge clk); resetn = 0; in_valid = 0; ref_in_valid = 0;
                repeat (3) @(negedge clk);
                resetn = 1;
                interruption = epoch / 4;
                // Abort different processing phases, then decode a clean block.
                for (cycle = 0; cycle < 400 + interruption * 490; cycle = cycle + 1) begin
                    @(negedge clk);
                    rng = {rng[30:0], rng[31] ^ rng[21] ^ rng[1] ^ rng[0]};
                    in_valid = ready; ref_in_valid = ref_ready;
                    in_byte = rng[15:8]; ref_in_byte = rng[15:8];
                end
                @(negedge clk); resetn = 0; in_valid = 0; ref_in_valid = 0;
                repeat (3) @(negedge clk);
                resetn = 1;
            end
            for (symbol = 0; symbol < 204; symbol = symbol + 1) begin
                rng = {rng[30:0], rng[31] ^ rng[21] ^ rng[1] ^ rng[0]};
                if (epoch >= 24)
                    packet[symbol] = (symbol < (1 + epoch % 8)) ?
                                     ((epoch < 32) ? 8'h01 : (epoch < 40) ? 8'h53 : 8'ha7) : 0;
                else if ((epoch % 6) == 0) packet[symbol] = 0;
                else if ((epoch % 6) == 1) packet[symbol] = (symbol < 8) ? 1 : 0;
                else packet[symbol] = rng[15:8];
            end
            accepted = 0; ref_accepted = 0; emitted = 0; ref_emitted = 0;
            for (cycle = 0; cycle < 10000 && (emitted < 188 || ref_emitted < 188); cycle = cycle + 1) begin
                @(negedge clk);
                rng = {rng[30:0], rng[31] ^ rng[21] ^ rng[1] ^ rng[0]};
                in_valid = (accepted < 204) && ((rng & 7) != 0);
                ref_in_valid = (ref_accepted < 204) && (((rng >> 3) & 7) != 0);
                in_byte = (accepted < 204) ? packet[accepted] : 0;
                ref_in_byte = (ref_accepted < 204) ? packet[ref_accepted] : 0;
                @(posedge clk);
                if (in_valid && ready) accepted = accepted + 1;
                if (ref_in_valid && ref_ready) ref_accepted = ref_accepted + 1;
                #1;
                if (valid) begin
                    if (emitted >= 188) $fatal(1, "extra DUT output epoch=%0d", epoch);
                    actual[emitted] = data_out; emitted = emitted + 1;
                end
                if (ref_valid) begin
                    if (ref_emitted >= 188) $fatal(1, "extra reference output epoch=%0d", epoch);
                    expected[ref_emitted] = ref_out; ref_emitted = ref_emitted + 1;
                end
            end
            if (emitted != 188 || ref_emitted != 188 || accepted != 204 || ref_accepted != 204)
                $fatal(1, "incomplete block epoch=%0d", epoch);
            if (fail !== ref_fail) $fatal(1, "fail mismatch epoch=%0d", epoch);
            for (symbol = 0; symbol < 188; symbol = symbol + 1)
                if (actual[symbol] !== expected[symbol])
                    $fatal(1, "output mismatch epoch=%0d byte=%0d: %h != %h", epoch, symbol, actual[symbol], expected[symbol]);
            @(negedge clk); in_valid = 0; ref_in_valid = 0;
            repeat (3) @(posedge clk);
        end
        if (output_entries != 7 || correction_reads == 0)
            $fatal(1, "RAM schedule coverage incomplete: entries=%0d reads=%0d", output_entries, correction_reads);
        $display("RAM schedule coverage: all three output entry paths, %0d correction reads", correction_reads);
        $display("PASS: RS latency-independent equivalence, 48 blocks and 12 reset interruptions followed by clean blocks");
        $finish;
    end
endmodule
