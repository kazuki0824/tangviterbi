// Single-producer, 256-byte holding bursts. Write and read staging share one
// 128x32 BSRAM. Non-stallable PSRAM reads own the write port.
// Physical writes own the RAM read port. The consumer retains a cached word
// and pauses only at its next word boundary until that port is available.
// Exclusive owner: s3_rs_psram_store, one codeword awaiting physical commit.
module s3_rs_psram_queue(
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
 (* ram_style="block" *) reg [31:0] staging[0:127];
 reg full,read_pending,read_complete,selected_read,prefer_read;
 reg [5:0] fill_index,tx_index,read_index;
 reg [6:0] rx_count,ack_remaining;
 reg [20:0] write_base,pending_address;
 reg [1:0] state;
 reg [31:0] read_q,ram_q;
 reg [1:0] read_refill;
 reg local_fault;
 localparam IDLE=0,COMMAND=1,TRANSFER=2;
 assign fault=local_fault||upstream_fault||burst_fault;
 assign in_ready=!full&&!r_valid&&!fault;
 assign ack_valid=ack_remaining!=0&&!fault;
 assign ack_tag=1'b0;
 assign read_ready=!read_pending&&!read_complete&&!fault;
 assign read_valid=read_complete&&!read_refill&&!fault;
 assign read_data=read_q;
 assign read_last=read_index==63;
 assign cmd_valid=state==COMMAND&&!fault;
 assign cmd_write=!selected_read;
 assign cmd_address=selected_read?pending_address:write_base;
 assign w_valid=state==TRANSFER&&!selected_read&&!fault;
 assign w_data=ram_q;
 wire pick_read=read_pending&&(prefer_read||!full);
 wire can_write=full;
 wire issue=read_pending||can_write;
 // One synchronous RAM output serves both owners. Refill the consumer cache
 // for two clocks after a word boundary; restart refill if a write intervenes.
 wire writing=state!=IDLE&&!selected_read;
 wire [6:0] ram_read_address=!writing?
  {1'b1,read_index}:
  {1'b0,(w_valid&&w_ready?tx_index+6'd1:tx_index)};
 always @(posedge clk)begin
  if(resetn&&!fault)begin
   if(r_valid&&state==TRANSFER&&selected_read&&rx_count<64)
    staging[{1'b1,rx_count[5:0]}]<=r_data;
   else if(in_valid&&in_ready)staging[{1'b0,fill_index}]<=in_data;
  end
  ram_q<=staging[ram_read_address];
 end
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   full<=0;read_pending<=0;read_complete<=0;selected_read<=0;prefer_read<=0;
   fill_index<=0;tx_index<=0;read_index<=0;rx_count<=0;ack_remaining<=0;
   write_base<=0;pending_address<=0;state<=IDLE;local_fault<=0;read_refill<=0;
  end else if(!fault)begin
   if(in_valid&&in_ready)begin
    if(in_tag)local_fault<=1;
    if(fill_index==0)begin
     if(in_address[5:0]!=0)local_fault<=1;
     write_base<=in_address;
    end else if(in_address!={write_base[20:6],fill_index})local_fault<=1;
    fill_index<=fill_index+1'b1;
    if(fill_index==63)full<=1;
   end
   if(ack_valid)ack_remaining<=ack_remaining-1'b1;
   if(read_request&&read_ready)begin
    if(read_address[5:0]!=0)local_fault<=1;
    read_pending<=1;pending_address<=read_address;
   end
   if(read_valid&&read_take)begin
    read_index<=read_index+1'b1;
    if(read_index==63)read_complete<=0;
    else read_refill<=2;
   end
   if(read_refill!=0&&writing)read_refill<=2;
   if(read_refill!=0&&!writing)begin
    read_refill<=read_refill-1'b1;
    if(read_refill==1)read_q<=ram_q;
   end
   case(state)
    IDLE:if(issue)begin
     selected_read<=pick_read||!can_write;state<=COMMAND;
     tx_index<=0;rx_count<=0;
    end
    COMMAND:if(cmd_valid&&cmd_ready)begin state<=TRANSFER;prefer_read<=!selected_read;end
    TRANSFER:begin
     if(w_valid&&w_ready)tx_index<=tx_index+1'b1;
     if(r_valid)begin
      if(!selected_read||rx_count==64)local_fault<=1;
      else rx_count<=rx_count+1'b1;
     end
     if(burst_done)begin
      state<=IDLE;
      if(selected_read)begin
       if(rx_count!=64)local_fault<=1;
       read_pending<=0;read_complete<=1;read_index<=0;read_refill<=2;
      end else begin
       if(ack_remaining!=0)local_fault<=1;
       full<=0;ack_remaining<=64;
      end
     end
    end
    default:local_fault<=1;
   endcase
  end else local_fault<=1;
 end
endmodule
