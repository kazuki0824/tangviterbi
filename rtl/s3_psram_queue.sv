// Two word-write producers -> four ping-pong 256-byte burst buffers. One
// separately reserved 256-byte read buffer permits downstream backpressure.
// All memory acks are issued AFTER physical burst completion. Full buffers
// retain ownership until that completion; read requests only enter when there
// is room for the entire non-stallable DDR response. Fair round-robin across
// four write buffers and the read request prevents starvation.
module s3_psram_queue(
 input wire clk,resetn,upstream_fault,
 input wire in_valid,output wire in_ready,
 input wire in_tag,input wire [20:0] in_address,input wire [31:0] in_data,
 output wire ack_valid,output wire ack_tag,
 input wire read_request,output wire read_ready,input wire [20:0] read_address,
 output wire read_valid,input wire read_take,output wire [31:0] read_data,
 output wire read_last,
 output wire cmd_valid,input wire cmd_ready,
 output wire cmd_write,output wire [20:0] cmd_address,
 output wire w_valid,input wire w_ready,output wire [31:0] w_data,
 input wire r_valid,input wire [31:0] r_data,input wire burst_done,burst_fault,
 output wire fault
);
 (* ram_style="block" *) reg [31:0] writes[0:255];
 (* ram_style="block" *) reg [31:0] reads[0:63];
 reg [3:0] full;reg [1:0] bank_select;
 reg [5:0] fill_index[0:1];reg [20:0] bases[0:3];
 reg [2:0] state,round_robin,selected;
 localparam IDLE=0,COMMAND=1,TRANSFER=2;
 reg [5:0] tx_index;reg [6:0] rx_count,ack_remaining;
 reg ack_port;
 reg read_pending,read_complete;reg [20:0] pending_address;
 reg [5:0] read_index;
 reg [31:0] tx_data,read_q;
 reg local_fault;
 wire [1:0] filling={in_tag,bank_select[in_tag]};
 assign fault=local_fault || burst_fault || upstream_fault;
 assign in_ready=!fault&&!full[filling];
 assign ack_valid=ack_remaining!=0&&!fault;
 assign ack_tag=ack_port;
 assign read_ready=!read_pending&&!read_complete&&!fault;
 assign read_valid=read_complete&&!fault;
 assign read_data=read_q;
 assign read_last=read_index==63;
 assign cmd_valid=state==COMMAND&&!fault;
 assign cmd_write=selected!=4;
 assign cmd_address=selected==4?pending_address:bases[selected[1:0]];
 assign w_valid=state==TRANSFER&&selected!=4&&!fault;
 assign w_data=tx_data;
 reg found;reg [2:0] pick;integer k,candidate;
 always @* begin
  found=0;pick=0;candidate=0;
  for(k=0;k<5;k=k+1)begin
   candidate=round_robin+k;if(candidate>=5)candidate=candidate-5;
   if(!found && ((candidate==4&&read_pending) ||
       (candidate<4&&full[candidate])))begin found=1;pick=candidate;end
  end
 end
 integer p;
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   full<=0;bank_select<=0;state<=IDLE;round_robin<=0;selected<=0;
   tx_index<=0;rx_count<=0;ack_remaining<=0;ack_port<=0;
   read_pending<=0;read_complete<=0;pending_address<=0;read_index<=0;
   local_fault<=0;
   for(p=0;p<2;p=p+1)fill_index[p]<=0;
   for(p=0;p<4;p=p+1)bases[p]<=0;
  end else if(!fault)begin
   if(in_valid&&in_ready)begin
    if(fill_index[in_tag]==0)begin
     if(in_address[5:0]!=0)local_fault<=1;
     bases[filling]<=in_address;
    end else if(in_address!={bases[filling][20:6],fill_index[in_tag]})local_fault<=1;
    fill_index[in_tag]<=fill_index[in_tag]+1'b1;
    if(fill_index[in_tag]==63)begin full[filling]<=1;bank_select[in_tag]<=!bank_select[in_tag];end
   end
   if(ack_valid)begin
    ack_remaining<=ack_remaining-1'b1;
    // Acks overlap the next transaction. Every physical burst takes more
    // than 64 cycles, so no second completion may overwrite this ack run.
   end
   if(read_request&&read_ready)begin
    if(read_address[5:0]!=0)local_fault<=1;
    read_pending<=1;pending_address<=read_address;
   end
   if(read_valid&&read_take)begin
    read_index<=read_index+1'b1;
    if(read_index==63)read_complete<=0;
   end
   case(state)
    IDLE:if(found)begin selected<=pick;state<=COMMAND;tx_index<=0;rx_count<=0;end
    COMMAND:if(cmd_valid&&cmd_ready)begin state<=TRANSFER;round_robin<=selected==4?0:selected+1'b1;end
    TRANSFER:begin
     if(w_valid&&w_ready)tx_index<=tx_index+1'b1;
     if(r_valid)begin
      if(selected!=4||rx_count==64)local_fault<=1;
      else rx_count<=rx_count+1'b1;
     end
     if(burst_done)begin
      state<=IDLE;
      if(selected==4)begin
       if(rx_count!=64)local_fault<=1;
       read_pending<=0;read_complete<=1;read_index<=0;
      end else begin
       if(ack_remaining!=0)local_fault<=1;
       ack_remaining<=64;ack_port<=selected[1];full[selected[1:0]]<=0;
      end
     end
    end
   endcase
  end else local_fault<=1;
 end
 // Synchronous RAM reads with look-ahead. No reset on RAM/output registers,
 // so synthesis can map these arrays to BSRAM. COMMAND/DDR latency prefetches
 // word zero long before the first write beat is accepted.
 always @(posedge clk)begin
  if(resetn&&in_valid&&in_ready)writes[{filling,fill_index[in_tag]}]<=in_data;
  if(resetn&&!fault&&state==TRANSFER&&selected==4&&r_valid&&rx_count<64)reads[rx_count[5:0]]<=r_data;
  tx_data<=writes[{selected[1:0],(w_valid&&w_ready?tx_index+6'd1:tx_index)}];
  read_q<=reads[read_complete?(read_take?read_index+6'd1:read_index):6'd0];
 end
endmodule
