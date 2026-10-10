// Metadata for one stream's external-memory page ring (4096 B/page).
// Two SPI ports may own different pages concurrently and finish in either
// order. finish[] is NOT wire end-of-page: it may be asserted only after ALL
// page writes are acknowledged by the memory backend and framing is valid.
// Payload memory/PHY is outside this module. The ordered consumer retires a
// page only after its final memory read/consumption, never on read issuance.
// epoch is constant until both ports, memory and consumer are stopped/reset.
module s3_page_reorder #(
 parameter SLOT_BITS=4,
 parameter [19:0] RESET_SEQUENCE=0
)(
 input wire clk,resetn,input wire [15:0] epoch,
 input wire [1:0] request,output wire [1:0] grant,
 input wire [31:0] offset0,offset1,
 input wire [15:0] epoch0,epoch1,
 output wire [SLOT_BITS-1:0] slot0,slot1,
 input wire [1:0] finish,input wire abort,
 output wire page_valid,output wire [31:0] page_offset,
 output wire [SLOT_BITS-1:0] page_slot,input wire retire,
 output reg [1:0] active,output reg fault
);
 localparam SLOTS=1<<SLOT_BITS;
 initial if(SLOT_BITS<1 || SLOT_BITS>10) $fatal(1,"invalid page ring size");
 reg [SLOTS-1:0] occupied,complete;
 reg [19:0] next_sequence;
 reg [SLOT_BITS-1:0] owned0,owned1;
 wire [19:0] sequence0=offset0[31:12],sequence1=offset1[31:12];
 wire [19:0] delta0=sequence0-next_sequence,delta1=sequence1-next_sequence;
 // The 20-bit subtraction must not share a cycle with arbitration and FIFO
 // backpressure. Cache only the arithmetic, never ownership. Invalidate a
 // cached result on a new request or ordered retirement. Current
 // occupied[] and active[] are checked at the actual reservation edge.
 reg [19:0] checked_base;
 reg [1:0] checked_request;
 reg window0,window1,old0,old1;
 reg [1:0] offered;
 reg reserve_turn;
 // A ready/valid request holds its address until grant. Checking its previous
 // valid cycle is sufficient to qualify the cached arithmetic; comparing the
 // entire address again would reintroduce a wide mux/compare control path.
 wire fresh0=checked_request[0] && request[0] && checked_base==next_sequence;
 wire fresh1=checked_request[1] && request[1] && checked_base==next_sequence;
 wire bad0=epoch==0 || epoch0!=epoch || offset0[11:0]!=0 || old0 || (window0 && occupied[slot0]);
 wire bad1=epoch==0 || epoch1!=epoch || offset1[11:0]!=0 || old1 || (window1 && occupied[slot1]);
 assign slot0=sequence0[SLOT_BITS-1:0];
 assign slot1=sequence1[SLOT_BITS-1:0];
 // A not-yet-open future window is backpressure, not an accepted/dropped page.
 // Register the grant, then reserve at its handshake edge. Do not issue a
 // second offer until the first has updated occupied[], so its check cannot
 // see stale ownership. Request/address must remain stable until handshake.
 // Only page metadata uses this two-cycle arbitration; payload is unaffected.
 wire eligible0=fresh0 && request[0] && !active[0] && !bad0 && window0;
 wire eligible1=fresh1 && request[1] && !active[1] && !bad1 && window1;
 assign grant=offered & {2{!fault}};
 assign page_slot=next_sequence[SLOT_BITS-1:0];
 assign page_offset={next_sequence,12'd0};
 assign page_valid=!fault && complete[page_slot];
 always @(posedge clk or negedge resetn) begin
  if(!resetn) begin
   occupied<=0;complete<=0;next_sequence<=RESET_SEQUENCE;
   owned0<=0;owned1<=0;active<=0;fault<=0;
   reserve_turn<=0;offered<=0;checked_request<=0;checked_base<=0;
   window0<=0;window1<=0;old0<=0;old1<=0;
  end else if(!fault) begin
   offered<=0;
   if(offered==0)begin
    if(!reserve_turn && eligible0)begin offered<=1;reserve_turn<=1;end
    else if(eligible1)begin offered<=2;reserve_turn<=0;end
    else if(eligible0)begin offered<=1;reserve_turn<=1;end
   end
   checked_request<=request;checked_base<=next_sequence;
   window0<=!(|delta0[19:SLOT_BITS]);window1<=!(|delta1[19:SLOT_BITS]);
   old0<=delta0[19];old1<=delta1[19];
   if(abort || (retire&&!page_valid) || (|(finish&~active)) ||
      (fresh0&&request[0]&&!active[0]&&bad0) || (fresh1&&request[1]&&!active[1]&&bad1)) fault<=1;
   // Updates on the edge detecting a fatal error are tentative: fault masks
   // every output immediately afterwards and freezes until epoch reset. Do
   // not distribute the entire error-detection cone as all metadata FF CEs.
    if(request[0]&&grant[0]) begin
     occupied[slot0]<=1;complete[slot0]<=0;owned0<=slot0;active[0]<=1;
    end
    if(request[1]&&grant[1]) begin
     occupied[slot1]<=1;complete[slot1]<=0;owned1<=slot1;active[1]<=1;
    end
    if(finish[0]) begin complete[owned0]<=1;active[0]<=0;end
    if(finish[1]) begin complete[owned1]<=1;active[1]<=0;end
    if(retire) begin
     occupied[page_slot]<=0;complete[page_slot]<=0;next_sequence<=next_sequence+1'b1;
    end
  end
 end
endmodule
