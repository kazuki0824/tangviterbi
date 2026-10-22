// EXPERIMENT: up to 32 background grants per lease; FFT remains priority.
// A missing requester ends its lease. Not a starvation or deadline proof.
// Single outstanding SDRAM transaction. Client 5 (FFT) has priority at each
// selection; clients 0..4 use round robin. No starvation bound is claimed.
// Sources must hold valid/address/data/mask until ready. Selection is locked
// before presenting a request, and ownership persists until response consumption.
// Payload storage remains in each producer and dual_sdram_burst, not duplicated.
module sdram_client_arbiter(
 input wire clk,resetn,
 input wire [5:0] client_valid,output wire [5:0] client_ready,
 input wire [5:0] client_write,input wire [125:0] client_address,
 input wire [1535:0] client_data,input wire [191:0] client_dqm,
 output wire [5:0] client_rsp_valid,input wire [5:0] client_rsp_ready,
 output wire [255:0] client_rsp_data,
 output wire req_valid,input wire req_ready,output reg req_write,
 output reg [20:0] req_address,output reg [255:0] req_data,
 output reg [31:0] req_dqm,input wire rsp_valid,output wire rsp_ready,
 input wire [255:0] rsp_data
);
 localparam SELECT=0,ISSUE=1,RESPONSE=2;
 reg [1:0] state;
 reg [5:0] owner;
 // Keep the circular cursor binary: FSM recoding leaves a $buf in this toolchain.
 (* fsm_encoding="none" *) reg [2:0] rr;
 reg [5:0] chosen;
 reg [4:0] lease; reg [4:0] remaining;
 reg [4:0] priority_mask,eligible;
 integer k;
 always @* begin
  // Two fixed priority encoders avoid variable index/add/modulo chains.
  case(rr)
   0:priority_mask=5'b11111;
   1:priority_mask=5'b11110;
   2:priority_mask=5'b11100;
   3:priority_mask=5'b11000;
   4:priority_mask=5'b10000;
   default:priority_mask=5'b11111;
  endcase
  eligible=client_valid[4:0]&priority_mask;
  if(eligible==0)eligible=client_valid[4:0];
  chosen=0;
  if(eligible[0])chosen[0]=1;
  else if(eligible[1])chosen[1]=1;
  else if(eligible[2])chosen[2]=1;
  else if(eligible[3])chosen[3]=1;
  else if(eligible[4])chosen[4]=1;
  if(remaining!=0 && |(lease & client_valid[4:0]))chosen={1'b0,lease};
  if(client_valid[5])chosen=6'b100000;
  req_write=0;req_address=0;req_data=0;req_dqm=0;
  for(k=0;k<6;k=k+1)begin
   req_write=req_write | (owner[k] & client_write[k]);
   req_address=req_address | ({21{owner[k]}} & client_address[k*21+:21]);
   req_data=req_data | ({256{owner[k]}} & client_data[k*256+:256]);
   req_dqm=req_dqm | ({32{owner[k]}} & client_dqm[k*32+:32]);
  end
 end
 assign req_valid=resetn && state==ISSUE && |(owner & client_valid);
 assign client_ready=owner & {6{resetn && state==ISSUE && req_ready}};
 assign client_rsp_valid=owner & {6{resetn && state==RESPONSE && rsp_valid}};
 assign rsp_ready=resetn && state==RESPONSE && |(owner & client_rsp_ready);
 assign client_rsp_data=rsp_data;
 always @(posedge clk)begin
  if(!resetn)begin state<=SELECT;owner<=0;rr<=0;lease<=0;remaining<=0;end
  else case(state)
   SELECT:if(|chosen)begin owner<=chosen;state<=ISSUE;end
   ISSUE:if(req_valid && req_ready)begin
    state<=RESPONSE;
    // FFT does not consume or reset a background lease.
    if(!owner[5])begin
     if(remaining!=0 && owner[4:0]==lease)remaining<=remaining-1'b1;
     else begin lease<=owner[4:0];remaining<=31;end
    end
    // Cursor advances as usual; lease temporarily overrides it.
    if(owner[0])rr<=1;
    if(owner[1])rr<=2;
    if(owner[2])rr<=3;
    if(owner[3])rr<=4;
    if(owner[4])rr<=0;
   end
   RESPONSE:if(rsp_valid && rsp_ready)begin state<=SELECT;owner<=0;end
  endcase
 end
endmodule
