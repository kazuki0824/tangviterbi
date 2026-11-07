// Conservative one-line outer-delay adapter. Reserve a whole BL8 line before
// admitting samples; drain the last scheduled write before writeback/refill.
// No PHY, background arbitration, or throughput guarantee is implied.
module sdf_delay_cache(
 input wire clk,resetn,input wire sample_accept,output wire external_ready,
 input wire read_enable,input wire [11:0] read_address,output reg [31:0] read_data,
 input wire write_enable,input wire [11:0] write_address,input wire [31:0] write_data,
 output wire req_valid,input wire req_ready,output wire req_write,
 output wire [20:0] req_address,output wire [255:0] req_data,
 input wire rsp_valid,input wire [255:0] rsp_data,output reg fault
);
 localparam FETCH=0,FETCH_WAIT=1,ACTIVE=2,DRAIN=3,STORE=4,STORE_WAIT=5;
 reg [2:0] state;reg [8:0] line_address;
 reg [3:0] accepted;reg [255:0] line_data;
 assign external_ready=state==ACTIVE && accepted<8 && !fault;
 assign req_valid=state==FETCH || state==STORE;
 assign req_write=state==STORE;
 assign req_address={9'd0,line_address,3'b000};
 assign req_data=line_data;
 integer word_index;
 always @(posedge clk)begin
  if(!resetn)begin state<=FETCH;line_address<=0;accepted<=0;fault<=0;read_data<=0;end
  else begin
   case(state)
    FETCH:if(req_ready)state<=FETCH_WAIT;
    FETCH_WAIT:if(rsp_valid)begin line_data<=rsp_data;accepted<=0;state<=ACTIVE;end
    ACTIVE:if(sample_accept)begin
     accepted<=accepted+1'b1;
     if(accepted==7)state<=DRAIN;
    end
    STORE:if(req_ready)state<=STORE_WAIT;
    STORE_WAIT:if(rsp_valid)begin line_address<=line_address+1'b1;state<=FETCH;end
   endcase
   if(sample_accept && !external_ready)fault<=1;
   if(read_enable)begin
    if(read_address[11:3]!=line_address || (state!=ACTIVE && state!=DRAIN))fault<=1;
    read_data<=line_data[read_address[2:0]*32+:32];
   end
   if(write_enable)begin
    if(write_address[11:3]!=line_address || (state!=ACTIVE && state!=DRAIN))fault<=1;
    for(word_index=0;word_index<8;word_index=word_index+1)
     if(write_address[2:0]==word_index)line_data[word_index*32+:32]<=write_data;
    if(write_address[2:0]==7)begin
     if(state!=DRAIN)fault<=1;
     state<=STORE;
    end
   end
  end
 end
endmodule
