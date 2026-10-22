// EXPERIMENT: per-client circular precedence masks and factored overrides.
// TTI-only bounded two-cycle grace before abandoning an idle lease.
// EXPERIMENT: accept selected request directly in SELECT; lock if stalled.
// EXPERIMENT: up to 128 background grants per lease; FFT remains priority.
// A missing requester ends its lease. Not a starvation or deadline proof.
// Single outstanding SDRAM transaction. Client 5 (FFT) has priority at each
// selection; clients 0..4 use round robin. No starvation bound is claimed.
// Sources must hold valid/address/data/mask until ready. Selection is locked
// before presenting a request, and ownership persists until response consumption.
// Payload storage remains in each producer and dual_sdram_burst, not duplicated.
module sdram_client_arbiter_metadata(
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
 reg [4:0] lease; reg [6:0] remaining;
 reg [1:0] grace;
 wire wait_tile=remaining!=0 && lease==5'b00100 && !client_valid[2];
 reg [24:0] predecessors;
 wire [4:0] rr_first;
 wire lease_active = remaining!=0 && |(lease & client_valid[4:0]);
 wire background_allowed = !client_valid[5] && !(wait_tile && grace<2);
 wire use_round_robin = background_allowed && !lease_active;
 wire use_lease = background_allowed && lease_active;
 genvar g;
 generate for(g=0;g<5;g=g+1)begin: circular_priority
  assign rr_first[g]=client_valid[g] && !(|(client_valid[4:0] & predecessors[g*5+:5]));
 end endgenerate
 wire [5:0] selected = state==SELECT ? chosen : owner;
 integer k;
 always @* begin
  // State-only masks; all candidate valid tests run in parallel.
  case(rr)
   0:predecessors=25'b0111100111000110000100000;
   1:predecessors=25'b0111000110000100000011110;
   2:predecessors=25'b0110000100000001110111100;
   3:predecessors=25'b0100000000110111100111000;
   4:predecessors=25'b0000010111100111000110000;
   default:predecessors=25'b0111100111000110000100000;
  endcase
  chosen[4:0]=({5{use_lease}} & lease) | ({5{use_round_robin}} & rr_first);
  chosen[5]=client_valid[5];
  req_write=0;req_address=0;req_data=0;req_dqm=0;
  for(k=0;k<6;k=k+1)begin
   req_write=req_write | (selected[k] & client_write[k]);
   req_address=req_address | ({21{selected[k]}} & client_address[k*21+:21]);
   req_data=req_data | ({256{selected[k]}} & client_data[k*256+:256]);
   req_dqm=req_dqm | ({32{selected[k]}} & client_dqm[k*32+:32]);
  end
 end
 assign req_valid=resetn && (state==SELECT || state==ISSUE) && |(selected & client_valid);
 assign client_ready=selected & {6{resetn && (state==SELECT || state==ISSUE) && req_ready}};
 assign client_rsp_valid=owner & {6{resetn && state==RESPONSE && rsp_valid}};
 assign rsp_ready=resetn && state==RESPONSE && |(owner & client_rsp_ready);
 assign client_rsp_data=rsp_data;
 always @(posedge clk)begin
  if(!resetn)begin state<=SELECT;owner<=0;rr<=0;lease<=0;remaining<=0;grace<=0;end
  else begin
   if(state==SELECT && wait_tile && !client_valid[5])begin
    if(grace<2)grace<=grace+1'b1;
   end else grace<=0;
   case(state)
    SELECT:if(|chosen)begin owner<=chosen;state<=req_ready?RESPONSE:ISSUE;end
    ISSUE:if(req_valid && req_ready)state<=RESPONSE;
    RESPONSE:if(rsp_valid && rsp_ready)begin state<=SELECT;owner<=0;end
   endcase
   if(req_valid && req_ready)begin
    if(!selected[5])begin
     if(remaining!=0 && selected[4:0]==lease)remaining<=remaining-1'b1;
     else begin lease<=selected[4:0];remaining<=127;end
    end
    if(selected[0])rr<=1;
    if(selected[1])rr<=2;
    if(selected[2])rr<=3;
    if(selected[3])rr<=4;
    if(selected[4])rr<=0;
   end
  end
 end
endmodule
