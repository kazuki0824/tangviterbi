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
    localparam [METRIC_W-1:0] INF = {METRIC_W{1'b1}};

    reg [METRIC_W-1:0] ma0 [0:15];
    reg [METRIC_W-1:0] ma1 [0:15];
    reg [METRIC_W-1:0] ma2 [0:15];
    reg [METRIC_W-1:0] ma3 [0:15];
    reg [METRIC_W-1:0] mb0 [0:15];
    reg [METRIC_W-1:0] mb1 [0:15];
    reg [METRIC_W-1:0] mb2 [0:15];
    reg [METRIC_W-1:0] mb3 [0:15];

    reg bank;
    reg [1:0] group;
    reg [7:0] soft0_q, soft1_q;
    reg [5:0] wr_ptr;
    reg [5:0] tb_ptr;
    reg [5:0] tb_state;
    reg [7:0] step_count;

    reg [31:0] survivor_lo [0:TRACEBACK-1];
    reg [31:0] survivor_hi [0:TRACEBACK-1];
    reg [31:0] survivor_lo_q, survivor_hi_q;
    reg [47:0] decision_partial;

    reg [METRIC_W-1:0] lane_metric [0:15];
    reg [15:0] lane_decision;

    integer i;
    integer p0_state;
    integer p1_state;
    integer src_idx;
    reg [METRIC_W-1:0] src0;
    reg [METRIC_W-1:0] src1;
    reg [1:0] coded0;
    reg [1:0] coded1;
    reg [8:0] branch0;
    reg [8:0] branch1;
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

    function automatic [8:0] soft_cost;
        input expected;
        input [7:0] sample;
        begin
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
            src_idx = (i >> 1) + (group[0] ? 8 : 0);
            if (!bank) begin
                if (!group[1]) begin
                    src0 = ma0[src_idx];
                    src1 = ma2[src_idx];
                end else begin
                    src0 = ma1[src_idx];
                    src1 = ma3[src_idx];
                end
            end else begin
                if (!group[1]) begin
                    src0 = mb0[src_idx];
                    src1 = mb2[src_idx];
                end else begin
                    src0 = mb1[src_idx];
                    src1 = mb3[src_idx];
                end
            end

            p0_state = (group << 3) + (i >> 1);
            p1_state = p0_state + 32;
            coded0 = encode_pair(p0_state[5:0], i[0]);
            coded1 = encode_pair(p1_state[5:0], i[0]);

            branch0 = soft_cost(coded0[1], active_soft0)
                    + soft_cost(coded0[0], active_soft1);
            branch1 = soft_cost(coded1[1], active_soft0)
                    + soft_cost(coded1[0], active_soft1);

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

    always @(posedge clk) begin
        survivor_lo_q <= survivor_lo[tb_ptr];
        survivor_hi_q <= survivor_hi[tb_ptr];
    end

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            bank <= 1'b0;
            group <= 2'd0;
            soft0_q <= 8'd0;
            soft1_q <= 8'd0;
            wr_ptr <= 6'd0;
            tb_ptr <= 6'd0;
            tb_state <= 6'd0;
            step_count <= 8'd0;
            out_valid <= 1'b0;
            out_bit <= 1'b0;
            decision_partial <= 48'd0;

            for (i = 0; i < 16; i = i + 1) begin
                ma0[i] <= (i == 0) ? {METRIC_W{1'b0}} : INF;
                ma1[i] <= INF;
                ma2[i] <= INF;
                ma3[i] <= INF;
                mb0[i] <= INF;
                mb1[i] <= INF;
                mb2[i] <= INF;
                mb3[i] <= INF;
            end
        end else begin
            out_valid <= 1'b0;

            if ((group != 2'd0) || in_valid) begin
                if (group == 2'd0) begin
                    soft0_q <= soft0;
                    soft1_q <= soft1;
                end

                if (!bank) begin
                    case (group)
                        2'd0: for (i=0; i<16; i=i+1) mb0[i] <= lane_metric[i];
                        2'd1: for (i=0; i<16; i=i+1) mb1[i] <= lane_metric[i];
                        2'd2: for (i=0; i<16; i=i+1) mb2[i] <= lane_metric[i];
                        2'd3: for (i=0; i<16; i=i+1) mb3[i] <= lane_metric[i];
                    endcase
                end else begin
                    case (group)
                        2'd0: for (i=0; i<16; i=i+1) ma0[i] <= lane_metric[i];
                        2'd1: for (i=0; i<16; i=i+1) ma1[i] <= lane_metric[i];
                        2'd2: for (i=0; i<16; i=i+1) ma2[i] <= lane_metric[i];
                        2'd3: for (i=0; i<16; i=i+1) ma3[i] <= lane_metric[i];
                    endcase
                end

                case (group)
                    2'd0: decision_partial[15:0]  <= lane_decision;
                    2'd1: decision_partial[31:16] <= lane_decision;
                    2'd2: decision_partial[47:32] <= lane_decision;
                    default: begin
                        survivor_lo[wr_ptr] <= decision_partial[31:0];
                        survivor_hi[wr_ptr] <= {lane_decision, decision_partial[47:32]};
                    end
                endcase

                if (group == 2'd3) begin
                    group <= 2'd0;
                    bank <= ~bank;
                    wr_ptr <= wr_ptr + 6'd1;
                    step_count <= step_count + 8'd1;

                    if (step_count >= TRACEBACK) begin
                        tb_ptr <= tb_ptr + 6'd1;
                        if (!tb_state[5])
                            out_bit <= survivor_lo_q[tb_state[4:0]];
                        else
                            out_bit <= survivor_hi_q[tb_state[4:0]];
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
