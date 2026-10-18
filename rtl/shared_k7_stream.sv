// Four lossless, same-clock input queues followed by the shared K7 core.
// The upstream producer MUST retain a word while valid && !ready.
// This interface is internal to the FPGA, not an FPGA -> SoC data path.
module shared_k7_stream #(parameter WEIGHTED = 1) (
    input wire clk, input wire resetn,
    input wire in_valid, output wire in_ready,
    input wire [1:0] in_context,
    input wire [7:0] soft0, soft1,
    input wire [1:0] erasure,
    output wire out_valid, out_bit,
    output wire [1:0] out_context
);
    wire [3:0] nonempty, full;
    wire [17:0] heads [0:3];
    reg [1:0] rr, idle_rr, boot_context;
    reg [1:0] share_phase;
    reg boot;
    reg [6:0] service_count;
    reg [1:0] selected;
    reg found;
    integer offset;
    reg [2:0] candidate;
    wire core_ready, core_input_ready;
    wire data_slot;
    reg prepare, grant_valid, grant_data;
    reg [1:0] grant_context;
    reg [17:0] grant_word;
    // Prepare the next grant during the current core slot's second cycle.
    // This register breaks arbitration/FIFO -> ACS combinational paths.
    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            prepare<=1; grant_valid<=0; grant_data<=0;
            grant_context<=0; grant_word<=0;
        end else begin
            prepare<=!prepare;
            if (prepare) begin
                grant_valid<=1; grant_data<=data_slot;
                grant_context<=selected; grant_word<=heads[selected];
            end
        end
    end
    wire maintenance = service_count == 127;
    always @* begin
        selected = idle_rr;
        found = 0;
        candidate = 0;
        for (offset=0; offset<4; offset=offset+1) begin
            candidate = (rr + offset) % 4;
            if (!found && nonempty[candidate]) begin
                selected = candidate;
                found = 1;
            end
        end
        // Two nominal slots for S, then one for the three T contexts.
        // Empty classes donate their slot; maintenance freezes this phase.
        if (WEIGHTED) begin
            found = 0;
            selected = idle_rr;
            for (offset=0; offset<3; offset=offset+1) begin
                candidate = rr + offset;
                if (candidate >= 3) candidate = candidate - 3;
                if (!found && nonempty[candidate]) begin selected=candidate; found=1; end
            end
            if (nonempty[3] && (share_phase != 2 || !found)) begin selected=3; found=1; end
        end
        if (maintenance) selected = idle_rr;
        if (boot) selected = boot_context;
    end
    assign data_slot = !boot && !maintenance && found;
    wire pop = resetn && prepare && data_slot;
    // No combinational ready dependency on the consumer: full queues take
    // one cycle to advertise the space freed by a simultaneous pop.
    assign in_ready = resetn && !full[in_context];
    wire push = in_valid && in_ready;
    generate for (genvar c=0;c<4;c=c+1) begin : g_fifo
        (* ram_style = "distributed" *) reg [17:0] words [0:15];
        reg [3:0] wr_ptr, rd_ptr;
        reg [4:0] count;
        wire put = push && in_context == c;
        wire take = pop && selected == c;
        assign nonempty[c] = count != 0;
        assign full[c] = count == 16;
        assign heads[c] = words[rd_ptr];
        always @(posedge clk) if (put) words[wr_ptr] <= {soft0,soft1,erasure};
        always @(posedge clk or negedge resetn) begin
            if (!resetn) begin wr_ptr<=0; rd_ptr<=0; count<=0; end
            else begin
                if (put) wr_ptr<=wr_ptr+1'b1;
                if (take) rd_ptr<=rd_ptr+1'b1;
                case ({put,take})
                    2'b10: count<=count+1'b1;
                    2'b01: count<=count-1'b1;
                    default: ;
                endcase
            end
        end
    end endgenerate
    always @(posedge clk or negedge resetn) begin
        if (!resetn) begin
            rr<=0; idle_rr<=0; boot_context<=0; boot<=1; service_count<=0; share_phase<=0;
        end else if (prepare) begin
            if (boot) begin
                boot_context<=boot_context+1'b1;
                if (boot_context==3) boot<=0;
            end else begin
                service_count<=service_count+1'b1;
                if (data_slot) begin
                    if (WEIGHTED) begin
                        share_phase <= share_phase==2 ? 0 : share_phase+1'b1;
                        if (selected!=3) rr <= selected==2 ? 0 : selected+1'b1;
                    end else rr<=selected+1'b1;
                end
                else idle_rr<=idle_rr+1'b1;
            end
        end
    end
    wire [17:0] word = grant_word;
    shared_k7_context core (
        .clk(clk), .resetn(resetn), .slot_valid(grant_valid),
        .slot_ready(core_ready), .slot_context(grant_context),
        .out_context(out_context), .in_valid(grant_data),
        .in_ready(core_input_ready), .soft0(word[17:10]),
        .soft1(word[9:2]), .erasure(word[1:0]),
        .out_valid(out_valid), .out_bit(out_bit)
    );
endmodule
