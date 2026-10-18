module folded_t_viterbi #(
    parameter integer METRIC_W = 13,
    parameter integer TRACEBACK = 64
) (
    input  wire        clk,
    input  wire        resetn,
    input  wire        in_valid,
    output wire        in_ready,
    input  wire [7:0]  soft0,
    input  wire [7:0]  soft1,
    input wire [1:0] erasure,
    output reg         out_valid,
    output reg         out_bit
);
    localparam [METRIC_W-1:0] INF = {METRIC_W{1'b1}};

    // Preserve old low predecessors overwritten before their last use.
    // Fixed per-phase indices avoid a dynamic 64:1 metric read crossbar.
    reg [2:0] phase, init_phase;
reg [5:0] phase_hot;
    reg initialized;
    reg [METRIC_W-1:0] metrics [0:63];
    reg [METRIC_W-1:0] metric_shadow [8:31];
    reg [METRIC_W-1:0] lane_metric [0:15];
    reg [15:0] lane_decision;
    wire step_enable = initialized && ((phase != 0) || in_valid);
    always @(posedge clk) begin
        if (!resetn) phase_hot <= 1;
        else if (step_enable) phase_hot <= {phase_hot[4:0],phase_hot[5]};
    end
    wire commit_step = step_enable && (phase_hot[5]);
    reg [7:0] soft0_q, soft1_q;
    reg [1:0] erasure_q;
    wire [1:0] active_erasure=phase_hot[0] ? erasure : erasure_q;
    reg [7:0] wr_ptr;
    reg [7:0] accepted;
    reg norm_q;
    reg [63:0] decision_partial;
    wire normalize = phase ? norm_q : metrics[0][METRIC_W-1];
    (* ram_style = "block" *) reg [15:0] survivor [0:1023];
    reg [15:0] survivor_q;
    reg [7:0] read_ptr;
    reg [6:0] walk;
    reg [5:0] state;
    reg tracing, priming;
    reg [63:0] decoded [0:1];
    reg decoded_write, decoded_read;
    reg [1:0] decoded_ready;
    reg output_tick;
    reg [5:0] output_pos;
    wire start_trace = commit_step && (accepted >= 127) &&
                      (wr_ptr[5:0] == 63);
    wire decision = survivor_q[state[3:0]];

    initial begin
        if (METRIC_W != 13 || TRACEBACK != 64)
            $fatal(1, "unsupported traceback/metric parameter override");
    end
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
    reg signed [METRIC_W-1:0] metric_difference;
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

    assign in_ready = initialized && (phase_hot[0]);

    always @(posedge clk) if (resetn && in_valid && in_ready) begin
        bm00 <= (erasure[1] ? 9'd0 : {1'b0, soft0}) + (erasure[0] ? 9'd0 : {1'b0, soft1});
        bm01 <= (erasure[1] ? 9'd0 : {1'b0, soft0}) + (erasure[0] ? 9'd0 : {1'b0, ~soft1});
        bm10 <= (erasure[1] ? 9'd0 : {1'b0, ~soft0}) + (erasure[0] ? 9'd0 : {1'b0, soft1});
        bm11 <= (erasure[1] ? 9'd0 : {1'b0, ~soft0}) + (erasure[0] ? 9'd0 : {1'b0, ~soft1});
    end
    wire [METRIC_W-1:0] result_0;
    reg [METRIC_W-1:0] a_0, b_0;
    reg [8:0] c_0, d_0;
    wire [METRIC_W-1:0] x_0 = a_0 + c_0;
    wire [METRIC_W-1:0] y_0 = b_0 + d_0;
    reg [METRIC_W-1:0] xq_0, yq_0;
    always @(posedge clk) begin xq_0 <= x_0; yq_0 <= y_0; end
    wire signed [METRIC_W-1:0] diff_0 = yq_0 - xq_0;
    always @* begin
        a_0 = ({{METRIC_W{phase_hot[1]}}} & metrics[0]) | ({{METRIC_W{phase_hot[2]}}} & metric_shadow[8]) | ({{METRIC_W{phase_hot[3]}}} & metric_shadow[16]) | ({{METRIC_W{phase_hot[4]}}} & metric_shadow[24]);
        b_0 = ({{METRIC_W{phase_hot[1]}}} & metrics[32]) | ({{METRIC_W{phase_hot[2]}}} & metrics[40]) | ({{METRIC_W{phase_hot[3]}}} & metrics[48]) | ({{METRIC_W{phase_hot[4]}}} & metrics[56]);
        c_0 = ({{9{phase_hot[1]}}} & bm00) | ({{9{phase_hot[2]}}} & bm11) | ({{9{phase_hot[3]}}} & bm10) | ({{9{phase_hot[4]}}} & bm01);
        d_0 = ({{9{phase_hot[1]}}} & bm11) | ({{9{phase_hot[2]}}} & bm00) | ({{9{phase_hot[3]}}} & bm01) | ({{9{phase_hot[4]}}} & bm10);
        lane_metric[0] = (diff_0 < 0) ? yq_0 : xq_0;
        lane_decision[0] = (diff_0 < 0);
    end
    wire [METRIC_W-1:0] result_1;
    reg [METRIC_W-1:0] a_1, b_1;
    reg [8:0] c_1, d_1;
    wire [METRIC_W-1:0] x_1 = a_1 + c_1;
    wire [METRIC_W-1:0] y_1 = b_1 + d_1;
    reg [METRIC_W-1:0] xq_1, yq_1;
    always @(posedge clk) begin xq_1 <= x_1; yq_1 <= y_1; end
    wire signed [METRIC_W-1:0] diff_1 = yq_1 - xq_1;
    always @* begin
        a_1 = ({{METRIC_W{phase_hot[1]}}} & metrics[0]) | ({{METRIC_W{phase_hot[2]}}} & metric_shadow[8]) | ({{METRIC_W{phase_hot[3]}}} & metric_shadow[16]) | ({{METRIC_W{phase_hot[4]}}} & metric_shadow[24]);
        b_1 = ({{METRIC_W{phase_hot[1]}}} & metrics[32]) | ({{METRIC_W{phase_hot[2]}}} & metrics[40]) | ({{METRIC_W{phase_hot[3]}}} & metrics[48]) | ({{METRIC_W{phase_hot[4]}}} & metrics[56]);
        c_1 = ({{9{phase_hot[1]}}} & bm11) | ({{9{phase_hot[2]}}} & bm00) | ({{9{phase_hot[3]}}} & bm01) | ({{9{phase_hot[4]}}} & bm10);
        d_1 = ({{9{phase_hot[1]}}} & bm00) | ({{9{phase_hot[2]}}} & bm11) | ({{9{phase_hot[3]}}} & bm10) | ({{9{phase_hot[4]}}} & bm01);
        lane_metric[1] = (diff_1 < 0) ? yq_1 : xq_1;
        lane_decision[1] = (diff_1 < 0);
    end
    wire [METRIC_W-1:0] result_2;
    reg [METRIC_W-1:0] a_2, b_2;
    reg [8:0] c_2, d_2;
    wire [METRIC_W-1:0] x_2 = a_2 + c_2;
    wire [METRIC_W-1:0] y_2 = b_2 + d_2;
    reg [METRIC_W-1:0] xq_2, yq_2;
    always @(posedge clk) begin xq_2 <= x_2; yq_2 <= y_2; end
    wire signed [METRIC_W-1:0] diff_2 = yq_2 - xq_2;
    always @* begin
        a_2 = ({{METRIC_W{phase_hot[1]}}} & metrics[1]) | ({{METRIC_W{phase_hot[2]}}} & metric_shadow[9]) | ({{METRIC_W{phase_hot[3]}}} & metric_shadow[17]) | ({{METRIC_W{phase_hot[4]}}} & metric_shadow[25]);
        b_2 = ({{METRIC_W{phase_hot[1]}}} & metrics[33]) | ({{METRIC_W{phase_hot[2]}}} & metrics[41]) | ({{METRIC_W{phase_hot[3]}}} & metrics[49]) | ({{METRIC_W{phase_hot[4]}}} & metrics[57]);
        c_2 = ({{9{phase_hot[1]}}} & bm01) | ({{9{phase_hot[2]}}} & bm10) | ({{9{phase_hot[3]}}} & bm11) | ({{9{phase_hot[4]}}} & bm00);
        d_2 = ({{9{phase_hot[1]}}} & bm10) | ({{9{phase_hot[2]}}} & bm01) | ({{9{phase_hot[3]}}} & bm00) | ({{9{phase_hot[4]}}} & bm11);
        lane_metric[2] = (diff_2 < 0) ? yq_2 : xq_2;
        lane_decision[2] = (diff_2 < 0);
    end
    wire [METRIC_W-1:0] result_3;
    reg [METRIC_W-1:0] a_3, b_3;
    reg [8:0] c_3, d_3;
    wire [METRIC_W-1:0] x_3 = a_3 + c_3;
    wire [METRIC_W-1:0] y_3 = b_3 + d_3;
    reg [METRIC_W-1:0] xq_3, yq_3;
    always @(posedge clk) begin xq_3 <= x_3; yq_3 <= y_3; end
    wire signed [METRIC_W-1:0] diff_3 = yq_3 - xq_3;
    always @* begin
        a_3 = ({{METRIC_W{phase_hot[1]}}} & metrics[1]) | ({{METRIC_W{phase_hot[2]}}} & metric_shadow[9]) | ({{METRIC_W{phase_hot[3]}}} & metric_shadow[17]) | ({{METRIC_W{phase_hot[4]}}} & metric_shadow[25]);
        b_3 = ({{METRIC_W{phase_hot[1]}}} & metrics[33]) | ({{METRIC_W{phase_hot[2]}}} & metrics[41]) | ({{METRIC_W{phase_hot[3]}}} & metrics[49]) | ({{METRIC_W{phase_hot[4]}}} & metrics[57]);
        c_3 = ({{9{phase_hot[1]}}} & bm10) | ({{9{phase_hot[2]}}} & bm01) | ({{9{phase_hot[3]}}} & bm00) | ({{9{phase_hot[4]}}} & bm11);
        d_3 = ({{9{phase_hot[1]}}} & bm01) | ({{9{phase_hot[2]}}} & bm10) | ({{9{phase_hot[3]}}} & bm11) | ({{9{phase_hot[4]}}} & bm00);
        lane_metric[3] = (diff_3 < 0) ? yq_3 : xq_3;
        lane_decision[3] = (diff_3 < 0);
    end
    wire [METRIC_W-1:0] result_4;
    reg [METRIC_W-1:0] a_4, b_4;
    reg [8:0] c_4, d_4;
    wire [METRIC_W-1:0] x_4 = a_4 + c_4;
    wire [METRIC_W-1:0] y_4 = b_4 + d_4;
    reg [METRIC_W-1:0] xq_4, yq_4;
    always @(posedge clk) begin xq_4 <= x_4; yq_4 <= y_4; end
    wire signed [METRIC_W-1:0] diff_4 = yq_4 - xq_4;
    always @* begin
        a_4 = ({{METRIC_W{phase_hot[1]}}} & metrics[2]) | ({{METRIC_W{phase_hot[2]}}} & metric_shadow[10]) | ({{METRIC_W{phase_hot[3]}}} & metric_shadow[18]) | ({{METRIC_W{phase_hot[4]}}} & metric_shadow[26]);
        b_4 = ({{METRIC_W{phase_hot[1]}}} & metrics[34]) | ({{METRIC_W{phase_hot[2]}}} & metrics[42]) | ({{METRIC_W{phase_hot[3]}}} & metrics[50]) | ({{METRIC_W{phase_hot[4]}}} & metrics[58]);
        c_4 = ({{9{phase_hot[1]}}} & bm00) | ({{9{phase_hot[2]}}} & bm11) | ({{9{phase_hot[3]}}} & bm10) | ({{9{phase_hot[4]}}} & bm01);
        d_4 = ({{9{phase_hot[1]}}} & bm11) | ({{9{phase_hot[2]}}} & bm00) | ({{9{phase_hot[3]}}} & bm01) | ({{9{phase_hot[4]}}} & bm10);
        lane_metric[4] = (diff_4 < 0) ? yq_4 : xq_4;
        lane_decision[4] = (diff_4 < 0);
    end
    wire [METRIC_W-1:0] result_5;
    reg [METRIC_W-1:0] a_5, b_5;
    reg [8:0] c_5, d_5;
    wire [METRIC_W-1:0] x_5 = a_5 + c_5;
    wire [METRIC_W-1:0] y_5 = b_5 + d_5;
    reg [METRIC_W-1:0] xq_5, yq_5;
    always @(posedge clk) begin xq_5 <= x_5; yq_5 <= y_5; end
    wire signed [METRIC_W-1:0] diff_5 = yq_5 - xq_5;
    always @* begin
        a_5 = ({{METRIC_W{phase_hot[1]}}} & metrics[2]) | ({{METRIC_W{phase_hot[2]}}} & metric_shadow[10]) | ({{METRIC_W{phase_hot[3]}}} & metric_shadow[18]) | ({{METRIC_W{phase_hot[4]}}} & metric_shadow[26]);
        b_5 = ({{METRIC_W{phase_hot[1]}}} & metrics[34]) | ({{METRIC_W{phase_hot[2]}}} & metrics[42]) | ({{METRIC_W{phase_hot[3]}}} & metrics[50]) | ({{METRIC_W{phase_hot[4]}}} & metrics[58]);
        c_5 = ({{9{phase_hot[1]}}} & bm11) | ({{9{phase_hot[2]}}} & bm00) | ({{9{phase_hot[3]}}} & bm01) | ({{9{phase_hot[4]}}} & bm10);
        d_5 = ({{9{phase_hot[1]}}} & bm00) | ({{9{phase_hot[2]}}} & bm11) | ({{9{phase_hot[3]}}} & bm10) | ({{9{phase_hot[4]}}} & bm01);
        lane_metric[5] = (diff_5 < 0) ? yq_5 : xq_5;
        lane_decision[5] = (diff_5 < 0);
    end
    wire [METRIC_W-1:0] result_6;
    reg [METRIC_W-1:0] a_6, b_6;
    reg [8:0] c_6, d_6;
    wire [METRIC_W-1:0] x_6 = a_6 + c_6;
    wire [METRIC_W-1:0] y_6 = b_6 + d_6;
    reg [METRIC_W-1:0] xq_6, yq_6;
    always @(posedge clk) begin xq_6 <= x_6; yq_6 <= y_6; end
    wire signed [METRIC_W-1:0] diff_6 = yq_6 - xq_6;
    always @* begin
        a_6 = ({{METRIC_W{phase_hot[1]}}} & metrics[3]) | ({{METRIC_W{phase_hot[2]}}} & metric_shadow[11]) | ({{METRIC_W{phase_hot[3]}}} & metric_shadow[19]) | ({{METRIC_W{phase_hot[4]}}} & metric_shadow[27]);
        b_6 = ({{METRIC_W{phase_hot[1]}}} & metrics[35]) | ({{METRIC_W{phase_hot[2]}}} & metrics[43]) | ({{METRIC_W{phase_hot[3]}}} & metrics[51]) | ({{METRIC_W{phase_hot[4]}}} & metrics[59]);
        c_6 = ({{9{phase_hot[1]}}} & bm01) | ({{9{phase_hot[2]}}} & bm10) | ({{9{phase_hot[3]}}} & bm11) | ({{9{phase_hot[4]}}} & bm00);
        d_6 = ({{9{phase_hot[1]}}} & bm10) | ({{9{phase_hot[2]}}} & bm01) | ({{9{phase_hot[3]}}} & bm00) | ({{9{phase_hot[4]}}} & bm11);
        lane_metric[6] = (diff_6 < 0) ? yq_6 : xq_6;
        lane_decision[6] = (diff_6 < 0);
    end
    wire [METRIC_W-1:0] result_7;
    reg [METRIC_W-1:0] a_7, b_7;
    reg [8:0] c_7, d_7;
    wire [METRIC_W-1:0] x_7 = a_7 + c_7;
    wire [METRIC_W-1:0] y_7 = b_7 + d_7;
    reg [METRIC_W-1:0] xq_7, yq_7;
    always @(posedge clk) begin xq_7 <= x_7; yq_7 <= y_7; end
    wire signed [METRIC_W-1:0] diff_7 = yq_7 - xq_7;
    always @* begin
        a_7 = ({{METRIC_W{phase_hot[1]}}} & metrics[3]) | ({{METRIC_W{phase_hot[2]}}} & metric_shadow[11]) | ({{METRIC_W{phase_hot[3]}}} & metric_shadow[19]) | ({{METRIC_W{phase_hot[4]}}} & metric_shadow[27]);
        b_7 = ({{METRIC_W{phase_hot[1]}}} & metrics[35]) | ({{METRIC_W{phase_hot[2]}}} & metrics[43]) | ({{METRIC_W{phase_hot[3]}}} & metrics[51]) | ({{METRIC_W{phase_hot[4]}}} & metrics[59]);
        c_7 = ({{9{phase_hot[1]}}} & bm10) | ({{9{phase_hot[2]}}} & bm01) | ({{9{phase_hot[3]}}} & bm00) | ({{9{phase_hot[4]}}} & bm11);
        d_7 = ({{9{phase_hot[1]}}} & bm01) | ({{9{phase_hot[2]}}} & bm10) | ({{9{phase_hot[3]}}} & bm11) | ({{9{phase_hot[4]}}} & bm00);
        lane_metric[7] = (diff_7 < 0) ? yq_7 : xq_7;
        lane_decision[7] = (diff_7 < 0);
    end
    wire [METRIC_W-1:0] result_8;
    reg [METRIC_W-1:0] a_8, b_8;
    reg [8:0] c_8, d_8;
    wire [METRIC_W-1:0] x_8 = a_8 + c_8;
    wire [METRIC_W-1:0] y_8 = b_8 + d_8;
    reg [METRIC_W-1:0] xq_8, yq_8;
    always @(posedge clk) begin xq_8 <= x_8; yq_8 <= y_8; end
    wire signed [METRIC_W-1:0] diff_8 = yq_8 - xq_8;
    always @* begin
        a_8 = ({{METRIC_W{phase_hot[1]}}} & metrics[4]) | ({{METRIC_W{phase_hot[2]}}} & metric_shadow[12]) | ({{METRIC_W{phase_hot[3]}}} & metric_shadow[20]) | ({{METRIC_W{phase_hot[4]}}} & metric_shadow[28]);
        b_8 = ({{METRIC_W{phase_hot[1]}}} & metrics[36]) | ({{METRIC_W{phase_hot[2]}}} & metrics[44]) | ({{METRIC_W{phase_hot[3]}}} & metrics[52]) | ({{METRIC_W{phase_hot[4]}}} & metrics[60]);
        c_8 = ({{9{phase_hot[1]}}} & bm11) | ({{9{phase_hot[2]}}} & bm00) | ({{9{phase_hot[3]}}} & bm01) | ({{9{phase_hot[4]}}} & bm10);
        d_8 = ({{9{phase_hot[1]}}} & bm00) | ({{9{phase_hot[2]}}} & bm11) | ({{9{phase_hot[3]}}} & bm10) | ({{9{phase_hot[4]}}} & bm01);
        lane_metric[8] = (diff_8 < 0) ? yq_8 : xq_8;
        lane_decision[8] = (diff_8 < 0);
    end
    wire [METRIC_W-1:0] result_9;
    reg [METRIC_W-1:0] a_9, b_9;
    reg [8:0] c_9, d_9;
    wire [METRIC_W-1:0] x_9 = a_9 + c_9;
    wire [METRIC_W-1:0] y_9 = b_9 + d_9;
    reg [METRIC_W-1:0] xq_9, yq_9;
    always @(posedge clk) begin xq_9 <= x_9; yq_9 <= y_9; end
    wire signed [METRIC_W-1:0] diff_9 = yq_9 - xq_9;
    always @* begin
        a_9 = ({{METRIC_W{phase_hot[1]}}} & metrics[4]) | ({{METRIC_W{phase_hot[2]}}} & metric_shadow[12]) | ({{METRIC_W{phase_hot[3]}}} & metric_shadow[20]) | ({{METRIC_W{phase_hot[4]}}} & metric_shadow[28]);
        b_9 = ({{METRIC_W{phase_hot[1]}}} & metrics[36]) | ({{METRIC_W{phase_hot[2]}}} & metrics[44]) | ({{METRIC_W{phase_hot[3]}}} & metrics[52]) | ({{METRIC_W{phase_hot[4]}}} & metrics[60]);
        c_9 = ({{9{phase_hot[1]}}} & bm00) | ({{9{phase_hot[2]}}} & bm11) | ({{9{phase_hot[3]}}} & bm10) | ({{9{phase_hot[4]}}} & bm01);
        d_9 = ({{9{phase_hot[1]}}} & bm11) | ({{9{phase_hot[2]}}} & bm00) | ({{9{phase_hot[3]}}} & bm01) | ({{9{phase_hot[4]}}} & bm10);
        lane_metric[9] = (diff_9 < 0) ? yq_9 : xq_9;
        lane_decision[9] = (diff_9 < 0);
    end
    wire [METRIC_W-1:0] result_10;
    reg [METRIC_W-1:0] a_10, b_10;
    reg [8:0] c_10, d_10;
    wire [METRIC_W-1:0] x_10 = a_10 + c_10;
    wire [METRIC_W-1:0] y_10 = b_10 + d_10;
    reg [METRIC_W-1:0] xq_10, yq_10;
    always @(posedge clk) begin xq_10 <= x_10; yq_10 <= y_10; end
    wire signed [METRIC_W-1:0] diff_10 = yq_10 - xq_10;
    always @* begin
        a_10 = ({{METRIC_W{phase_hot[1]}}} & metrics[5]) | ({{METRIC_W{phase_hot[2]}}} & metric_shadow[13]) | ({{METRIC_W{phase_hot[3]}}} & metric_shadow[21]) | ({{METRIC_W{phase_hot[4]}}} & metric_shadow[29]);
        b_10 = ({{METRIC_W{phase_hot[1]}}} & metrics[37]) | ({{METRIC_W{phase_hot[2]}}} & metrics[45]) | ({{METRIC_W{phase_hot[3]}}} & metrics[53]) | ({{METRIC_W{phase_hot[4]}}} & metrics[61]);
        c_10 = ({{9{phase_hot[1]}}} & bm10) | ({{9{phase_hot[2]}}} & bm01) | ({{9{phase_hot[3]}}} & bm00) | ({{9{phase_hot[4]}}} & bm11);
        d_10 = ({{9{phase_hot[1]}}} & bm01) | ({{9{phase_hot[2]}}} & bm10) | ({{9{phase_hot[3]}}} & bm11) | ({{9{phase_hot[4]}}} & bm00);
        lane_metric[10] = (diff_10 < 0) ? yq_10 : xq_10;
        lane_decision[10] = (diff_10 < 0);
    end
    wire [METRIC_W-1:0] result_11;
    reg [METRIC_W-1:0] a_11, b_11;
    reg [8:0] c_11, d_11;
    wire [METRIC_W-1:0] x_11 = a_11 + c_11;
    wire [METRIC_W-1:0] y_11 = b_11 + d_11;
    reg [METRIC_W-1:0] xq_11, yq_11;
    always @(posedge clk) begin xq_11 <= x_11; yq_11 <= y_11; end
    wire signed [METRIC_W-1:0] diff_11 = yq_11 - xq_11;
    always @* begin
        a_11 = ({{METRIC_W{phase_hot[1]}}} & metrics[5]) | ({{METRIC_W{phase_hot[2]}}} & metric_shadow[13]) | ({{METRIC_W{phase_hot[3]}}} & metric_shadow[21]) | ({{METRIC_W{phase_hot[4]}}} & metric_shadow[29]);
        b_11 = ({{METRIC_W{phase_hot[1]}}} & metrics[37]) | ({{METRIC_W{phase_hot[2]}}} & metrics[45]) | ({{METRIC_W{phase_hot[3]}}} & metrics[53]) | ({{METRIC_W{phase_hot[4]}}} & metrics[61]);
        c_11 = ({{9{phase_hot[1]}}} & bm01) | ({{9{phase_hot[2]}}} & bm10) | ({{9{phase_hot[3]}}} & bm11) | ({{9{phase_hot[4]}}} & bm00);
        d_11 = ({{9{phase_hot[1]}}} & bm10) | ({{9{phase_hot[2]}}} & bm01) | ({{9{phase_hot[3]}}} & bm00) | ({{9{phase_hot[4]}}} & bm11);
        lane_metric[11] = (diff_11 < 0) ? yq_11 : xq_11;
        lane_decision[11] = (diff_11 < 0);
    end
    wire [METRIC_W-1:0] result_12;
    reg [METRIC_W-1:0] a_12, b_12;
    reg [8:0] c_12, d_12;
    wire [METRIC_W-1:0] x_12 = a_12 + c_12;
    wire [METRIC_W-1:0] y_12 = b_12 + d_12;
    reg [METRIC_W-1:0] xq_12, yq_12;
    always @(posedge clk) begin xq_12 <= x_12; yq_12 <= y_12; end
    wire signed [METRIC_W-1:0] diff_12 = yq_12 - xq_12;
    always @* begin
        a_12 = ({{METRIC_W{phase_hot[1]}}} & metrics[6]) | ({{METRIC_W{phase_hot[2]}}} & metric_shadow[14]) | ({{METRIC_W{phase_hot[3]}}} & metric_shadow[22]) | ({{METRIC_W{phase_hot[4]}}} & metric_shadow[30]);
        b_12 = ({{METRIC_W{phase_hot[1]}}} & metrics[38]) | ({{METRIC_W{phase_hot[2]}}} & metrics[46]) | ({{METRIC_W{phase_hot[3]}}} & metrics[54]) | ({{METRIC_W{phase_hot[4]}}} & metrics[62]);
        c_12 = ({{9{phase_hot[1]}}} & bm11) | ({{9{phase_hot[2]}}} & bm00) | ({{9{phase_hot[3]}}} & bm01) | ({{9{phase_hot[4]}}} & bm10);
        d_12 = ({{9{phase_hot[1]}}} & bm00) | ({{9{phase_hot[2]}}} & bm11) | ({{9{phase_hot[3]}}} & bm10) | ({{9{phase_hot[4]}}} & bm01);
        lane_metric[12] = (diff_12 < 0) ? yq_12 : xq_12;
        lane_decision[12] = (diff_12 < 0);
    end
    wire [METRIC_W-1:0] result_13;
    reg [METRIC_W-1:0] a_13, b_13;
    reg [8:0] c_13, d_13;
    wire [METRIC_W-1:0] x_13 = a_13 + c_13;
    wire [METRIC_W-1:0] y_13 = b_13 + d_13;
    reg [METRIC_W-1:0] xq_13, yq_13;
    always @(posedge clk) begin xq_13 <= x_13; yq_13 <= y_13; end
    wire signed [METRIC_W-1:0] diff_13 = yq_13 - xq_13;
    always @* begin
        a_13 = ({{METRIC_W{phase_hot[1]}}} & metrics[6]) | ({{METRIC_W{phase_hot[2]}}} & metric_shadow[14]) | ({{METRIC_W{phase_hot[3]}}} & metric_shadow[22]) | ({{METRIC_W{phase_hot[4]}}} & metric_shadow[30]);
        b_13 = ({{METRIC_W{phase_hot[1]}}} & metrics[38]) | ({{METRIC_W{phase_hot[2]}}} & metrics[46]) | ({{METRIC_W{phase_hot[3]}}} & metrics[54]) | ({{METRIC_W{phase_hot[4]}}} & metrics[62]);
        c_13 = ({{9{phase_hot[1]}}} & bm00) | ({{9{phase_hot[2]}}} & bm11) | ({{9{phase_hot[3]}}} & bm10) | ({{9{phase_hot[4]}}} & bm01);
        d_13 = ({{9{phase_hot[1]}}} & bm11) | ({{9{phase_hot[2]}}} & bm00) | ({{9{phase_hot[3]}}} & bm01) | ({{9{phase_hot[4]}}} & bm10);
        lane_metric[13] = (diff_13 < 0) ? yq_13 : xq_13;
        lane_decision[13] = (diff_13 < 0);
    end
    wire [METRIC_W-1:0] result_14;
    reg [METRIC_W-1:0] a_14, b_14;
    reg [8:0] c_14, d_14;
    wire [METRIC_W-1:0] x_14 = a_14 + c_14;
    wire [METRIC_W-1:0] y_14 = b_14 + d_14;
    reg [METRIC_W-1:0] xq_14, yq_14;
    always @(posedge clk) begin xq_14 <= x_14; yq_14 <= y_14; end
    wire signed [METRIC_W-1:0] diff_14 = yq_14 - xq_14;
    always @* begin
        a_14 = ({{METRIC_W{phase_hot[1]}}} & metrics[7]) | ({{METRIC_W{phase_hot[2]}}} & metric_shadow[15]) | ({{METRIC_W{phase_hot[3]}}} & metric_shadow[23]) | ({{METRIC_W{phase_hot[4]}}} & metric_shadow[31]);
        b_14 = ({{METRIC_W{phase_hot[1]}}} & metrics[39]) | ({{METRIC_W{phase_hot[2]}}} & metrics[47]) | ({{METRIC_W{phase_hot[3]}}} & metrics[55]) | ({{METRIC_W{phase_hot[4]}}} & metrics[63]);
        c_14 = ({{9{phase_hot[1]}}} & bm10) | ({{9{phase_hot[2]}}} & bm01) | ({{9{phase_hot[3]}}} & bm00) | ({{9{phase_hot[4]}}} & bm11);
        d_14 = ({{9{phase_hot[1]}}} & bm01) | ({{9{phase_hot[2]}}} & bm10) | ({{9{phase_hot[3]}}} & bm11) | ({{9{phase_hot[4]}}} & bm00);
        lane_metric[14] = (diff_14 < 0) ? yq_14 : xq_14;
        lane_decision[14] = (diff_14 < 0);
    end
    wire [METRIC_W-1:0] result_15;
    reg [METRIC_W-1:0] a_15, b_15;
    reg [8:0] c_15, d_15;
    wire [METRIC_W-1:0] x_15 = a_15 + c_15;
    wire [METRIC_W-1:0] y_15 = b_15 + d_15;
    reg [METRIC_W-1:0] xq_15, yq_15;
    always @(posedge clk) begin xq_15 <= x_15; yq_15 <= y_15; end
    wire signed [METRIC_W-1:0] diff_15 = yq_15 - xq_15;
    always @* begin
        a_15 = ({{METRIC_W{phase_hot[1]}}} & metrics[7]) | ({{METRIC_W{phase_hot[2]}}} & metric_shadow[15]) | ({{METRIC_W{phase_hot[3]}}} & metric_shadow[23]) | ({{METRIC_W{phase_hot[4]}}} & metric_shadow[31]);
        b_15 = ({{METRIC_W{phase_hot[1]}}} & metrics[39]) | ({{METRIC_W{phase_hot[2]}}} & metrics[47]) | ({{METRIC_W{phase_hot[3]}}} & metrics[55]) | ({{METRIC_W{phase_hot[4]}}} & metrics[63]);
        c_15 = ({{9{phase_hot[1]}}} & bm01) | ({{9{phase_hot[2]}}} & bm10) | ({{9{phase_hot[3]}}} & bm11) | ({{9{phase_hot[4]}}} & bm00);
        d_15 = ({{9{phase_hot[1]}}} & bm10) | ({{9{phase_hot[2]}}} & bm01) | ({{9{phase_hot[3]}}} & bm00) | ({{9{phase_hot[4]}}} & bm11);
        lane_metric[15] = (diff_15 < 0) ? yq_15 : xq_15;
        lane_decision[15] = (diff_15 < 0);
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 0) metrics[0] <= 0;
        end else if (step_enable && phase_hot[2])
            metrics[0] <= lane_metric[0];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 0) metrics[1] <= 0;
        end else if (step_enable && phase_hot[2])
            metrics[1] <= lane_metric[1];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 0) metrics[2] <= 0;
        end else if (step_enable && phase_hot[2])
            metrics[2] <= lane_metric[2];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 0) metrics[3] <= 0;
        end else if (step_enable && phase_hot[2])
            metrics[3] <= lane_metric[3];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 0) metrics[4] <= 0;
        end else if (step_enable && phase_hot[2])
            metrics[4] <= lane_metric[4];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 0) metrics[5] <= 0;
        end else if (step_enable && phase_hot[2])
            metrics[5] <= lane_metric[5];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 0) metrics[6] <= 0;
        end else if (step_enable && phase_hot[2])
            metrics[6] <= lane_metric[6];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 0) metrics[7] <= 0;
        end else if (step_enable && phase_hot[2])
            metrics[7] <= lane_metric[7];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 0) metrics[8] <= 0;
        end else if (step_enable && phase_hot[2])
            metrics[8] <= lane_metric[8];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 0) metrics[9] <= 0;
        end else if (step_enable && phase_hot[2])
            metrics[9] <= lane_metric[9];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 0) metrics[10] <= 0;
        end else if (step_enable && phase_hot[2])
            metrics[10] <= lane_metric[10];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 0) metrics[11] <= 0;
        end else if (step_enable && phase_hot[2])
            metrics[11] <= lane_metric[11];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 0) metrics[12] <= 0;
        end else if (step_enable && phase_hot[2])
            metrics[12] <= lane_metric[12];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 0) metrics[13] <= 0;
        end else if (step_enable && phase_hot[2])
            metrics[13] <= lane_metric[13];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 0) metrics[14] <= 0;
        end else if (step_enable && phase_hot[2])
            metrics[14] <= lane_metric[14];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 0) metrics[15] <= 0;
        end else if (step_enable && phase_hot[2])
            metrics[15] <= lane_metric[15];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 1) metrics[16] <= 0;
        end else if (step_enable && phase_hot[3])
            metrics[16] <= lane_metric[0];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 1) metrics[17] <= 0;
        end else if (step_enable && phase_hot[3])
            metrics[17] <= lane_metric[1];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 1) metrics[18] <= 0;
        end else if (step_enable && phase_hot[3])
            metrics[18] <= lane_metric[2];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 1) metrics[19] <= 0;
        end else if (step_enable && phase_hot[3])
            metrics[19] <= lane_metric[3];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 1) metrics[20] <= 0;
        end else if (step_enable && phase_hot[3])
            metrics[20] <= lane_metric[4];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 1) metrics[21] <= 0;
        end else if (step_enable && phase_hot[3])
            metrics[21] <= lane_metric[5];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 1) metrics[22] <= 0;
        end else if (step_enable && phase_hot[3])
            metrics[22] <= lane_metric[6];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 1) metrics[23] <= 0;
        end else if (step_enable && phase_hot[3])
            metrics[23] <= lane_metric[7];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 1) metrics[24] <= 0;
        end else if (step_enable && phase_hot[3])
            metrics[24] <= lane_metric[8];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 1) metrics[25] <= 0;
        end else if (step_enable && phase_hot[3])
            metrics[25] <= lane_metric[9];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 1) metrics[26] <= 0;
        end else if (step_enable && phase_hot[3])
            metrics[26] <= lane_metric[10];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 1) metrics[27] <= 0;
        end else if (step_enable && phase_hot[3])
            metrics[27] <= lane_metric[11];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 1) metrics[28] <= 0;
        end else if (step_enable && phase_hot[3])
            metrics[28] <= lane_metric[12];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 1) metrics[29] <= 0;
        end else if (step_enable && phase_hot[3])
            metrics[29] <= lane_metric[13];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 1) metrics[30] <= 0;
        end else if (step_enable && phase_hot[3])
            metrics[30] <= lane_metric[14];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 1) metrics[31] <= 0;
        end else if (step_enable && phase_hot[3])
            metrics[31] <= lane_metric[15];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 2) metrics[32] <= 0;
        end else if (step_enable && phase_hot[4])
            metrics[32] <= lane_metric[0];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 2) metrics[33] <= 0;
        end else if (step_enable && phase_hot[4])
            metrics[33] <= lane_metric[1];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 2) metrics[34] <= 0;
        end else if (step_enable && phase_hot[4])
            metrics[34] <= lane_metric[2];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 2) metrics[35] <= 0;
        end else if (step_enable && phase_hot[4])
            metrics[35] <= lane_metric[3];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 2) metrics[36] <= 0;
        end else if (step_enable && phase_hot[4])
            metrics[36] <= lane_metric[4];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 2) metrics[37] <= 0;
        end else if (step_enable && phase_hot[4])
            metrics[37] <= lane_metric[5];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 2) metrics[38] <= 0;
        end else if (step_enable && phase_hot[4])
            metrics[38] <= lane_metric[6];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 2) metrics[39] <= 0;
        end else if (step_enable && phase_hot[4])
            metrics[39] <= lane_metric[7];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 2) metrics[40] <= 0;
        end else if (step_enable && phase_hot[4])
            metrics[40] <= lane_metric[8];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 2) metrics[41] <= 0;
        end else if (step_enable && phase_hot[4])
            metrics[41] <= lane_metric[9];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 2) metrics[42] <= 0;
        end else if (step_enable && phase_hot[4])
            metrics[42] <= lane_metric[10];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 2) metrics[43] <= 0;
        end else if (step_enable && phase_hot[4])
            metrics[43] <= lane_metric[11];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 2) metrics[44] <= 0;
        end else if (step_enable && phase_hot[4])
            metrics[44] <= lane_metric[12];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 2) metrics[45] <= 0;
        end else if (step_enable && phase_hot[4])
            metrics[45] <= lane_metric[13];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 2) metrics[46] <= 0;
        end else if (step_enable && phase_hot[4])
            metrics[46] <= lane_metric[14];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 2) metrics[47] <= 0;
        end else if (step_enable && phase_hot[4])
            metrics[47] <= lane_metric[15];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 3) metrics[48] <= 0;
        end else if (step_enable && phase_hot[5])
            metrics[48] <= lane_metric[0];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 3) metrics[49] <= 0;
        end else if (step_enable && phase_hot[5])
            metrics[49] <= lane_metric[1];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 3) metrics[50] <= 0;
        end else if (step_enable && phase_hot[5])
            metrics[50] <= lane_metric[2];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 3) metrics[51] <= 0;
        end else if (step_enable && phase_hot[5])
            metrics[51] <= lane_metric[3];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 3) metrics[52] <= 0;
        end else if (step_enable && phase_hot[5])
            metrics[52] <= lane_metric[4];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 3) metrics[53] <= 0;
        end else if (step_enable && phase_hot[5])
            metrics[53] <= lane_metric[5];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 3) metrics[54] <= 0;
        end else if (step_enable && phase_hot[5])
            metrics[54] <= lane_metric[6];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 3) metrics[55] <= 0;
        end else if (step_enable && phase_hot[5])
            metrics[55] <= lane_metric[7];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 3) metrics[56] <= 0;
        end else if (step_enable && phase_hot[5])
            metrics[56] <= lane_metric[8];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 3) metrics[57] <= 0;
        end else if (step_enable && phase_hot[5])
            metrics[57] <= lane_metric[9];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 3) metrics[58] <= 0;
        end else if (step_enable && phase_hot[5])
            metrics[58] <= lane_metric[10];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 3) metrics[59] <= 0;
        end else if (step_enable && phase_hot[5])
            metrics[59] <= lane_metric[11];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 3) metrics[60] <= 0;
        end else if (step_enable && phase_hot[5])
            metrics[60] <= lane_metric[12];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 3) metrics[61] <= 0;
        end else if (step_enable && phase_hot[5])
            metrics[61] <= lane_metric[13];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 3) metrics[62] <= 0;
        end else if (step_enable && phase_hot[5])
            metrics[62] <= lane_metric[14];
    end
    always @(posedge clk) if (resetn) begin
        if (!initialized) begin
            if (init_phase == 3) metrics[63] <= 0;
        end else if (step_enable && phase_hot[5])
            metrics[63] <= lane_metric[15];
    end
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[8] <= metrics[8];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[9] <= metrics[9];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[10] <= metrics[10];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[11] <= metrics[11];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[12] <= metrics[12];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[13] <= metrics[13];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[14] <= metrics[14];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[15] <= metrics[15];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[16] <= metrics[16];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[17] <= metrics[17];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[18] <= metrics[18];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[19] <= metrics[19];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[20] <= metrics[20];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[21] <= metrics[21];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[22] <= metrics[22];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[23] <= metrics[23];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[24] <= metrics[24];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[25] <= metrics[25];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[26] <= metrics[26];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[27] <= metrics[27];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[28] <= metrics[28];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[29] <= metrics[29];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[30] <= metrics[30];
    always @(posedge clk)
        if (resetn && initialized && step_enable && phase_hot[0])
            metric_shadow[31] <= metrics[31];
    wire [63:0] decision_word = {lane_decision[15:0], decision_partial[47:0]};
    wire [1:0] write_quadrant = phase - 2;
    always @(posedge clk) begin
        survivor_q <= survivor[{read_ptr, state[5:4]}];
        if (resetn && step_enable && phase >= 2 && phase < 6)
            survivor[{wr_ptr,write_quadrant}] <= lane_decision;
    end
    // Traceback always moves toward older rows. The first 60 steps converge
    // from state zero; the next 64 are saved in reverse index order. Writer
    // never reaches these rows before the complete block has been decoded.
    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            phase <= 0; initialized <= 0; init_phase <= 0;
            soft0_q <= 0; soft1_q <= 0; erasure_q <= 0; decision_partial <= 0;
            wr_ptr <= 0; accepted <= 0; norm_q <= 0;
            read_ptr <= 0; walk <= 0; state <= 0;
            tracing <= 0; priming <= 0; decoded_write <= 0;
            decoded_read <= 0; decoded_ready <= 0; output_pos <= 0; output_tick <= 0;
            out_valid <= 0; out_bit <= 0;
        end else begin
            out_valid <= 0;
            output_tick <= ~output_tick;
            if (!initialized) begin
                if (init_phase == 3) initialized <= 1;
                else init_phase <= init_phase + 1;
            end else if (step_enable) begin
                if (phase_hot[0]) begin soft0_q <= soft0; soft1_q <= soft1; erasure_q <= erasure; end
                case (phase)
                  3'd2: decision_partial[0 +: 16] <= lane_decision;
                  3'd3: decision_partial[16 +: 16] <= lane_decision;
                  3'd4: decision_partial[32 +: 16] <= lane_decision;
                  default: begin end
                endcase
                if (commit_step) begin
                    phase <= 0; wr_ptr <= wr_ptr + 1;
                    if (accepted < 128) accepted <= accepted + 1;
                end else phase <= phase + 1;
            end

            if (start_trace) begin
                read_ptr <= wr_ptr - 4; state <= 0; walk <= 0;
                priming <= 1; tracing <= 1;
            end else if (tracing) begin
                if (priming) priming <= 0;
                else begin
                    read_ptr <= read_ptr - 1;
                    state <= {decision, state[5:1]};
                    walk <= walk + 1; priming <= 1;
                    if (walk >= 60) decoded[decoded_write][123-walk] <= state[0];
                    if (walk == 123) begin
                        tracing <= 0; decoded_write <= ~decoded_write;
                        decoded_ready[decoded_write] <= 1;
                    end
                end
            end

            if (decoded_ready[decoded_read] && output_tick) begin
                out_valid <= 1;
                out_bit <= decoded[decoded_read][output_pos];
                output_pos <= output_pos + 1;
                if (output_pos == 63) begin
                    decoded_read <= ~decoded_read;
                    decoded_ready[decoded_read] <= 0;
                end
            end
        end
    end
endmodule
