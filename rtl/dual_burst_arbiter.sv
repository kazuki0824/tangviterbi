// Two clients, one response slot each. The selected source is locked while the
// downstream stalls; its standard valid/ready contract holds the payload.
// Upstream ready is asserted only on actual downstream acceptance. This avoids
// a redundant 310-bit payload register and mux in each arbitration layer.
// A completed response may issue the next request on the same clock. Full
// response slots backpressure the controller without overwriting older data.
module dual_burst_arbiter #(parameter PRIORITY_SECOND=0,DIRECT_RESPONSE=0)(input wire clk,resetn,
 input wire[1:0] req_valid,output wire[1:0] req_ready,input wire[1:0] req_write,
 input wire[41:0] req_address,input wire[511:0] req_data,
 output reg[1:0] rsp_valid,input wire[1:0] rsp_ready,output reg[511:0] rsp_data,
 output wire mv,input wire mr,output wire mw,output wire[20:0] ma,output wire[255:0] md,
 input wire rv,output wire rr,input wire[255:0] rd,
 input wire[63:0] req_dqm,output wire[31:0] mdqm);
 reg[1:0] state;reg last,owner;
 wire selecting=state==0||(state==2&&rv&&rr);
 wire[1:0] eligible=req_valid&(DIRECT_RESPONSE ? 2'b11 : (~rsp_valid|rsp_ready));
 wire choice=state==1 ? owner : (PRIORITY_SECOND ? eligible[1] : (eligible[!last]?!last:last));
 assign mv=state==1||(selecting&&|eligible);
 assign req_ready=mv&&mr ? (choice?2'b10:2'b01) : 2'b00;
 assign rr=state==2&&(DIRECT_RESPONSE ? rsp_ready[owner] : (!rsp_valid[owner]||rsp_ready[owner]));
 assign mw=req_write[choice];assign ma=req_address[choice*21+:21];
 assign md=req_data[choice*256+:256];assign mdqm=req_dqm[choice*32+:32];
 always @(posedge clk)begin
  if(!resetn)begin state<=0;last<=1;owner<=0;end
  else begin
   if(state==2&&rv&&rr)state<=0;
   if(mv)begin
    owner<=choice;
    if(mr)begin last<=choice;state<=2;end
    else state<=1;
   end
  end
 end
 // A cascaded background arbiter can use the downstream response slot directly.
 // Backpressure then blocks the whole background port; its consumers must meet
 // the declared service contract. No duplicated per-client payload registers.
 generate if(DIRECT_RESPONSE)begin:direct_response
  always @* begin
   rsp_valid=state==2&&rv ? (owner?2'b10:2'b01) : 2'b00;
   rsp_data={rd,rd};
  end
 end else begin:buffered_response
  always @(posedge clk)begin
   if(!resetn)begin rsp_valid<=0;rsp_data<=0;end
   else begin
    rsp_valid<=rsp_valid&~rsp_ready;
    if(state==2&&rv&&rr)begin rsp_data[owner*256+:256]<=rd;rsp_valid[owner]<=1;end
   end
  end
 end endgenerate
endmodule
