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

    // Two phases update the 64 metrics in place. Phase 0 would overwrite
    // predecessors 16..31 needed by phase 1, so only that quarter is saved.
    // The shadow snapshot and first-half writes use the same clock edge;
    // nonblocking assignments preserve the old predecessor generation.
    reg phase;
    reg initialized;
    reg init_phase;
    reg [METRIC_W-1:0] metrics [0:63];
    reg [METRIC_W-1:0] metric_shadow [0:15];
    reg [METRIC_W-1:0] lane_metric [0:31];
    reg [31:0] lane_decision;
    wire step_enable = initialized && (phase || in_valid);

    reg [35:0] costs_q;
    reg [3:0] b1_q;
    wire [35:0] active_costs=phase?costs_q:costs;
    wire [3:0] active_b1=phase?b1_q:b1_choice;

    reg [7:0] wr_ptr;
    reg [7:0] accepted;
    reg norm_q;
    reg [31:0] decision_partial;
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
    wire [63:0] traceback_b1;
    genvar trace_state;
    generate for(trace_state=0;trace_state<64;trace_state=trace_state+1)begin:g_trace_b1
        localparam [1:0] BASE=encode_pair(trace_state >> 1,trace_state & 1);
        assign traceback_b1[trace_state]=survivor_pipe[trace_state] ?
            uncoded_pipe[BASE ^ 2'b11] : uncoded_pipe[BASE];
    end endgenerate
    reg decoded_write, decoded_read;
    reg [1:0] decoded_ready;
    reg output_tick;
    reg [5:0] output_pos;
    wire start_trace = initialized && phase && (accepted >= 127) &&
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

        lane_decision = 32'b0;

        bm00 = active_costs[0 +: 9];
        bm01 = active_costs[9 +: 9];
        bm10 = active_costs[18 +: 9];
        bm11 = active_costs[27 +: 9];

        for (i = 0; i < 32; i = i + 1) begin
            // phase 0 produces states 0..31 and phase 1 states 32..63.
            // Each destination state has predecessors state>>1 and +32.
            p0_state = (phase ? 16 : 0) + (i >> 1);
            p1_state = p0_state + 32;
            src0 = phase ? metric_shadow[i >> 1] : metrics[i >> 1];
            src1 = phase ? metrics[48 + (i >> 1)] : metrics[32 + (i >> 1)];

            coded0 = encode_pair(p0_state[5:0], i[0]);
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
                    if (init_phase == (metric_slot >= 32))
                        metrics[metric_slot] <= {METRIC_W{1'b0}};
                end else if (step_enable && (phase == (metric_slot >= 32))) begin
                    metrics[metric_slot] <= lane_metric[metric_slot % 32];
                end
            end
        end
    end
    for (metric_slot=0; metric_slot<16; metric_slot=metric_slot+1) begin : g_metric_shadow
        always @(posedge clk) begin
            if (resetn && initialized && step_enable && !phase)
                metric_shadow[metric_slot] <= metrics[16 + metric_slot];
        end
    end endgenerate

    always @(posedge clk) begin
        survivor_q <= {survivor_hi[read_ptr], survivor_lo[read_ptr]};
        survivor_pipe <= survivor_q;
        uncoded_q <= branch_choice[read_ptr];
        uncoded_pipe <= uncoded_q;
        if (resetn && initialized && phase) begin
            survivor_lo[wr_ptr] <= decision_partial;
            survivor_hi[wr_ptr] <= lane_decision;
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
                init_phase <= ~init_phase;
                if (init_phase) initialized <= 1;
            end else if (step_enable) begin
                if (!phase) begin
                    costs_q <= costs; b1_q <= b1_choice;
                    decision_partial <= lane_decision;
                    norm_q <= metrics[0][METRIC_W-1];
                    phase <= 1;
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
                    save_b0<=state[0]; save_b1<=traceback_b1[state];
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
