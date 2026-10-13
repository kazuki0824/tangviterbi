// One complete, immutable 4096-byte IQ page, core clock -> mode-0 SPI read.
// D7 1B | epoch16 | offset32 | length16, MSB-first header; payload bytes are
// chronological little-endian 32-bit words. No dummy clocks are inserted.
// The producer must fill all 1024 words before exposing page_ready to the S3.
// SPI owns RAM from publication until the LAST payload sampling edge; neither
// idle SCK nor a stopped clock at the end may prevent completion notification.
// Ready/fault status must be integrated into the S3 scheduler before adoption.
module s3_spi_iq_tx #(
 parameter LANES=4, MAX_TRANSFER_CYCLES=32768
)(
 input wire clk,resetn,
 input wire begin_valid,output wire begin_ready,
 input wire [15:0] begin_epoch,input wire [31:0] begin_offset,
 input wire word_valid,output wire word_ready,input wire [31:0] word_data,
 output wire page_ready,output reg sent,output reg fault,input wire abort,
 input wire spi_clk,cs_n,input wire [LANES-1:0] dq_in,
 output reg [LANES-1:0] dq_out,output wire dq_oe
);
 localparam HEADER_BEATS=80/LANES, WORD_BEATS=32/LANES;
 localparam TOTAL_BEATS=HEADER_BEATS+32768/LANES;
 localparam TIMER_W=$clog2(MAX_TRANSFER_CYCLES+1);
 initial if((LANES!=4 && LANES!=8) || MAX_TRANSFER_CYCLES<2)
  $fatal(1,"unsupported SPI IQ configuration");
 (* ram_style="block" *) reg [31:0] mem[0:1023];
 reg loading,published;
 reg [9:0] write_index;
 reg [15:0] page_epoch;
 reg [31:0] page_offset;
 reg acknowledged,started,spi_fault;
 (* async_reg="true" *) reg ack1,ack2,start1,start2,fault1,fault2;
 reg start_seen,waiting;
 reg [TIMER_W-1:0] age;
 assign begin_ready=!fault && !loading && published==ack2;
 assign word_ready=loading && !fault;
 assign page_ready=!fault && published!=ack2;
 always @(posedge clk) if(word_valid&&word_ready) mem[write_index]<=word_data;
 always @(posedge clk or negedge resetn) begin
  if(!resetn) begin
   loading<=0;published<=0;write_index<=0;page_epoch<=0;page_offset<=0;
   ack1<=0;ack2<=0;start1<=0;start2<=0;fault1<=0;fault2<=0;
   start_seen<=0;waiting<=0;age<=0;sent<=0;fault<=0;
  end else begin
   ack1<=acknowledged;ack2<=ack1;start1<=started;start2<=start1;
   fault1<=spi_fault;fault2<=fault1;sent<=0;
   if(abort||fault2) fault<=1;
   if(!fault) begin
    if(begin_valid&&begin_ready) begin
     if(begin_epoch==0 || begin_offset[11:0]!=0) fault<=1;
     else begin loading<=1;write_index<=0;page_epoch<=begin_epoch;page_offset<=begin_offset;end
    end
    if(word_valid&&word_ready) begin
     write_index<=write_index+1'b1;
     if(write_index==1023) begin loading<=0;published<=~published;end
    end
    if(start2!=start_seen) begin start_seen<=start2;waiting<=1;age<=0;end
    else if(waiting) begin
     if(ack2==published) begin waiting<=0;sent<=1;end
     else if(age==MAX_TRANSFER_CYCLES-1) fault<=1;
     else age<=age+1'b1;
    end
   end
  end
 end

 (* async_reg="true" *) reg pub1,pub2;
 reg [13:0] beat;
 reg [79:0] header;
 reg selected,oe_q;
 wire frame_reset=cs_n || !resetn;
 wire [79:0] next_header={header[79-LANES:0],dq_in};
 wire is_iq=next_header[79:64]==16'hd71b;
 // The metadata bus is a bundled-data handshake: held from before published
 // crosses two flops until acknowledged crosses back. No independent bit sync.
 wire header_ok=pub2!=acknowledged && next_header[63:48]==page_epoch &&
                next_header[47:16]==page_offset && next_header[15:0]==4096;
 wire last_header=!cs_n && beat==HEADER_BEATS-1;
 wire last_payload=!cs_n && selected && beat==TOTAL_BEATS-1;
 always @(posedge spi_clk or negedge resetn) begin
  if(!resetn) begin pub1<=0;pub2<=0;acknowledged<=0;started<=0;spi_fault<=0;end
  else begin
   pub1<=published;pub2<=pub1;
   if(last_header&&is_iq) begin
    if(!header_ok) spi_fault<=1;
    else started<=~started;
   end
   if(last_payload&&!spi_fault) acknowledged<=pub2;
   if(!cs_n && selected && beat>=TOTAL_BEATS) spi_fault<=1;
  end
 end
 always @(posedge spi_clk or posedge frame_reset) begin
  if(frame_reset) begin beat<=0;header<=0;selected<=0;end
  else begin
   if(beat!=14'h3fff) beat<=beat+1'b1;
   if(beat<HEADER_BEATS) header<=next_header;
   if(last_header) selected<=is_iq && header_ok && !spi_fault;
  end
 end
 // Prefetch the next word on the edge that samples the preceding word's last
 // lane. All header clocks preload word zero; its first lane is thus ready
 // on the falling edge immediately following the final header sampling edge.
 wire [13:0] payload_beat=beat-HEADER_BEATS;
 wire [13:0] next_payload_beat=payload_beat+1'b1;
 wire [9:0] read_index=beat<HEADER_BEATS ? 10'd0 :
                             next_payload_beat/(32/LANES);
 reg [31:0] read_word;
 always @(posedge spi_clk) read_word<=mem[read_index];
 wire [2:0] byte_lane=(payload_beat/(8/LANES))%4;
 wire [7:0] output_byte=read_word>>(8*byte_lane);
 always @(negedge spi_clk or posedge frame_reset) begin
  if(frame_reset) begin oe_q<=0;dq_out<=0;end
  else begin
   oe_q<=selected && beat>=HEADER_BEATS && beat<TOTAL_BEATS && !spi_fault;
   if(LANES==8) dq_out<=output_byte;
   else dq_out<=payload_beat[0] ? output_byte[3:0] : output_byte[7:4];
  end
 end
 assign dq_oe=oe_q && !cs_n && !fault;
endmodule
