// REQUIRES s3_tc8psk_metric COST_SHIFT=22, Q1.15 I/Q; arbitrary costs are NOT supported.
module s3_tc8psk #(
    parameter integer METRIC_W = 12,
    parameter integer TRACEBACK = 64
) (
    input  wire        clk,
    input  wire        resetn,
    input  wire        in_valid,
    output wire        in_ready,
    input wire [35:0] costs,
    input wire [3:0] b1_choice,
    output reg         out_valid,
    output reg [1:0]   out_bits
);
    localparam [METRIC_W-1:0] INF = {METRIC_W{1'b1}};

    // Three in-place updates write states 0..21, 22..43 and 44..63.
    // Before the first write preserve old states 11..21; before the second
    // preserve 22..31 in the same eleven shadow registers. The last update
    // has twenty useful lanes. All 64 path metrics use the fixed Q15/SHIFT22 12-bit modulo contract.
    reg [1:0] phase;
    reg initialized;
    reg [1:0] init_phase;
    reg [METRIC_W-1:0] metrics [0:63];
    reg [METRIC_W-1:0] metric_shadow [0:10];
    reg [METRIC_W-1:0] lane_metric [0:21];
    reg [21:0] lane_decision;
    wire step_enable = initialized && ((phase != 0) || in_valid);

    reg [35:0] costs_q;
    reg [3:0] b1_q;
    wire [35:0] active_costs=phase?costs_q:costs;
    wire [3:0] active_b1=phase?b1_q:b1_choice;

    reg [7:0] wr_ptr;
    reg [7:0] accepted;
    reg norm_q;
    reg [43:0] decision_partial;
    wire normalize = phase ? norm_q : metrics[0][METRIC_W-1];
    (* ram_style = "block" *) reg [31:0] survivor_lo [0:255];
    (* ram_style = "block" *) reg [31:0] survivor_hi [0:255];
    reg [63:0] survivor_q, survivor_pipe;
    reg prime_extra;
    reg [7:0] read_ptr;
    reg [6:0] walk;
    reg [5:0] state;
    reg tracing, priming;
    (* ram_style="block" *) reg [1:0] decoded_mem[0:127];
    reg save_valid,save_bank,save_last,save_b0,save_b1;
    reg [5:0] save_index;
    (* ram_style="block" *) reg [3:0] branch_choice[0:255];
    reg [3:0] uncoded_q,uncoded_pipe;
    wire [1:0] traceback_xy=encode_pair({survivor_pipe[state],state[5:1]},state[0]);
    reg decoded_write, decoded_read;
    reg [1:0] decoded_ready;
    reg output_tick;
    reg [5:0] output_pos;
    wire start_trace = initialized && (phase == 2) && (accepted >= 127) &&
                      (wr_ptr[5:0] == 63);
    wire decision = survivor_pipe[state];

    initial begin
        if (METRIC_W != 12 || TRACEBACK != 64)
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

        lane_decision = 22'b0;

        bm00 = active_costs[0 +: 9];
        bm01 = active_costs[9 +: 9];
        bm10 = active_costs[18 +: 9];
        bm11 = active_costs[27 +: 9];

        for (i = 0; i < 22; i = i + 1) begin
            // Destinations are phase*22+i; phase2 lanes20/21 are not stored.
            // Each destination state has predecessors state>>1 and +32.
            p0_state = (phase == 0 ? 0 : phase == 1 ? 11 : 22) + (i >> 1);
            p1_state = p0_state + 32;
            src0 = phase ? metric_shadow[i >> 1] : metrics[i >> 1];
            src1 = phase == 0 ? metrics[32 + (i >> 1)] : phase == 1 ? metrics[43 + (i >> 1)] : i < 20 ? metrics[54 + (i >> 1)] : 0;

            coded0 = phase == 0 ? encode_pair(i >> 1, i[0]) : phase == 1 ? encode_pair(11+(i >> 1), i[0]) : encode_pair(22+(i >> 1), i[0]);
            case (coded0)
                2'b00: begin branch0 = bm00; branch1 = bm11; end
                2'b01: begin branch0 = bm01; branch1 = bm10; end
                2'b10: begin branch0 = bm10; branch1 = bm01; end
                default: begin branch0 = bm11; branch1 = bm00; end
            endcase

            cand0 = {1'b0, src0} + branch0;
            cand1 = {1'b0, src1} + branch1;
            metric_difference = cand1[METRIC_W-1:0] - cand0[METRIC_W-1:0];
            if (metric_difference < 0) begin
                lane_metric[i] = cand1[METRIC_W-1:0];
                lane_decision[i] = 1'b1;
            end else begin
                lane_metric[i] = cand0[METRIC_W-1:0];
                lane_decision[i] = 1'b0;
            end

        end
    end

    genvar metric_slot;
    generate for (metric_slot=0; metric_slot<64; metric_slot=metric_slot+1) begin : g_metric_state
        always @(posedge clk) begin
            if (resetn) begin
                if (!initialized) begin
                    if (init_phase == (metric_slot / 22))
                        metrics[metric_slot] <= {METRIC_W{1'b0}};
                end else if (step_enable && (phase == (metric_slot / 22))) begin
                    metrics[metric_slot] <= lane_metric[metric_slot % 22];
                end
            end
        end
    end
    for (metric_slot=0; metric_slot<11; metric_slot=metric_slot+1) begin : g_metric_shadow
        always @(posedge clk) begin
            if (resetn && initialized && step_enable) begin
                if (phase == 0) metric_shadow[metric_slot] <= metrics[11 + metric_slot];
                else if (phase == 1 && metric_slot < 10)
                    metric_shadow[metric_slot] <= metrics[22 + metric_slot];
            end
        end
    end endgenerate

    always @(posedge clk) begin
        survivor_q <= {survivor_hi[read_ptr], survivor_lo[read_ptr]};
        survivor_pipe <= survivor_q;
        uncoded_q <= branch_choice[read_ptr];
        uncoded_pipe <= uncoded_q;
        if (resetn && initialized && phase == 2) begin
            survivor_lo[wr_ptr] <= decision_partial[31:0];
            survivor_hi[wr_ptr] <= {lane_decision[19:0],decision_partial[43:32]};
            branch_choice[wr_ptr] <= b1_q;
        end
    end

    always @(posedge clk) begin
        if (resetn && save_valid)
            decoded_mem[{save_bank,save_index}] <= {save_b1,save_b0};
        if (resetn && decoded_ready[decoded_read] && output_tick)
            out_bits <= decoded_mem[{decoded_read,output_pos}];
    end

    // Traceback always moves toward older rows. The first 60 steps converge
    // from state zero; the next 64 are saved in reverse index order. Writer
    // never reaches these rows before the complete block has been decoded.
    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            phase <= 0; initialized <= 0; init_phase <= 0;
            costs_q <= 0; b1_q <= 0; decision_partial <= 0;
            wr_ptr <= 0; accepted <= 0; norm_q <= 0;
            read_ptr <= 0; walk <= 0; state <= 0;
            prime_extra <= 0;
            tracing <= 0; priming <= 0; decoded_write <= 0;
            decoded_read <= 0; decoded_ready <= 0; output_pos <= 0; output_tick <= 0;
            out_valid <= 0;
            save_valid<=0;save_bank<=0;save_last<=0;
            save_b0<=0;save_b1<=0;save_index<=0;
        end else begin
            out_valid <= 0;
            save_valid<=0;
            if (save_valid) begin
                if (save_last) decoded_ready[save_bank]<=1;
            end
            output_tick <= ~output_tick;
            if (!initialized) begin
                if (init_phase == 2) initialized <= 1;
                else init_phase <= init_phase + 1'b1;
            end else if (step_enable) begin
                if (!phase) begin
                    costs_q <= costs; b1_q <= b1_choice;
                    decision_partial[21:0] <= lane_decision;
                    norm_q <= metrics[0][METRIC_W-1];
                    phase <= 1;
                end else if (phase == 1) begin
                    decision_partial[43:22] <= lane_decision;
                    phase <= 2;
                end else begin
                    phase <= 0;
                    wr_ptr <= wr_ptr + 1;
                    if (accepted < 128) accepted <= accepted + 1;
                end
            end

            if (start_trace) begin
                read_ptr <= wr_ptr - 4; state <= 0; walk <= 0;
                priming <= 1; prime_extra <= 1; tracing <= 0;
            end else if (priming) begin
                read_ptr <= read_ptr - 1;
                if (prime_extra) prime_extra <= 0;
                else begin priming <= 0; tracing <= 1; end
            end else if (tracing) begin
                read_ptr <= read_ptr - 1;
                state <= {decision, state[5:1]};
                walk <= walk + 1;
                if (walk >= 60) begin
                    save_valid<=1; save_bank<=decoded_write;
                    save_index<=6'd59-walk[5:0];
                    save_b0<=state[0]; save_b1<=uncoded_pipe[traceback_xy];
                    save_last<=walk==123;
                end
                if (walk == 123) begin
                    tracing <= 0;
                    decoded_write <= ~decoded_write;

                end
            end

            if (decoded_ready[decoded_read] && output_tick) begin
                out_valid <= 1;
                output_pos <= output_pos + 1;
                if (output_pos == 63) begin
                    decoded_read <= ~decoded_read;
                    decoded_ready[decoded_read] <= 0;
                end
            end
        end
    end
endmodule
