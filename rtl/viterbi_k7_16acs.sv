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

    reg bank;
    reg [1:0] group;
    reg initialized;
    reg [1:0] init_group;
    wire step_enable = initialized && ((group != 0) || in_valid);
    wire [2*METRIC_W-1:0] read_low [0:7];
    wire [2*METRIC_W-1:0] read_high [0:7];
    reg [METRIC_W-1:0] lane_metric [0:15];
    // Prefetch the next group's metrics. After group 3, the newly written
    // generation becomes the source. Its group-0 predecessor rows were
    // written in groups 0 and 2, so no read/write collision is required.
    wire [1:0] read_group = step_enable ? group + 2'd1 : group;
    wire read_bank = bank ^ (step_enable && group == 2'd3);

    // Bank by state[3:1], packing the even/odd destination metrics together.
    // Eight banks receive one 32-bit write each cycle. Each needs two
    // synchronous reads (predecessor state[5]=0/1); Yosys replicates these
    // into 16 BSRAMs. Array writes and reads have no asynchronous reset.
    // A four-clock startup sweep initializes the source generation only.
    genvar metric_bank;
    generate for (metric_bank = 0; metric_bank < 8; metric_bank = metric_bank + 1) begin : g_metric
        (* ram_style = "block" *) reg [2*METRIC_W-1:0] metrics [0:7];
        reg [2*METRIC_W-1:0] low_q, high_q;
        assign read_low[metric_bank] = low_q;
        assign read_high[metric_bank] = high_q;
        always @(posedge clk) begin
            low_q <= metrics[{read_bank, 1'b0, read_group[1]}];
            high_q <= metrics[{read_bank, 1'b1, read_group[1]}];
            if (resetn) begin
                if (!initialized)
                    metrics[{1'b0, init_group}] <=
                        ((metric_bank == 0) && (init_group == 0)) ? {INF, {METRIC_W{1'b0}}} : {INF, INF};
                else if (step_enable)
                    metrics[{~bank, group}] <= {lane_metric[2*metric_bank+1], lane_metric[2*metric_bank]};
            end
        end
    end endgenerate
    reg [7:0] soft0_q, soft1_q;
    reg [5:0] wr_ptr;
    reg [5:0] tb_ptr;
    reg [5:0] tb_state;
    reg [7:0] step_count;

    (* ram_style = "block" *) reg [31:0] survivor_lo [0:TRACEBACK-1];
    (* ram_style = "block" *) reg [31:0] survivor_hi [0:TRACEBACK-1];
    reg [31:0] survivor_lo_q, survivor_hi_q;
    reg [47:0] decision_partial;

    reg [15:0] lane_decision;

    integer i;
    integer p0_state;
    integer p1_state;
    integer src_idx;
    reg [METRIC_W-1:0] src0;
    reg [METRIC_W-1:0] src1;
    reg [2*METRIC_W-1:0] src_pair0, src_pair1;
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

    function automatic [8:0] soft_cost;
        input expected;
        input [7:0] sample;
        begin
            soft_cost = expected ? (9'd255 - {1'b0, sample})
                                 : {1'b0, sample};
        end
    endfunction

    assign in_ready = initialized && (group == 2'd0);

    always @* begin
        active_soft0 = (group == 2'd0) ? soft0 : soft0_q;
        active_soft1 = (group == 2'd0) ? soft1 : soft1_q;
        lane_decision = 16'b0;

        // Only four branch metrics exist for a rate-1/2 code at a given
        // received soft pair. Compute them once and share them across all
        // sixteen ACS lanes instead of duplicating the same arithmetic.
        bm00 = {1'b0, active_soft0} + {1'b0, active_soft1};
        bm01 = {1'b0, active_soft0} + (9'd255 - {1'b0, active_soft1});
        bm10 = (9'd255 - {1'b0, active_soft0}) + {1'b0, active_soft1};
        bm11 = 9'd510 - {1'b0, active_soft0} - {1'b0, active_soft1};

        for (i = 0; i < 16; i = i + 1) begin
            src_idx = (i >> 2) + (group[0] ? 4 : 0);
            src_pair0 = read_low[src_idx];
            src_pair1 = read_high[src_idx];
            src0 = (i & 2) ? src_pair0[2*METRIC_W-1:METRIC_W] : src_pair0[METRIC_W-1:0];
            src1 = (i & 2) ? src_pair1[2*METRIC_W-1:METRIC_W] : src_pair1[METRIC_W-1:0];

            p0_state = (group << 3) + (i >> 1);
            p1_state = p0_state + 32;
            coded0 = encode_pair(p0_state[5:0], i[0]);
            case (coded0)
                2'b00: branch0 = bm00;
                2'b01: branch0 = bm01;
                2'b10: branch0 = bm10;
                default: branch0 = bm11;
            endcase

            // The two predecessor states differ only in the oldest shift-
            // register bit. Both K=7 generators include that tap, therefore
            // the competing branch codeword is the bitwise complement.
            branch1 = 9'd510 - branch0;

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

    // Keep the RAM ports in clock-only processes. In particular, do not put
    // the write port in the asynchronously-reset control process below; that
    // causes Yosys to lower the memory to individual flip-flops.
    always @(posedge clk) begin
        survivor_lo_q <= survivor_lo[tb_ptr];
        survivor_hi_q <= survivor_hi[tb_ptr];
    end

    always @(posedge clk) begin
        if (resetn && initialized && (group == 2'd3)) begin
            survivor_lo[wr_ptr] <= decision_partial[31:0];
            survivor_hi[wr_ptr] <= {lane_decision, decision_partial[47:32]};
        end
    end

    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            bank <= 1'b0;
            group <= 2'd0;
            initialized <= 1'b0;
            init_group <= 2'd0;
            soft0_q <= 8'd0;
            soft1_q <= 8'd0;
            wr_ptr <= 6'd0;
            tb_ptr <= 6'd0;
            tb_state <= 6'd0;
            step_count <= 8'd0;
            out_valid <= 1'b0;
            out_bit <= 1'b0;
            decision_partial <= 48'd0;

        end else begin
            out_valid <= 1'b0;

            if (!initialized) begin
                // Initialize only the source generation. Every destination
                // entry is written before the ping-pong bank is switched.
                init_group <= init_group + 2'd1;
                if (init_group == 2'd3)
                    initialized <= 1'b1;
            end else if (step_enable) begin
                if (group == 2'd0) begin
                    soft0_q <= soft0;
                    soft1_q <= soft1;
                end

                case (group)
                    2'd0: decision_partial[15:0]  <= lane_decision;
                    2'd1: decision_partial[31:16] <= lane_decision;
                    2'd2: decision_partial[47:32] <= lane_decision;
                    default: begin
                        // Survivor RAM write is performed in its dedicated
                        // synchronous write-port process above.
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
