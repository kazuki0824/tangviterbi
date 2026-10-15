// One actual upstream symbol buffer plus the time DMA's in-place symbol RAM.
// Commit on final capture; reuse only after the child accepts the final word.
// drain_only queues a final drain after all buffered input has been consumed.
module dual_t_buffered_time_dma #(
 parameter integer MODE=1,S0=3,I0=4,S1=3,I1=8,S2=7,I2=16,
 parameter [22:0] BASE=0
)(input wire clk,resetn,
 input wire start_valid,output wire start_ready,input wire drain_only,
 input wire in_valid,output wire in_ready,input wire[31:0] in_data,
 output wire out_valid,input wire out_ready,output wire[31:0] out_data,
 output wire out_last,out_settled,result_ready,symbol_done,busy,fault,
 output wire req_valid,input wire req_ready,output wire req_write,
 output wire[20:0] req_address,output wire[255:0] req_data,output wire[31:0] req_dqm,
 input wire rsp_valid,output wire rsp_ready,input wire[255:0] rsp_data);
 localparam WORDS=13*96*(1<<(MODE-1))*6/4,AW=$clog2(WORDS);
 localparam EMPTY=0,FILL=1,FULL=2,SEND=3;
 reg[1:0] state;reg flush,draining;
 reg[AW-1:0] write_pos;reg[AW:0] read_pos;
 (* ram_style="block" *) reg[31:0] ram[0:WORDS-1];
 reg[31:0] data_q;reg valid_q,last_q;
 wire child_ready,child_in_ready,child_busy;
 wire launch=state==FULL||flush;
 wire fetch=state==SEND&&read_pos<WORDS&&(!valid_q||child_in_ready);
 wire consumed=state==SEND&&valid_q&&child_in_ready;
 assign start_ready=state==EMPTY&&!flush&&(!draining||symbol_done);
 assign in_ready=state==FILL;
 assign busy=state!=EMPTY||flush||(draining&&!symbol_done)||child_busy;
 always @(posedge clk)begin
  if(in_valid&&in_ready)ram[write_pos]<=in_data;
  if(fetch)data_q<=ram[read_pos[AW-1:0]];
 end
 always @(posedge clk)begin
  if(!resetn)begin state<=EMPTY;flush<=0;draining<=0;write_pos<=0;read_pos<=0;valid_q<=0;last_q<=0;end
  else begin
   if(draining&&symbol_done)draining<=0;
   if(start_valid&&start_ready)begin
    if(drain_only)flush<=1;
    else begin state<=FILL;write_pos<=0;end
   end
   if(in_valid&&in_ready)begin
    if(write_pos==WORDS-1)state<=FULL;
    else write_pos<=write_pos+1'b1;
   end
   if(launch&&child_ready)begin
    if(flush)begin flush<=0;draining<=1;end
    else begin state<=SEND;read_pos<=0;valid_q<=0;end
   end
   if(consumed)begin
    valid_q<=0;
    if(last_q)state<=EMPTY;
   end
   if(fetch)begin
    valid_q<=1;last_q<=read_pos==WORDS-1;read_pos<=read_pos+1'b1;
   end
  end
 end
 dual_t_time_dma #(.MODE(MODE),.S0(S0),.I0(I0),.S1(S1),.I1(I1),.S2(S2),.I2(I2),.BASE(BASE)) time_dma(
  clk,resetn,launch,child_ready,flush,state==SEND&&valid_q,child_in_ready,data_q,
  out_valid,out_ready,out_data,out_last,out_settled,result_ready,symbol_done,child_busy,fault,
  req_valid,req_ready,req_write,req_address,req_data,req_dqm,rsp_valid,rsp_ready,rsp_data);
endmodule
