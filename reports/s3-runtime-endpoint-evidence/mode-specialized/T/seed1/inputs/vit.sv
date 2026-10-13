module s3_viterbi_traceback #(
    parameter integer METRIC_W = 13,
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

    reg [7:0] soft0_q, soft1_q;
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
    reg [63:0] decoded [0:1];
    reg decoded_write, decoded_read;
    reg [1:0] decoded_ready;
    reg output_tick;
    reg [5:0] output_pos;
    wire start_trace = initialized && phase && (accepted >= 127) &&
                      (wr_ptr[5:0] == 63);
    wire decision = survivor_pipe[state];

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
        if (resetn && initialized && phase) begin
            survivor_lo[wr_ptr] <= decision_partial;
            survivor_hi[wr_ptr] <= lane_decision;
        end
    end

    // Traceback always moves toward older rows. The first 60 steps converge
    // from state zero; the next 64 are saved in reverse index order. Writer
    // never reaches these rows before the complete block has been decoded.
    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            phase <= 0; initialized <= 0; init_phase <= 0;
            soft0_q <= 0; soft1_q <= 0; decision_partial <= 0;
            wr_ptr <= 0; accepted <= 0; norm_q <= 0;
            read_ptr <= 0; walk <= 0; state <= 0;
            prime_extra <= 0;
            tracing <= 0; priming <= 0; decoded_write <= 0;
            decoded_read <= 0; decoded_ready <= 0; output_pos <= 0; output_tick <= 0;
            out_valid <= 0; out_bit <= 0;
        end else begin
            out_valid <= 0;
            output_tick <= ~output_tick;
            if (!initialized) begin
                init_phase <= ~init_phase;
                if (init_phase) initialized <= 1;
            end else if (step_enable) begin
                if (!phase) begin
                    soft0_q <= soft0; soft1_q <= soft1;
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
                if (walk >= 60) decoded[decoded_write][123-walk] <= state[0];
                if (walk == 123) begin
                    tracing <= 0;
                    decoded_write <= ~decoded_write;
                    decoded_ready[decoded_write] <= 1;
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
