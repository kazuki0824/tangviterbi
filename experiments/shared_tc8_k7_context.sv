module shared_tc8_k7_context #(
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
    output reg         out_bit,
    input wire in_tc8, input wire[35:0] costs, input wire[3:0] b1_choice,
    output reg out_b1
);
    reg initialized [0:3];
    reg [7:0] wr_ptr [0:3];
    reg [7:0] accepted [0:3];
    reg [63:0] survivor_q [0:3];
    reg [63:0] survivor_pipe [0:3];
    reg prime_extra [0:3];
    reg [7:0] read_ptr [0:3];
    reg [6:0] walk [0:3];
    reg [5:0] state [0:3];
    reg tracing [0:3];
    reg priming [0:3];
    reg decoded_write [0:3];
    reg decoded_read [0:3];
    reg [1:0] decoded_ready [0:3];
    reg output_tick [0:3];
    reg [5:0] output_pos [0:3];
    reg slot_active;
    reg [1:0] held_context;
    wire [1:0] context_id = slot_active ? held_context : slot_context;
    wire tick = resetn && (slot_active || slot_valid);
    assign slot_ready = resetn && !slot_active;
    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin slot_active<=0; held_context<=0; end
        else if (slot_active) slot_active<=0;
        else if (slot_valid) begin slot_active<=1; held_context<=slot_context; end
    end
    integer reset_context;
    localparam [METRIC_W-1:0] INF = {METRIC_W{1'b1}};

    // Two phases update the 64 metrics in place. Phase 0 would overwrite
    // predecessors 16..31 needed by phase 1, so only that quarter is saved.
    // The shadow snapshot and first-half writes use the same clock edge;
    // nonblocking assignments preserve the old predecessor generation.
    reg phase;

    reg init_phase;
    wire [METRIC_W-1:0] metrics [0:255];
    wire [METRIC_W-1:0] selected_metrics [0:63];
    reg [METRIC_W-1:0] metric_shadow [0:15];
    reg [METRIC_W-1:0] lane_metric [0:31];
    reg [31:0] lane_decision;
    wire step_enable = initialized[context_id] && (phase || (!slot_active && in_valid));

    reg [7:0] soft0_q, soft1_q;
    reg tc8_q;reg[35:0]costs_q;reg[3:0]b1_q;
    wire use_costs=context_id==3 && (phase ? tc8_q : in_tc8);
    wire[35:0]active_costs=phase ? costs_q : costs;
    reg [1:0] erasure_q;
    wire [1:0] active_erasure=phase?erasure_q:erasure;


    reg norm_q;
    reg [31:0] decision_partial;
    wire normalize = phase ? norm_q : selected_metrics[0][METRIC_W-1];
    (* ram_style = "block" *) reg [31:0] survivor_lo [0:1023];
    (* ram_style = "block" *) reg [31:0] survivor_hi [0:1023];






    reg [63:0] decoded [0:7];
    reg[63:0]decoded_b1[0:1];




    wire start_trace = initialized[context_id] && phase && (accepted[context_id] >= 127) &&
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

        if(use_costs)begin
         bm00=active_costs[0+:9];bm01=active_costs[9+:9];
         bm10=active_costs[18+:9];bm11=active_costs[27+:9];
        end
        for (i = 0; i < 32; i = i + 1) begin
            // phase 0 produces states 0..31 and phase 1 states 32..63.
            // Each destination state[context_id] has predecessors state[context_id]>>1 and +32.
            p0_state = (phase ? 16 : 0) + (i >> 1);
            p1_state = p0_state + 32;
            src0 = selected_metrics[i >> 1];
            src1 = phase ? selected_metrics[48 + (i >> 1)] : selected_metrics[32 + (i >> 1)];

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

    reg pending_hi_valid;
    reg [1:0] pending_hi_context;
    always @(posedge clk or negedge resetn)begin
        if(!resetn)begin pending_hi_valid<=0;pending_hi_context<=0;end
        else begin
            pending_hi_valid<=tick && ((!initialized[context_id] && init_phase) ||
                                      (initialized[context_id] && phase));
            if(tick)pending_hi_context<=context_id;
        end
    end
    generate for(genvar bank_lane=0;bank_lane<16;bank_lane=bank_lane+1)begin : g_paired_metric
        (* ram_style = "distributed" *) reg [METRIC_W-1:0] lo_bank[0:7];
        (* ram_style = "distributed" *) reg [METRIC_W-1:0] hi_bank[0:7];
        reg [METRIC_W-1:0] pending_lo,pending_hi;
        wire [METRIC_W-1:0] lo_read=lo_bank[{context_id,slot_active}];
        wire [METRIC_W-1:0] hi_read=hi_bank[{context_id,slot_active}];
        assign selected_metrics[bank_lane]=lo_read;
        assign selected_metrics[16+bank_lane]=lo_read;
        assign selected_metrics[32+bank_lane]=hi_read;
        assign selected_metrics[48+bank_lane]=hi_read;
        for(genvar ct=0;ct<4;ct=ct+1)begin : g_tap
            assign metrics[64*ct+bank_lane]=lo_bank[2*ct];
            assign metrics[64*ct+16+bank_lane]=lo_bank[2*ct+1];
            assign metrics[64*ct+32+bank_lane]=hi_bank[2*ct];
            assign metrics[64*ct+48+bank_lane]=pending_hi_valid && pending_hi_context==ct
                ? pending_hi : hi_bank[2*ct+1];
        end
        always @(posedge clk)begin
            if(tick && ((!initialized[context_id] && !init_phase) ||
                        (step_enable && !phase)))begin
                pending_lo<=initialized[context_id] ? lane_metric[16+bank_lane] : 13'd0;
                lo_bank[{context_id,1'b0}]<=initialized[context_id] ? lane_metric[bank_lane] : 13'd0;
            end else if(tick && ((!initialized[context_id] && init_phase) ||
                                (initialized[context_id] && phase)))
                lo_bank[{context_id,1'b1}]<=pending_lo;
            // Upper group 48..63 retires one global clock later. No added slot.
            if(pending_hi_valid)hi_bank[{pending_hi_context,1'b1}]<=pending_hi;
            else if(tick && ((!initialized[context_id] && init_phase) ||
                            (initialized[context_id] && phase)))
                hi_bank[{context_id,1'b0}]<=initialized[context_id] ? lane_metric[bank_lane] : 13'd0;
            if(tick && ((!initialized[context_id] && init_phase) ||
                        (initialized[context_id] && phase)))
                pending_hi<=initialized[context_id] ? lane_metric[16+bank_lane] : 13'd0;
        end
    end endgenerate

    always @(posedge clk) begin
        if (tick) begin

        survivor_pipe[context_id] <= current_survivor_q;
        if (tick && initialized[context_id] && phase) begin
            survivor_lo[{context_id, wr_ptr[context_id]}] <= decision_partial;
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
            for(reset_context=0;reset_context<4;reset_context=reset_context+1)begin
            phase <= 0; initialized[reset_context] <= 0; init_phase <= 0;
            soft0_q <= 0; soft1_q <= 0;tc8_q<=0;costs_q<=0;b1_q<=0; erasure_q<=0; decision_partial <= 0;
            wr_ptr[reset_context] <= 0; accepted[reset_context] <= 0; norm_q <= 0;
            read_ptr[reset_context] <= 0; walk[reset_context] <= 0; state[reset_context] <= 0;
            prime_extra[reset_context] <= 0;
            tracing[reset_context] <= 0; priming[reset_context] <= 0; decoded_write[reset_context] <= 0;
            decoded_read[reset_context] <= 0; decoded_ready[reset_context] <= 0; output_pos[reset_context] <= 0; output_tick[reset_context] <= 0;
            out_valid <= 0; out_bit <= 0;out_b1<=0;
            end
        end else begin
            out_valid <= 0;
            if (tick) begin
            out_context <= context_id;
            output_tick[context_id] <= ~output_tick[context_id];
            if (!initialized[context_id]) begin
                init_phase <= ~init_phase;
                if (init_phase) initialized[context_id] <= 1;
            end else if (step_enable) begin
                if (!phase) begin
                    soft0_q <= soft0; soft1_q <= soft1;tc8_q<=in_tc8;costs_q<=costs;b1_q<=b1_choice; erasure_q<=erasure;
                    decision_partial <= lane_decision;
                    norm_q <= selected_metrics[0][METRIC_W-1];
                    phase <= 1;
                end else begin
                    phase <= 0;
                    wr_ptr[context_id] <= wr_ptr[context_id] + 1;
                    if (accepted[context_id] < 128) accepted[context_id] <= accepted[context_id] + 1;
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
                out_b1<=context_id==3 ? decoded_b1[decoded_read[3]][0] : 1'b0;
                
                output_pos[context_id] <= output_pos[context_id] + 1;
                if (output_pos[context_id] == 63) begin
                    decoded_read[context_id] <= ~decoded_read[context_id];
                    decoded_ready[context_id][decoded_read[context_id]] <= 0;
                end
            end
            end
        end
    end
    // Match the survivor RAM's tagged forwarding/retention latency. Only S
    // uses this history, and T ticks must never advance S's read pipeline.
    (* ram_style="block" *) reg[3:0]branch_history[0:255];
    reg[3:0]b1_ram,b1_saved,b1_pipe;reg b1_ram_valid;
    wire s_tick=tick && context_id==3;
    wire[3:0]current_b1=b1_ram_valid ? b1_ram : b1_saved;
    wire[1:0]traceback_xy=encode_pair({decision,state[3][5:1]},state[3][0]);
    always @(posedge clk)begin
     if(s_tick)b1_ram<=branch_history[read_ptr[3]];
     if(b1_ram_valid)b1_saved<=b1_ram;
     if(s_tick)b1_pipe<=current_b1;
     if(s_tick && initialized[3] && phase && tc8_q)
      branch_history[wr_ptr[3]]<=b1_q;
    end
    always @(posedge clk or negedge resetn)
     if(!resetn)b1_ram_valid<=0;else b1_ram_valid<=s_tick;
    generate for(genvar b1_bank=0;b1_bank<2;b1_bank=b1_bank+1)begin: g_uncoded_output
     always @(posedge clk)begin
      if(s_tick && tracing[3] && walk[3]>=60 && decoded_write[3]==b1_bank)
       decoded_b1[b1_bank]<={decoded_b1[b1_bank][62:0],b1_pipe[traceback_xy]};
      if(s_tick && decoded_ready[3][decoded_read[3]] && output_tick[3] && decoded_read[3]==b1_bank)
       decoded_b1[b1_bank]<={1'b0,decoded_b1[b1_bank][63:1]};
     end
    end endgenerate
    generate for(genvar bank_id=0;bank_id<8;bank_id=bank_id+1)begin : g_output_bank
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
