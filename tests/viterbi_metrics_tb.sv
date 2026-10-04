`timescale 1ns/1ps
module viterbi_metrics_tb;
    parameter integer METRIC_W = 16;
    localparam integer MASK = (1 << METRIC_W) - 1;
    reg clk = 0;
    always #5 clk = ~clk;
    reg resetn = 0, in_valid = 0;
    reg [7:0] soft0 = 0, soft1 = 0;
    wire in_ready, out_valid, out_bit;
    viterbi_k7_16acs #(.METRIC_W(METRIC_W)) dut (
        .clk(clk), .resetn(resetn), .in_valid(in_valid), .in_ready(in_ready),
        .soft0(soft0), .soft1(soft1), .out_valid(out_valid), .out_bit(out_bit)
    );
    integer metrics [0:63];
    integer next_metrics [0:63];
    reg [63:0] decisions;
    reg [31:0] rng = 32'h4567abcd;
    integer epoch, step, phase, state, pred, c0, c1, i, ptr;
    reg [6:0] shift;
    reg [1:0] code;
    reg expected_out_bit, expected_out_valid;

    task random_inputs;
        begin
            rng = {rng[30:0], rng[31] ^ rng[21] ^ rng[1] ^ rng[0]};
            soft0 = rng[7:0];
            soft1 = rng[15:8];
        end
    endtask

    initial begin
        // Two epochs verify reset after populated RAM. 16-bit metrics also
        // cross the existing truncation boundary; a second run uses 10 bits.
        for (epoch = 0; epoch < 2; epoch = epoch + 1) begin
            @(negedge clk);
            resetn = 0;
            in_valid = 0;
            #1;
            for (i = 0; i < 64; i = i + 1)
                metrics[i] = (i == 0) ? 0 : MASK;
            @(negedge clk);
            resetn = 1;
            for (i = 0; i < 4; i = i + 1) begin
                #1;
                if (in_ready) $fatal(1, "ready before metric initialization");
                @(negedge clk);
            end
            #1;
            if (!in_ready) $fatal(1, "initialization did not finish in four clocks");
            for (step = 0; step < 1000; step = step + 1) begin
                // Exercise idle gaps and changing external inputs while an
                // accepted pair is held for the remaining three ACS groups.
                repeat (rng[17:16]) begin
                    in_valid = 0;
                    random_inputs();
                    @(negedge clk);
                    #1;
                    if (!in_ready || dut.group != 0)
                        $fatal(1, "idle advanced the trellis");
                end
                random_inputs();
                if (step % 7 == 0) begin soft0 = 127; soft1 = 128; end
                in_valid = 1;
                for (state = 0; state < 64; state = state + 1) begin
                    pred = state >> 1;
                    shift = {pred[5:0], state[0]};
                    code = {^(shift & 7'h79), ^(shift & 7'h5b)};
                    c0 = metrics[pred] + (code[1] ? 255-soft0 : soft0)
                                              + (code[0] ? 255-soft1 : soft1);
                    // Independently encode the other predecessor.
                    shift = {(pred[5:0] | 6'd32), state[0]};
                    code = {^(shift & 7'h79), ^(shift & 7'h5b)};
                    c1 = metrics[pred+32] + (code[1] ? 255-soft0 : soft0)
                                                 + (code[0] ? 255-soft1 : soft1);
                    decisions[state] = c1 < c0;
                    next_metrics[state] = ((c1 < c0) ? c1 : c0) & MASK;
                end
                ptr = dut.wr_ptr;
                for (phase = 0; phase < 4; phase = phase + 1) begin
                    #1;
                    if (dut.group != phase || in_ready != (phase == 0))
                        $fatal(1, "four-cycle scheduling changed");
                    expected_out_valid = (phase == 3) && (step % 256 >= 64);
                    expected_out_bit = dut.tb_state[5] ? dut.survivor_hi_q[dut.tb_state[4:0]]
                                                      : dut.survivor_lo_q[dut.tb_state[4:0]];
                    for (i = 0; i < 16; i = i + 1) begin
                        if (dut.lane_metric[i] !== next_metrics[16*phase+i][METRIC_W-1:0])
                            $fatal(1, "metric mismatch epoch=%0d step=%0d state=%0d", epoch, step, 16*phase+i);
                        if (dut.lane_decision[i] !== decisions[16*phase+i])
                            $fatal(1, "decision mismatch");
                    end
                    @(negedge clk);
                    #1;
                    if (out_valid !== expected_out_valid ||
                        (expected_out_valid && out_bit !== expected_out_bit))
                        $fatal(1, "traceback output/timing differs from original row selection");
                    in_valid = 0;
                    random_inputs();
                end
                #1;
                if ({dut.survivor_hi[ptr], dut.survivor_lo[ptr]} !== decisions)
                    $fatal(1, "survivor write mismatch");
                for (i = 0; i < 64; i = i + 1) metrics[i] = next_metrics[i];
            end
        end
        $display("PASS: metric recurrence, decisions, survivor writes, traceback selection, stalls/reset, four-cycle throughput (W=%0d)", METRIC_W);
        $finish;
    end
endmodule
