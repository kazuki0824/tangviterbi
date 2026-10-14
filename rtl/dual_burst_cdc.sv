// Single outstanding bundled-data mailbox. Payload is held from request until
// response consumption; response held until next request. Toggle controls use
// two synchronizers. Both domains must be reset together while quiescent.
// Simulation validates the protocol, not metastability/physical CDC constraints.
module dual_burst_cdc(
 input wire aclk,bclk,resetn,
 input wire av,output wire ar,input wire aw,input wire[20:0] aa,
 input wire[255:0] ad,output wire arv,input wire arr,output reg[255:0] ard,
 output wire bv,input wire br,output wire bw,output wire[20:0] ba,
 output wire[255:0] bd,input wire brv,output wire brr,input wire[255:0] brd,
 input wire[31:0] a_dqm,output wire[31:0] b_dqm);
 reg request,response;reg outstanding;reg[309:0] payload;reg[255:0] result;
 (* async_reg="true" *) reg rq1,rq2,rs1,rs2;
 reg[1:0] state;reg seen;reg valid;
 assign ar=!outstanding;assign arv=valid;
 assign bv=state==1;assign {bw,ba,bd,b_dqm}=payload;assign brr=state==2;
 always @(posedge aclk or negedge resetn)begin
  if(!resetn)begin request<=0;outstanding<=0;payload<=0;rs1<=0;rs2<=0;valid<=0;ard<=0;end
  else begin
   rs1<=response;rs2<=rs1;
   if(av&&ar)begin payload<={aw,aa,ad,a_dqm};request<=!request;outstanding<=1;end
   if(outstanding&&rs2==request&&!valid)begin ard<=result;valid<=1;end
   if(valid&&arr)begin valid<=0;outstanding<=0;end
  end
 end
 always @(posedge bclk or negedge resetn)begin
  if(!resetn)begin rq1<=0;rq2<=0;response<=0;seen<=0;state<=0;result<=0;end
  else begin
   rq1<=request;rq2<=rq1;
   case(state)
    0:if(rq2!=seen)begin seen<=rq2;state<=1;end
    1:if(br)state<=2;
    2:if(brv)begin result<=brd;response<=seen;state<=0;end
   endcase
  end
 end
endmodule
