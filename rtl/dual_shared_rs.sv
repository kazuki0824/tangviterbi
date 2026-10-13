// Three non-preemptive outer-code streams: 0=T, 1=S, 2=S TMCC.
// Compile with experiments.s3_rs_isdb.source(True, True), NOT the historical
// rtl/rs204_188_compact.sv benchmark (different field/code conventions).
// pending promises a complete 204/204/64-byte word at the source. Once granted,
// bytes must be supplied without gaps whenever source_ready is asserted.
// credit promises 188/188/48 free output bytes, reserved on grant. This module
// cannot stall the decoder output. Queues, SDRAM DMA and TS serialization are
// external and MUST implement these contracts. Reset aborts the current word.
module dual_shared_rs #(
    parameter integer SLOT_CYCLES = 2672
)(
    input wire clk, resetn,
    input wire [2:0] pending, credit,
    input wire [23:0] source_bytes,
    output reg [2:0] source_ready,
    output reg [2:0] grant,
    output wire out_valid, out_first, out_last, out_fail,
    output wire [1:0] out_source,
    output wire [7:0] out_byte
);
    localparam IDLE=0, FEED=1, DRAIN=2, RECOVER=3;
    reg [1:0] state, selected, next_source;
    reg [7:0] input_index, output_index;
    reg [$clog2(SLOT_CYCLES+1)-1:0] cooldown;
    reg [1:0] choice;
    reg found;
    integer i, candidate;
    wire rs_ready, rs_valid, rs_fail;
    wire [7:0] rs_byte;
    wire prefix = selected == 2 && input_index < 140;
    wire [7:0] input_byte = prefix ? 8'd0 :
        selected == 0 ? source_bytes[7:0] :
        selected == 1 ? source_bytes[15:8] : source_bytes[23:16];
    rs204_188_compact decoder(clk,resetn,state==FEED,rs_ready,input_byte,
                             rs_valid,rs_byte,rs_fail);
    always @* begin
        found=0; choice=0;
        for(i=0;i<3;i=i+1) begin
            candidate=next_source+i;
            if(candidate>=3) candidate=candidate-3;
            if(!found && pending[candidate] && credit[candidate]) begin
                found=1; choice=candidate;
            end
        end
        source_ready=0;
        if(state==FEED && !prefix) source_ready[selected]=rs_ready;
    end
    assign out_valid=state==DRAIN && rs_valid &&
                     (selected!=2 || output_index>=140);
    assign out_first=out_valid && output_index==(selected==2 ? 140 : 0);
    assign out_last=out_valid && output_index==187;
    assign out_source=selected;
    assign out_byte=rs_byte;
    assign out_fail=rs_fail;
    always @(posedge clk) begin
        if(!resetn) begin
            state<=IDLE; selected<=0; next_source<=0;
            input_index<=0; output_index<=0; cooldown<=0; grant<=0;
        end else begin
            grant<=0;
            if(cooldown!=0) cooldown<=cooldown-1'b1;
            case(state)
                IDLE: if(found && rs_ready && cooldown==0) begin
                    selected<=choice; next_source<=choice==2 ? 0 : choice+1'b1;
                    grant[choice]<=1; state<=FEED;
                    input_index<=0; output_index<=0;
                    cooldown<=SLOT_CYCLES-1;
                end
                FEED: if(rs_ready) begin
                    input_index<=input_index+1'b1;
                    if(input_index==203) state<=DRAIN;
                end
                DRAIN: if(rs_valid) begin
                    output_index<=output_index+1'b1;
                    if(output_index==187) state<=RECOVER;
                end
                RECOVER: if(rs_ready) state<=IDLE;
            endcase
        end
    end
endmodule
