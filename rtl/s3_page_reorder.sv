// Metadata for one stream's external-memory page ring (4096 B/page).
// Two SPI ports may reserve different pages concurrently and finish in either
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
 wire bad0=epoch==0 || epoch0!=epoch || offset0[11:0]!=0 || delta0[19] || (delta0<SLOTS && occupied[slot0]);
 wire bad1=epoch==0 || epoch1!=epoch || offset1[11:0]!=0 || delta1[19] || (delta1<SLOTS && occupied[slot1]);
 assign slot0=sequence0[SLOT_BITS-1:0];
 assign slot1=sequence1[SLOT_BITS-1:0];
 // A not-yet-open future window is backpressure, not an accepted/dropped page.
 assign grant[0]=!fault && !active[0] && !bad0 && delta0<SLOTS;
 assign grant[1]=!fault && !active[1] && !bad1 && delta1<SLOTS &&
                 !(request[0] && grant[0] && slot0==slot1);
 assign page_slot=next_sequence[SLOT_BITS-1:0];
 assign page_offset={next_sequence,12'd0};
 assign page_valid=!fault && complete[page_slot];
 always @(posedge clk or negedge resetn) begin
  if(!resetn) begin
   occupied<=0;complete<=0;next_sequence<=RESET_SEQUENCE;
   owned0<=0;owned1<=0;active<=0;fault<=0;
  end else if(!fault) begin
   if(abort || (retire&&!page_valid) || (|(finish&~active)) ||
      (request[0]&&!active[0]&&bad0) || (request[1]&&!active[1]&&bad1)) fault<=1;
   else begin
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
 end
endmodule
