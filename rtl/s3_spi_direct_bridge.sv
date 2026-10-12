// Two physical SPI inputs -> four committed 4-KiB BSRAM pages -> ordered words.
// The native packed I10/Q10 payload is unchanged. No PSRAM PHY/controller.
// The caller must bound sink stalls and issue page credits before SPI starts;
// overflow poisons the epoch, never discards an old page to accept a new one.
// This is a transport component, not FIR/sync/FFT/FEC/TS or a receiver.
module s3_spi_direct_bridge #(
 parameter SLOT_BITS=2, WINDOW_PIPELINE=0
)(
 input wire clk,resetn,input wire [15:0] epoch,
 input wire spi2_sclk,spi2_cs_n,input wire [7:0] spi2_d,
 input wire spi3_sclk,spi3_cs_n,input wire [3:0] spi3_d,
 output wire out_valid,input wire out_ready,output wire [31:0] out_data,
 output wire out_last,output wire [31:0] out_offset,output wire fault
);
 wire [35:0] token0,token1;
 wire [1:0] valid,ready,overflow;
 s3_spi_rx #(.LANES(8),.FIFO_AW(7),.IGNORE_IQ_READ(1),.IGNORE_CONTROL(1)) p2(
  spi2_sclk,spi2_cs_n,clk,resetn,spi2_d,valid[0],ready[0],token0,overflow[0]);
 s3_spi_rx #(.LANES(4),.FIFO_AW(7),.IGNORE_IQ_READ(1),.IGNORE_CONTROL(1)) p3(
  spi3_sclk,spi3_cs_n,clk,resetn,spi3_d,valid[1],ready[1],token1,overflow[1]);
 wire write_valid,write_tag,page_valid,retire,store_fault;
 wire [SLOT_BITS+9:0] write_address;
 wire [31:0] write_data,page_offset;
 wire [SLOT_BITS-1:0] page_slot;
 reg ack_valid,ack_tag;
 reg local_fault;
 assign fault=store_fault||local_fault;
 s3_rx_page_store #(.SLOT_BITS(SLOT_BITS),.WINDOW_PIPELINE(WINDOW_PIPELINE)) store(
  clk,resetn,epoch,valid,ready,token0,token1,|overflow,
  write_valid,1'b1,write_address,write_data,write_tag,ack_valid,ack_tag,
  page_valid,page_offset,page_slot,retire,store_fault);
 // Synchronous read port and registered output; one read may be outstanding.
 // Keep the page owned until the last word has been accepted by the sink.
 reg [31:0] memory[0:(1<<(SLOT_BITS+10))-1];
 reg active,read_pending,holding;
 reg [SLOT_BITS-1:0] slot;
 reg [31:0] offset,read_value,held_value;
 reg [9:0] index;
 wire take=out_valid&&out_ready;
 wire launch=active&&!read_pending&&!holding&&!fault;
 assign out_valid=holding&&!fault;
 assign out_data=held_value;
 assign out_last=index==1023;
 assign out_offset=offset;
 assign retire=take&&out_last;
 always @(posedge clk)begin
  if(write_valid)memory[write_address]<=write_data;
  if(launch)read_value<=memory[{slot,index}];
 end
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   ack_valid<=0;ack_tag<=0;active<=0;read_pending<=0;holding<=0;
   slot<=0;offset<=0;index<=0;held_value<=0;local_fault<=0;
  end else begin
   ack_valid<=write_valid;ack_tag<=write_tag;
   if(!fault)begin
    if(!active&&page_valid)begin active<=1;slot<=page_slot;offset<=page_offset;index<=0;end
    if(active&&(!page_valid||page_slot!=slot||page_offset!=offset))local_fault<=1;
    if(launch)read_pending<=1;
    if(read_pending)begin read_pending<=0;held_value<=read_value;holding<=1;end
    if(take)begin
     holding<=0;index<=index+1'b1;
     if(out_last)active<=0;
    end
   end
  end
 end
endmodule
