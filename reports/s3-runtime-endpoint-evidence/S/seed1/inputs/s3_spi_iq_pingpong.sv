// Two immutable 4096-byte pages. The producer can fill one page while SPI
// transmits the other. Page offset bit 12 selects the bank. Each publication,
// acknowledgement and timeout belongs to that bank; metadata is bundled data
// held through its handshake. SCK may stop after the last payload edge.
module s3_spi_iq_pingpong #(
 parameter LANES=4,MAX_TRANSFER_CYCLES=32768
)(
 input wire clk,resetn,
 input wire begin_valid,output wire begin_ready,
 input wire [15:0] begin_epoch,input wire [31:0] begin_offset,
 input wire word_valid,output wire word_ready,input wire [31:0] word_data,
 output wire [1:0] page_ready,output reg sent,output reg fault,input wire abort,
 input wire spi_clk,cs_n,input wire [LANES-1:0] dq_in,
 output reg [LANES-1:0] dq_out,output wire dq_oe
);
 localparam HEADER_BEATS=80/LANES,WORD_BEATS=32/LANES;
 localparam TOTAL_BEATS=HEADER_BEATS+32768/LANES;
 localparam TIMER_W=$clog2(MAX_TRANSFER_CYCLES+1);
 (* ram_style="block" *) reg [31:0] mem[0:2047];
 reg loading,write_bank;reg [9:0] write_index;
 reg [1:0] published,acknowledged,started;
 reg [15:0] page_epoch[0:1];reg [31:0] page_offset[0:1];
 reg spi_fault;
 (* async_reg="true" *) reg [1:0] ack1,ack2,start1,start2;
 (* async_reg="true" *) reg fault1,fault2;
 reg [1:0] start_seen,waiting;
 reg [TIMER_W-1:0] age[0:1];
 assign begin_ready=!fault&&!loading&&published[write_bank]==ack2[write_bank];
 assign word_ready=loading&&!fault;
 assign page_ready=(published^ack2)&{2{!fault}};
 always @(posedge clk)if(word_valid&&word_ready)mem[{write_bank,write_index}]<=word_data;
 integer b;
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   loading<=0;write_bank<=0;write_index<=0;published<=0;ack1<=0;ack2<=0;
   start1<=0;start2<=0;fault1<=0;fault2<=0;start_seen<=0;waiting<=0;sent<=0;fault<=0;
   for(b=0;b<2;b=b+1)begin page_epoch[b]<=0;page_offset[b]<=0;age[b]<=0;end
  end else begin
   ack1<=acknowledged;ack2<=ack1;start1<=started;start2<=start1;
   fault1<=spi_fault;fault2<=fault1;sent<=0;
   if(abort||fault2)fault<=1;
   if(!fault)begin
    if(begin_valid&&begin_ready)begin
     if(begin_epoch==0||begin_offset[11:0]!=0||begin_offset[12]!=write_bank)fault<=1;
     else begin loading<=1;write_index<=0;page_epoch[write_bank]<=begin_epoch;page_offset[write_bank]<=begin_offset;end
    end
    if(word_valid&&word_ready)begin
     write_index<=write_index+1'b1;
     if(write_index==1023)begin loading<=0;published[write_bank]<=!published[write_bank];write_bank<=!write_bank;end
    end
    for(b=0;b<2;b=b+1)begin
     if(start2[b]!=start_seen[b])begin start_seen[b]<=start2[b];waiting[b]<=1;age[b]<=0;end
     else if(waiting[b])begin
      if(ack2[b]==published[b])begin waiting[b]<=0;sent<=1;end
      else if(age[b]==MAX_TRANSFER_CYCLES-1)fault<=1;
      else age[b]<=age[b]+1'b1;
     end
    end
   end
  end
 end
 (* async_reg="true" *) reg [1:0] pub1,pub2;
 reg [13:0] beat;reg [79:0] header;
 reg selected,read_bank,oe_q;
 wire frame_reset=cs_n||!resetn;
 wire [79:0] next_header={header[79-LANES:0],dq_in};
 wire target_bank=next_header[28];
 wire is_iq=next_header[79:64]==16'hd71b;
 wire header_ok=pub2[target_bank]!=acknowledged[target_bank] &&
  next_header[63:48]==page_epoch[target_bank] &&
  next_header[47:16]==page_offset[target_bank] && next_header[15:0]==4096;
 wire last_header=!cs_n&&beat==HEADER_BEATS-1;
 wire last_payload=!cs_n&&selected&&beat==TOTAL_BEATS-1;
 always @(posedge spi_clk or negedge resetn)begin
  if(!resetn)begin pub1<=0;pub2<=0;acknowledged<=0;started<=0;spi_fault<=0;end
  else begin
   pub1<=published;pub2<=pub1;
   if(last_header&&is_iq)begin
    if(!header_ok)spi_fault<=1;
    else started[target_bank]<=!started[target_bank];
   end
   if(last_payload&&!spi_fault)acknowledged[read_bank]<=pub2[read_bank];
   if(!cs_n&&selected&&beat>=TOTAL_BEATS)spi_fault<=1;
  end
 end
 always @(posedge spi_clk or posedge frame_reset)begin
  if(frame_reset)begin beat<=0;header<=0;selected<=0;read_bank<=0;end
  else begin
   if(beat!=14'h3fff)beat<=beat+1'b1;
   if(beat<HEADER_BEATS)header<=next_header;
   if(beat==64/LANES-1)read_bank<=next_header[12];
   if(last_header)selected<=is_iq&&header_ok&&!spi_fault;
  end
 end
 wire [13:0] payload_beat=beat-HEADER_BEATS;
 wire [13:0] next_payload_beat=payload_beat+1'b1;
 wire [9:0] read_index=beat<HEADER_BEATS?10'd0:next_payload_beat/WORD_BEATS;
 // Offset has been received two bytes before the header ends. Bank selection
 // is registered there so RAM word zero is prefetched before the final edge.
 wire memory_bank=read_bank;
 reg [31:0] read_word;
 always @(posedge spi_clk)read_word<=mem[{memory_bank,read_index}];
 wire [2:0] byte_lane=(payload_beat/(8/LANES))%4;
 wire [7:0] output_byte=read_word>>(8*byte_lane);
 always @(negedge spi_clk or posedge frame_reset)begin
  if(frame_reset)begin oe_q<=0;dq_out<=0;end
  else begin
   oe_q<=selected&&beat>=HEADER_BEATS&&beat<TOTAL_BEATS&&!spi_fault;
   if(LANES==8)dq_out<=output_byte;
   else dq_out<=payload_beat[0]?output_byte[3:0]:output_byte[7:4];
  end
 end
 assign dq_oe=oe_q&&!cs_n&&!fault;
endmodule
