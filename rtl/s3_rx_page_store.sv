// Two validated write streams -> one tagged, acknowledged memory write port.
// This implements ordering/ownership, NOT a physical PSRAM interface. Memory
// must return exactly one ack for each accepted word, with its original tag.
// Consumer reads from the same page-slot memory and retires after its last read.
module s3_rx_page_store #(
 parameter SLOT_BITS=4, STREAM_ID=1, ACK_TIMEOUT_CYCLES=32768, REORDER_PIPE_WINDOW=0, FIXED_ARBITER=0,
 parameter [19:0] RESET_SEQUENCE=0
)(
 input wire clk,resetn,input wire [15:0] epoch,
 input wire [1:0] in_valid,output wire [1:0] in_ready,
 input wire [35:0] token0,token1,input wire upstream_fault,
 output wire mem_valid,input wire mem_ready,
 output wire [SLOT_BITS+9:0] mem_word_address,
 output wire [31:0] mem_data,output wire mem_tag,
 input wire ack_valid,ack_tag,
 output wire page_valid,output wire [31:0] page_offset,
 output wire [SLOT_BITS-1:0] page_slot,input wire retire,
 output wire fault
);
 initial if(STREAM_ID!=1 && STREAM_ID!=2) $fatal(1,"invalid write stream");
 // Registered token boundaries remove the reservation/arbiter -> async FIFO
 // BSRAM-enable path. Each port still accepts one word per two core clocks
 // (49.5 Mword/s at 99 MHz), above the Octal port's 20 Mword/s maximum.
 reg [35:0] token[0:1];reg [1:0] token_full;
 wire [1:0] request,grant,start,dv,dr,commit,guard_fault,active,finish,guarded_ready;
 wire [1:0] stream[0:1];wire [31:0] offset[0:1],data[0:1];
 wire [SLOT_BITS-1:0] reserve_slot[0:1];
 reg [SLOT_BITS-1:0] owned[0:1];
 reg [9:0] index[0:1];reg [10:0] outstanding[0:1];
 reg [1:0] end_seen;
 localparam ACK_TIMER_BITS=$clog2(ACK_TIMEOUT_CYCLES+1);
 reg [ACK_TIMER_BITS-1:0] ack_age[0:1];
 reg [1:0] ack_timeout;
 reg memory_fault,stream_fault;
 reg stopped;
 wire reorder_fault,ordered_valid;
 assign page_valid=ordered_valid && !fault;
 assign in_ready=~token_full & {2{!fault}};
 reg prefer,held,held_port;
 wire choose=held ? held_port : (FIXED_ARBITER ? prefer : ((dv[1]&&prefer)||!dv[0]));
 assign mem_valid=!fault && dv[choose];
 assign mem_data=data[choose];assign mem_tag=choose;
 assign mem_word_address={owned[choose],index[choose]};
 assign dr[0]=!stopped && !choose && mem_ready;
 assign dr[1]=!stopped && choose && mem_ready;
 wire [1:0] push={mem_valid&&mem_ready&&choose,mem_valid&&mem_ready&&!choose};
 wire [1:0] ack={ack_valid&&ack_tag,ack_valid&&!ack_tag};
 reg [1:0] filtered_request;
 assign fault=upstream_fault || (|guard_fault) || reorder_fault || memory_fault || stream_fault || (|ack_timeout);
 // Mask public handshakes immediately with fault, but register the internal
 // freeze. Tentative internal transitions during that one fatal edge cannot
 // publish a page or memory write; the epoch can only recover by full reset.
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin stopped<=0;filtered_request<=0;end
  else begin
   if(fault)stopped<=1;
   filtered_request<={request[1]&&stream[1]==STREAM_ID,request[0]&&stream[0]==STREAM_ID} & {2{!stopped}};
  end
 end
 genvar p;generate for(p=0;p<2;p=p+1)begin:g
  s3_page_guard guard(clk,resetn,epoch,token_full[p]&&!stopped,guarded_ready[p],token[p],
   grant[p]&&!stopped&&stream[p]==STREAM_ID,start[p],stream[p],offset[p],
   dv[p],dr[p],data[p],commit[p],guard_fault[p],request[p]);
  assign finish[p]=end_seen[p] && outstanding[p]==0 && !stopped;
  always @(posedge clk or negedge resetn)begin
   if(!resetn)begin owned[p]<=0;index[p]<=0;outstanding[p]<=0;end_seen[p]<=0;ack_age[p]<=0;ack_timeout[p]<=0;end
   else if(!stopped)begin
    // A progress watchdog covers accepted words even after the wire frame has
    // committed (where the page guard's frame timer has already stopped).
    // Reset only on a real tagged ack or when no writes remain outstanding.
    if(outstanding[p]==0 || ack[p])ack_age[p]<=0;
    else if(ack_age[p]==ACK_TIMEOUT_CYCLES-1)ack_timeout[p]<=1;
    else ack_age[p]<=ack_age[p]+1'b1;
    if(filtered_request[p]&&grant[p])begin owned[p]<=reserve_slot[p];index[p]<=0;end
    if(push[p])index[p]<=index[p]+1'b1;
    case({push[p],ack[p]})
     2'b10:outstanding[p]<=outstanding[p]+1'b1;
     2'b01:outstanding[p]<=outstanding[p]-1'b1;
    endcase
    if(commit[p])end_seen[p]<=1;
    if(finish[p])end_seen[p]<=0;
   end
  end
 end endgenerate
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin token_full<=0;token[0]<=0;token[1]<=0;end
  else if(!stopped)begin
   if(in_valid[0]&&in_ready[0])begin token[0]<=token0;token_full[0]<=1;end
   if(in_valid[1]&&in_ready[1])begin token[1]<=token1;token_full[1]<=1;end
   if(token_full[0]&&guarded_ready[0])token_full[0]<=0;
   if(token_full[1]&&guarded_ready[1])token_full[1]<=0;
  end
 end
 s3_page_reorder #(.SLOT_BITS(SLOT_BITS),.RESET_SEQUENCE(RESET_SEQUENCE),.PIPE_WINDOW(REORDER_PIPE_WINDOW)) order(
  // Guard has already rejected non-page-aligned offsets. Make that invariant
  // explicit at the boundary, removing a second 12-bit alignment comparator.
  clk,resetn,epoch,filtered_request,grant,{offset[0][31:12],12'd0},{offset[1][31:12],12'd0},epoch,epoch,
  reserve_slot[0],reserve_slot[1],finish,upstream_fault||(|guard_fault)||memory_fault||stream_fault,
  ordered_valid,page_offset,page_slot,retire,active,reorder_fault);
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin prefer<=0;held<=0;held_port<=0;memory_fault<=0;stream_fault<=0;end
  else if(!stopped)begin
   if(mem_valid&&!mem_ready)begin held<=1;held_port<=choose;end
   if(mem_valid&&mem_ready)held<=0;
   // Fixed slots eliminate cross-port payload decode -> peer ready paths.
   // Each port gets one memory opportunity per two core clocks.
   if(FIXED_ARBITER)begin
    if(!held || mem_ready)prefer<=!choose;
   end else if(mem_valid&&mem_ready)prefer<=!choose;
   if((ack[0]&&outstanding[0]==0&&!push[0]) ||
      (ack[1]&&outstanding[1]==0&&!push[1]))memory_fault<=1;
   if((request[0]&&stream[0]!=STREAM_ID)||(request[1]&&stream[1]!=STREAM_ID))stream_fault<=1;
  end
 end
endmodule
