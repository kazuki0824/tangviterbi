module viterbi_k7_32acs #(
    parameter integer METRIC_W = 16,
    parameter integer TRACEBACK = 64
) (
    input  wire        clk,
    input  wire        resetn,
    input  wire        in_valid,
    output wire        in_ready,
    input  wire [7:0]  soft0,
    input  wire [7:0]  soft1,
    output reg         out_valid,
    output reg         out_bit
);
    localparam [METRIC_W-1:0] INF = {METRIC_W{1'b1}};

    // 32 ACS lanes consume one trellis step in two clocks.  Unlike the 16-ACS
    // baseline, the metric store deliberately spends 20K FF/LUT headroom on
    // two complete ping-pong generations.  This avoids a multi-write-port
    // BSRAM construction and makes the two-cycle dependency explicit.
    reg phase;
    reg bank;
    reg initialized;
    reg init_phase;
    reg [METRIC_W-1:0] metrics_a [0:63];
    reg [METRIC_W-1:0] metrics_b [0:63];
    reg [METRIC_W-1:0] lane_metric [0:31];
    reg [31:0] lane_decision;
    wire step_enable = initialized && (phase || in_valid);

    reg [7:0] soft0_q, soft1_q;
    reg [5:0] wr_ptr;
    reg [5:0] tb_ptr;
    reg [5:0] tb_state;
    reg [7:0] step_count;
    reg [31:0] decision_partial;

    (* ram_style = "block" *) reg [31:0] survivor_lo [0:TRACEBACK-1];
    (* ram_style = "block" *) reg [31:0] survivor_hi [0:TRACEBACK-1];
    reg [31:0] survivor_lo_q, survivor_hi_q;
    wire tb_selected = tb_state[5] ? survivor_hi_q[tb_state[4:0]]
                                   : survivor_lo_q[tb_state[4:0]];

    integer i;
    integer p0_state;
    integer p1_state;
    reg [METRIC_W-1:0] src0;
    reg [METRIC_W-1:0] src1;
    reg [1:0] coded0;
    reg [8:0] branch0;
    reg [8:0] branch1;
    reg [8:0] bm00;
    reg [8:0] bm01;
    reg [8:0] bm10;
    reg [8:0] bm11;
    reg [METRIC_W:0] cand0;
    reg [METRIC_W:0] cand1;
    reg [7:0] active_soft0;
    reg [7:0] active_soft1;

    function automatic parity7;
        input [6:0] x;
        begin
            parity7 = ^x;
        end
    endfunction

    function automatic [1:0] encode_pair;
        input [5:0] prev_state;
        input       input_bit;
        reg [6:0] shift;
        begin
            shift = {prev_state, input_bit};
            encode_pair[1] = parity7(shift & 7'h79);
            encode_pair[0] = parity7(shift & 7'h5b);
        end
    endfunction

    assign in_ready = initialized && !phase;

    always @* begin
        active_soft0 = !phase ? soft0 : soft0_q;
        active_soft1 = !phase ? soft1 : soft1_q;
        lane_decision = 32'b0;

        bm00 = {1'b0, active_soft0} + {1'b0, active_soft1};
        bm01 = {1'b0, active_soft0} + {1'b0, ~active_soft1};
        bm10 = {1'b0, ~active_soft0} + {1'b0, active_soft1};
        bm11 = {1'b0, ~active_soft0} + {1'b0, ~active_soft1};

        for (i = 0; i < 32; i = i + 1) begin
            // phase 0 produces states 0..31 and phase 1 states 32..63.
            // Each destination state has predecessors state>>1 and +32.
            p0_state = (phase ? 16 : 0) + (i >> 1);
            p1_state = p0_state + 32;
            if (bank) begin
                src0 = metrics_b[p0_state];
                src1 = metrics_b[p1_state];
            end else begin
                src0 = metrics_a[p0_state];
                src1 = metrics_a[p1_state];
            end

            coded0 = encode_pair(p0_state[5:0], i[0]);
            case (coded0)
                2'b00: begin branch0 = bm00; branch1 = bm11; end
                2'b01: begin branch0 = bm01; branch1 = bm10; end
                2'b10: begin branch0 = bm10; branch1 = bm01; end
                default: begin branch0 = bm11; branch1 = bm00; end
            endcase

            cand0 = {1'b0, src0} + branch0;
            cand1 = {1'b0, src1} + branch1;
            if (cand1 < cand0) begin
                lane_metric[i] = cand1[METRIC_W-1:0];
                lane_decision[i] = 1'b1;
            end else begin
                lane_metric[i] = cand0[METRIC_W-1:0];
                lane_decision[i] = 1'b0;
            end
        end
    end

    integer j;
    always @(posedge clk) begin
        if (resetn) begin
            if (!initialized) begin
                // Initialize only the first source generation.  The other
                // generation is completely overwritten before it is read.
                for (j = 0; j < 32; j = j + 1)
                    metrics_a[(init_phase ? 32 : 0) + j] <=
                        (!init_phase && (j == 0)) ? {METRIC_W{1'b0}} : INF;
            end else if (step_enable) begin
                if (!bank) begin
                    for (j = 0; j < 32; j = j + 1)
                        metrics_b[(phase ? 32 : 0) + j] <= lane_metric[j];
                end else begin
                    for (j = 0; j < 32; j = j + 1)
                        metrics_a[(phase ? 32 : 0) + j] <= lane_metric[j];
                end
            end
        end
    end

    always @(posedge clk) begin
        survivor_lo_q <= survivor_lo[tb_ptr];
        survivor_hi_q <= survivor_hi[tb_ptr];
    end

    always @(posedge clk) begin
        if (resetn && initialized && step_enable && phase) begin
            survivor_lo[wr_ptr] <= decision_partial;
            survivor_hi[wr_ptr] <= lane_decision;
        end
    end

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            phase <= 1'b0;
            bank <= 1'b0;
            initialized <= 1'b0;
            init_phase <= 1'b0;
            soft0_q <= 8'd0;
            soft1_q <= 8'd0;
            wr_ptr <= 6'd0;
            tb_ptr <= 6'd0;
            tb_state <= 6'd0;
            step_count <= 8'd0;
            decision_partial <= 32'd0;
            out_valid <= 1'b0;
            out_bit <= 1'b0;
        end else begin
            out_valid <= 1'b0;

            if (!initialized) begin
                init_phase <= ~init_phase;
                if (init_phase)
                    initialized <= 1'b1;
            end else if (step_enable) begin
                if (!phase) begin
                    soft0_q <= soft0;
                    soft1_q <= soft1;
                    decision_partial <= lane_decision;
                    phase <= 1'b1;
                end else begin
                    phase <= 1'b0;
                    bank <= ~bank;
                    wr_ptr <= wr_ptr + 6'd1;
                    step_count <= step_count + 8'd1;

                    if (step_count >= TRACEBACK) begin
                        tb_ptr <= tb_ptr + 6'd1;
                        out_bit <= tb_selected;
                        tb_state <= {tb_selected, tb_state[5:1]};
                        out_valid <= 1'b1;
                    end
                end
            end
        end
    end
endmodule
