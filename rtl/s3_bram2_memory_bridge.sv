// S-mode experiment: lossless Octal/LCD16 pages in two on-chip RAM slots.
// No external PSRAM controller. A producer must obey ready/credit and the
// two-page window; the complete RF page/deadline schedule is not yet proven.
module s3_bram2_memory_bridge(
 input wire clk,resetn,input wire [15:0] epoch,
 input wire spi2_sclk,spi2_cs_n,input wire [7:0] spi2_d,
 input wire lcd_wr,lcd_cs_n,lcd_dc,input wire [15:0] lcd_d,
 output wire out_valid,input wire out_ready,output wire [31:0] out_data,
 output wire out_last,output wire [31:0] out_offset,output wire fault
);
 wire spi2_clock,lcd_clock;
 BUFG spi2_global(.I(spi2_sclk),.O(spi2_clock));
 BUFG lcd_global(.I(lcd_wr),.O(lcd_clock));
 wire [35:0] tok0,tok1;
 wire [1:0] input_valid,input_ready,overflow;
 s3_spi_rx #(.LANES(8),.FIFO_AW(7)) octal(
  spi2_clock,spi2_cs_n,clk,resetn,spi2_d,
  input_valid[0],input_ready[0],tok0,overflow[0]);
 s3_lcd16_rx #(.FIFO_AW(7)) lcd(
  lcd_clock,lcd_cs_n,lcd_dc,clk,resetn,lcd_d,
  input_valid[1],input_ready[1],tok1,overflow[1]);

 wire write_valid,write_ready,write_tag;
 reg ack_valid,ack_tag;
 wire [10:0] write_address;
 wire [31:0] write_data,page_offset;
 wire page_valid,retire,store_fault;
 wire page_slot;
 reg stopped,read_fault;
 assign fault=store_fault||(|overflow)||read_fault;
 assign write_ready=!stopped;
 s3_rx_page_store #(.SLOT_BITS(1),.STREAM_ID(1)) store(
  clk,resetn,epoch,input_valid,input_ready,tok0,tok1,
  (|overflow)||read_fault,write_valid,write_ready,write_address,
  write_data,write_tag,ack_valid,ack_tag,
  page_valid,page_offset,page_slot,retire,store_fault);

 // One synchronous dual-port 8-KiB ring. FPGA memory inference must be
 // checked in the mapped netlist, not assumed from this declaration.
 reg [31:0] mem [0:2047];
 reg [31:0] read_data;
 reg active,pending,slot;
 reg [9:0] index;
 reg [31:0] offset;
 wire write_fire=write_valid&&write_ready;
 wire read_issue=active&&!pending&&!stopped;
 assign out_valid=active&&pending&&!fault;
 assign out_data=read_data;
 assign out_last=out_valid&&index==1023;
 assign out_offset=offset;
 assign retire=out_valid&&out_ready&&index==1023;
 always @(posedge clk)begin
  if(write_fire)mem[write_address]<=write_data;
  if(read_issue)read_data<=mem[{slot,index}];
 end
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   ack_valid<=0;ack_tag<=0;stopped<=0;read_fault<=0;
   active<=0;pending<=0;slot<=0;index<=0;offset<=0;
  end else begin
   ack_valid<=write_fire;
   if(write_fire)ack_tag<=write_tag;
   if(fault)stopped<=1;
   if(!stopped)begin
    if(active&&(!page_valid||page_slot!=slot||page_offset!=offset))read_fault<=1;
    if(!active&&page_valid)begin
     active<=1;slot<=page_slot;offset<=page_offset;index<=0;
    end
    if(read_issue)pending<=1;
    if(out_valid&&out_ready)begin
     pending<=0;
     index<=index+1'b1;
     if(index==1023)active<=0;
    end
   end
  end
 end
endmodule
