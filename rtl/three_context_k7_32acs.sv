// Three-context K=7, 32 ACS lanes, two clocks/trellis step.
// 8-bit soft inputs, puncture erasure, 13-bit modulo path metrics, 64-state
// survivor traceback. Device fit and real-time service are not yet qualified.
module three_context_k7_32acs #(
    parameter integer METRIC_W = 13,
    parameter integer TRACEBACK = 64
) (
    input  wire        clk,
    input  wire        resetn,
    input wire slot_valid,
    output wire slot_ready,
    input wire [1:0] slot_context,
    output reg [1:0] out_context,
    input  wire        in_valid,
    output wire        in_ready,
    input  wire [7:0]  soft0,
    input  wire [7:0]  soft1,
    input wire [1:0] erasure,
    output reg         out_valid,
    output reg         out_bit
);
    reg initialized [0:2];
    reg [7:0] wr_ptr [0:2];
    reg [7:0] accepted [0:2];
    reg [63:0] survivor_q [0:2];
    reg [63:0] survivor_pipe [0:2];
    reg prime_extra [0:2];
    reg [7:0] read_ptr [0:2];
    reg [6:0] walk [0:2];
    reg [5:0] state [0:2];
    reg tracing [0:2];
    reg priming [0:2];
    reg decoded_write [0:2];
    reg decoded_read [0:2];
    reg [1:0] decoded_ready [0:2];
    reg output_tick [0:2];
    reg [5:0] output_pos [0:2];
    reg [1:0] slot_phase; // only phases 0 and 1 are reachable
    wire slot_active = slot_phase != 0;
    reg [1:0] held_context;
    wire [1:0] context_id = slot_active ? held_context : slot_context;
    wire tick = resetn && (slot_active || (slot_valid && slot_context < 3));
    assign slot_ready = resetn && !slot_active && slot_context < 3;
    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin slot_phase<=0; held_context<=0; end
        else if (tick) begin
            slot_phase <= {1'b0, ~slot_phase[0]};
            if (!slot_active) held_context<=slot_context;
        end
    end
    integer reset_context;
    localparam [METRIC_W-1:0] INF = {METRIC_W{1'b1}};

    // Read old generation throughout all four phases; flip at commit.
    wire [1:0] phase = slot_phase;
    reg active_step;
    reg generation [0:2];

    
    wire [METRIC_W-1:0] metrics [0:191];
    wire [METRIC_W-1:0] selected_metrics [0:63];
    
    reg [METRIC_W-1:0] lane_metric [0:31];
    reg [31:0] lane_decision;
    wire step_enable = initialized[context_id] && (slot_active ? active_step : in_valid);

    reg [7:0] soft0_q, soft1_q;
    reg [1:0] erasure_q;
    wire [1:0] active_erasure=phase?erasure_q:erasure;



    reg [31:0] decision_partial;

    (* ram_style = "block" *) reg [31:0] survivor_lo [0:1023];
    (* ram_style = "block" *) reg [31:0] survivor_hi [0:1023];






    reg [63:0] decoded [0:5];




    wire start_trace = step_enable && phase == 1 && (accepted[context_id] >= 127) &&
                      (wr_ptr[context_id][5:0] == 63);
    wire decision = survivor_pipe[context_id][state[context_id]];

    initial begin
        if (METRIC_W != 13 || TRACEBACK != 64)
            $fatal(1, "unsupported traceback/metric parameter override");
    end
    reg [63:0] ram_q;
    reg [1:0] ram_context;
    reg ram_valid;
    wire [63:0] current_survivor_q = ram_valid && ram_context == context_id
                                    ? ram_q : survivor_q[context_id];
    always @(posedge clk) begin
        if (tick) ram_q <= {survivor_hi[{context_id, read_ptr[context_id]}],
                            survivor_lo[{context_id, read_ptr[context_id]}]};
        if (ram_valid) survivor_q[ram_context] <= ram_q;
    end
    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin ram_context<=0; ram_valid<=0; end
        else begin ram_valid<=tick; if(tick)ram_context<=context_id; end
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

    assign in_ready = slot_ready && initialized[context_id] && !phase;

    always @* begin
        active_soft0 = !phase ? soft0 : soft0_q;
        active_soft1 = !phase ? soft1 : soft1_q;
        lane_decision = 32'b0;

        bm00 = (active_erasure[1] ? 9'd0 : {1'b0, active_soft0}) + (active_erasure[0] ? 9'd0 : {1'b0, active_soft1});
        bm01 = (active_erasure[1] ? 9'd0 : {1'b0, active_soft0}) + (active_erasure[0] ? 9'd0 : {1'b0, ~active_soft1});
        bm10 = (active_erasure[1] ? 9'd0 : {1'b0, ~active_soft0}) + (active_erasure[0] ? 9'd0 : {1'b0, active_soft1});
        bm11 = (active_erasure[1] ? 9'd0 : {1'b0, ~active_soft0}) + (active_erasure[0] ? 9'd0 : {1'b0, ~active_soft1});

        for (i = 0; i < 32; i = i + 1) begin
            // Each phase produces sixteen consecutive destination states.
            // Each destination state[context_id] has predecessors state[context_id]>>1 and +32.
            p0_state = 16*phase + (i >> 1);
            p1_state = p0_state + 32;
            src0 = selected_metrics[(phase[0] ? 16 : 0) + (i >> 1)];
            src1 = selected_metrics[32 + (phase[0] ? 16 : 0) + (i >> 1)];

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

    // 32 ACS lanes, 2 phases, 3 independent contexts. The two generations
    // store 32 x 3 x 2 x 2 x METRIC_W = 4992 bits when METRIC_W=13.
    // Old generation is never overwritten until both phases have completed.
    generate for(genvar lane=0;lane<32;lane=lane+1)begin : g_metric
        (* ram_style = "distributed" *) reg [METRIC_W-1:0] bank [0:15];
        assign selected_metrics[lane] = bank[{context_id,generation[context_id],1'b0}];
        assign selected_metrics[32+lane] = bank[{context_id,generation[context_id],1'b1}];
        for(genvar ct=0;ct<3;ct=ct+1)begin : g_context
            assign metrics[64*ct+lane] = bank[4*ct+2*generation[ct]];
            assign metrics[64*ct+32+lane] = bank[4*ct+2*generation[ct]+1];
        end
        always @(posedge clk) if(tick) begin
            if(!initialized[context_id])
                bank[{context_id,1'b0,phase[0]}] <= 0;
            else if(step_enable)
                bank[{context_id,~generation[context_id],phase[0]}] <= lane_metric[lane];
        end
    end endgenerate

    always @(posedge clk) begin
        if (tick) begin

        survivor_pipe[context_id] <= current_survivor_q;
        if (tick && step_enable && phase == 1) begin
            survivor_lo[{context_id, wr_ptr[context_id]}] <= decision_partial[31:0];
            survivor_hi[{context_id, wr_ptr[context_id]}] <= lane_decision;
        end
    end
    end

    // Traceback always moves toward older rows. The first 60 steps converge
    // from state[context_id] zero; the next 64 are saved in reverse index order. Writer
    // never reaches these rows before the complete block has been decoded.
    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            out_context<=0;
            for(reset_context=0;reset_context<3;reset_context=reset_context+1)begin
            active_step<=0; generation[reset_context]<=0; initialized[reset_context]<=0;
            soft0_q <= 0; soft1_q <= 0; erasure_q<=0; decision_partial <= 0;
            wr_ptr[reset_context] <= 0; accepted[reset_context] <= 0;
            read_ptr[reset_context] <= 0; walk[reset_context] <= 0; state[reset_context] <= 0;
            prime_extra[reset_context] <= 0;
            tracing[reset_context] <= 0; priming[reset_context] <= 0; decoded_write[reset_context] <= 0;
            decoded_read[reset_context] <= 0; decoded_ready[reset_context] <= 0; output_pos[reset_context] <= 0; output_tick[reset_context] <= 0;
            out_valid <= 0; out_bit <= 0;
            end
        end else begin
            out_valid <= 0;
            if (tick) begin
            out_context <= context_id;
            output_tick[context_id] <= ~output_tick[context_id];
            if(!slot_active) active_step<=in_valid && initialized[context_id];
            if (!initialized[context_id]) begin
                if(phase==1)initialized[context_id]<=1;
            end else if(step_enable)begin
                if(phase==0)begin soft0_q<=soft0; soft1_q<=soft1; erasure_q<=erasure; end
                if(phase==0)decision_partial<=lane_decision;
                else begin
                    generation[context_id]<=~generation[context_id];
                    wr_ptr[context_id]<=wr_ptr[context_id]+1;
                    if(accepted[context_id]<128)accepted[context_id]<=accepted[context_id]+1;
                end
            end

            if (start_trace) begin
                read_ptr[context_id] <= wr_ptr[context_id] - 4; state[context_id] <= 0; walk[context_id] <= 0;
                priming[context_id] <= 1; prime_extra[context_id] <= 1; tracing[context_id] <= 0;
            end else if (priming[context_id]) begin
                read_ptr[context_id] <= read_ptr[context_id] - 1;
                if (prime_extra[context_id]) prime_extra[context_id] <= 0;
                else begin priming[context_id] <= 0; tracing[context_id] <= 1; end
            end else if (tracing[context_id]) begin
                read_ptr[context_id] <= read_ptr[context_id] - 1;
                state[context_id] <= {decision, state[context_id][5:1]};
                walk[context_id] <= walk[context_id] + 1;
                
                if (walk[context_id] == 123) begin
                    tracing[context_id] <= 0;
                    decoded_write[context_id] <= ~decoded_write[context_id];
                    decoded_ready[context_id][decoded_write[context_id]] <= 1;
                end
            end

            if (decoded_ready[context_id][decoded_read[context_id]] && output_tick[context_id]) begin
                out_valid <= 1;
                out_bit <= decoded[{context_id, decoded_read[context_id]}][0];
                
                output_pos[context_id] <= output_pos[context_id] + 1;
                if (output_pos[context_id] == 63) begin
                    decoded_read[context_id] <= ~decoded_read[context_id];
                    decoded_ready[context_id][decoded_read[context_id]] <= 0;
                end
            end
            end
        end
    end
    generate for(genvar bank_id=0;bank_id<6;bank_id=bank_id+1)begin : g_output_bank
        always @(posedge clk) begin
            if(tick && tracing[context_id] && walk[context_id]>=60 &&
               {context_id,decoded_write[context_id]} == bank_id)
                decoded[bank_id] <= {decoded[bank_id][62:0],state[context_id][0]};
            if(tick && decoded_ready[context_id][decoded_read[context_id]] &&
               output_tick[context_id] && {context_id,decoded_read[context_id]} == bank_id)
                decoded[bank_id] <= {1'b0,decoded[bank_id][63:1]};
        end
    end endgenerate
endmodule
