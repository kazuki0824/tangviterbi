module viterbi_k7_16acs #(
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

    localparam integer STATES = 64;
    localparam [METRIC_W-1:0] INF = {METRIC_W{1'b1}};

    reg [METRIC_W-1:0] metric_a [0:STATES-1];
    reg [METRIC_W-1:0] metric_b [0:STATES-1];
    reg                  bank;
    reg [1:0]            group;
    reg [7:0]            soft0_q, soft1_q;
    reg [5:0]            wr_ptr;
    reg [5:0]            tb_ptr;
    reg [5:0]            tb_state;
    reg [7:0]            step_count;

    // Four narrow banks make the 64 survivor decisions per trellis step.
    // This maps much more naturally to embedded RAM than a 64x64 FF matrix.
    reg [15:0] survivor0 [0:TRACEBACK-1];
    reg [15:0] survivor1 [0:TRACEBACK-1];
    reg [15:0] survivor2 [0:TRACEBACK-1];
    reg [15:0] survivor3 [0:TRACEBACK-1];

    reg [METRIC_W-1:0] lane_metric [0:15];
    reg [15:0] lane_decision;

    integer i;
    integer s;
    integer p0;
    integer p1;
    reg [1:0] c0;
    reg [1:0] c1;
    reg [8:0] bm0;
    reg [8:0] bm1;
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

    // ISDB-T mother convolutional code: K=7, generators 171(oct) and 133(oct).
    function automatic [1:0] encode_pair;
        input [5:0] prev_state;
        input       input_bit;
        reg [6:0] shift;
        begin
            shift = {prev_state, input_bit};
            encode_pair[1] = parity7(shift & 7'h79); // 171 octal
            encode_pair[0] = parity7(shift & 7'h5b); // 133 octal
        end
    endfunction

    function automatic [8:0] soft_cost;
        input expected;
        input [7:0] sample;
        begin
            // Unsigned soft convention: 0 = strong zero, 255 = strong one.
            soft_cost = expected ? (9'd255 - {1'b0, sample})
                                 : {1'b0, sample};
        end
    endfunction

    assign in_ready = (group == 2'd0);

    always @* begin
        active_soft0 = (group == 2'd0) ? soft0 : soft0_q;
        active_soft1 = (group == 2'd0) ? soft1 : soft1_q;
        lane_decision = 16'b0;

        for (i = 0; i < 16; i = i + 1) begin
            s = ({30'd0, group} << 4) + i;
            // State convention: next = {prev[4:0], input_bit}.
            p0 = (s >> 1);
            p1 = (s >> 1) | 32;

            c0 = encode_pair(p0[5:0], s[0]);
            c1 = encode_pair(p1[5:0], s[0]);

            bm0 = soft_cost(c0[1], active_soft0) + soft_cost(c0[0], active_soft1);
            bm1 = soft_cost(c1[1], active_soft0) + soft_cost(c1[0], active_soft1);

            if (!bank) begin
                cand0 = {1'b0, metric_a[p0]} + bm0;
                cand1 = {1'b0, metric_a[p1]} + bm1;
            end else begin
                cand0 = {1'b0, metric_b[p0]} + bm0;
                cand1 = {1'b0, metric_b[p1]} + bm1;
            end

            if (cand1 < cand0) begin
                lane_metric[i] = cand1[METRIC_W-1:0];
                lane_decision[i] = 1'b1;
            end else begin
                lane_metric[i] = cand0[METRIC_W-1:0];
                lane_decision[i] = 1'b0;
            end
        end
    end

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            bank       <= 1'b0;
            group      <= 2'd0;
            soft0_q    <= 8'd0;
            soft1_q    <= 8'd0;
            wr_ptr     <= 6'd0;
            tb_ptr     <= 6'd0;
            tb_state   <= 6'd0;
            step_count <= 8'd0;
            out_valid  <= 1'b0;
            out_bit    <= 1'b0;

            for (i = 0; i < STATES; i = i + 1) begin
                metric_a[i] <= (i == 0) ? {METRIC_W{1'b0}} : INF;
                metric_b[i] <= INF;
            end
        end else begin
            out_valid <= 1'b0;

            // group 0 consumes a new soft pair. Groups 1..3 finish the same
            // trellis step, yielding exactly 4 cycles/step for 16 ACS lanes.
            if ((group != 2'd0) || in_valid) begin
                if (group == 2'd0) begin
                    soft0_q <= soft0;
                    soft1_q <= soft1;
                end

                for (i = 0; i < 16; i = i + 1) begin
                    s = ({30'd0, group} << 4) + i;
                    if (!bank)
                        metric_b[s] <= lane_metric[i];
                    else
                        metric_a[s] <= lane_metric[i];
                end

                case (group)
                    2'd0: survivor0[wr_ptr] <= lane_decision;
                    2'd1: survivor1[wr_ptr] <= lane_decision;
                    2'd2: survivor2[wr_ptr] <= lane_decision;
                    2'd3: survivor3[wr_ptr] <= lane_decision;
                endcase

                if (group == 2'd3) begin
                    group      <= 2'd0;
                    bank       <= ~bank;
                    wr_ptr     <= wr_ptr + 6'd1;
                    step_count <= step_count + 8'd1;

                    // Lightweight continuous traceback path. It deliberately
                    // reads the survivor RAM so synthesis accounts for the
                    // storage/read datapath needed by a decoder.
                    if (step_count >= TRACEBACK) begin
                        tb_ptr <= wr_ptr - TRACEBACK + 1;
                        case (tb_state[5:4])
                            2'd0: out_bit <= survivor0[tb_ptr][tb_state[3:0]];
                            2'd1: out_bit <= survivor1[tb_ptr][tb_state[3:0]];
                            2'd2: out_bit <= survivor2[tb_ptr][tb_state[3:0]];
                            default: out_bit <= survivor3[tb_ptr][tb_state[3:0]];
                        endcase
                        tb_state <= {out_bit, tb_state[5:1]};
                        out_valid <= 1'b1;
                    end
                end else begin
                    group <= group + 2'd1;
                end
            end
        end
    end
endmodule
