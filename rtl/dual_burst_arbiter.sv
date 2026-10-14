// Two-client burst round-robin. One response slot per client isolates stalled
// consumers. Forward immediately when the controller accepts; otherwise latch
// the selected payload. Response completion may launch the OTHER client on the
// same edge. The retiring owner is excluded until its response slot is drained.
module dual_burst_arbiter(input wire clk,resetn,
 input wire[1:0] req_valid,output wire[1:0] req_ready,input wire[1:0] req_write,
 input wire[41:0] req_address,input wire[511:0] req_data,
 output reg[1:0] rsp_valid,input wire[1:0] rsp_ready,output reg[511:0] rsp_data,
 output wire mv,input wire mr,output wire mw,output wire[20:0] ma,output wire[255:0] md,
 input wire rv,output wire rr,input wire[255:0] rd);
 reg[1:0] state;reg last,owner;
 reg hold_write;reg[20:0] hold_address;reg[255:0] hold_data;
 wire selecting=state==0||(state==2&&rv);
 wire[1:0] retiring=state==2 ? (owner?2'b10:2'b01) : 2'b00;
 wire[1:0] eligible=req_valid&(~rsp_valid|rsp_ready)&~retiring;
 wire choice=eligible[!last]?!last:last;
 assign req_ready=selecting&&|eligible ? (choice?2'b10:2'b01) : 2'b00;
 assign mv=state==1||(selecting&&|eligible);assign rr=state==2;
 assign mw=selecting?req_write[choice]:hold_write;
 assign ma=selecting?req_address[choice*21+:21]:hold_address;
 assign md=selecting?req_data[choice*256+:256]:hold_data;
 always @(posedge clk)begin
  if(!resetn)begin
   state<=0;last<=1;owner<=0;hold_write<=0;hold_address<=0;hold_data<=0;rsp_valid<=0;rsp_data<=0;
  end else begin
   rsp_valid<=rsp_valid&~rsp_ready;
   if(state==1&&mr)state<=2;
   if(state==2&&rv)begin rsp_data[owner*256+:256]<=rd;rsp_valid[owner]<=1;state<=0;end
   if(selecting&&|eligible)begin
    owner<=choice;last<=choice;hold_write<=req_write[choice];
    hold_address<=req_address[choice*21+:21];hold_data<=req_data[choice*256+:256];
    state<=mr?2:1;
   end
  end
 end
endmodule
