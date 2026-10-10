// Mode-0 multiline S3->FPGA wire receiver; LANES=4 or 8, MSB-first header.
// Data bytes are packed little endian into 32-bit FIFO words.
// Output token tags: 1=command/epoch, 2=byte offset, 3=payload length,
// 0=payload, 8=last payload. Header validation/reordering belong downstream.
// CS clears only frame parsing, NEVER the FIFO. No input backpressure exists:
// FIFO overflow or write-frame overrun is latched until a stopped-epoch reset
// and must mute the TS path.
// FIFO is a clock-crossing elasticity buffer, not a complete page store.
// SPI reads (D71B) generate header tokens but no RX payload.
module s3_spi_rx #(parameter LANES=8, FIFO_AW=5, IGNORE_IQ_READ=0, IGNORE_STATUS_READ=0)(
 input wire spi_clk, cs_n, clk, resetn,
 input wire [LANES-1:0] dq,
 output wire valid, input wire ready, output wire [35:0] token,
 output wire overflow
);
 initial if(LANES!=4 && LANES!=8) $fatal(1,"SPI width must be 4 or 8");
 reg [13:0] byte_count;
 reg nibble;
 reg [3:0] high_nibble;
 reg [31:0] shift;
 reg [15:0] command;
 wire frame_reset=!resetn || cs_n;
 wire byte_end=LANES==8 || nibble;
 wire [7:0] octet=LANES==8 ? dq : {high_nibble,dq[3:0]};
 wire [31:0] header_word={shift[23:0],octet};
 wire [31:0] payload_word={octet,shift[31:8]};
 wire is_write=command==16'hd711 || command==16'hd712;
 wire body=byte_count>=10 && byte_count<14'd4106 && is_write;
 wire last_word=byte_count==14'd4105;
 wire word_end=body && byte_count[1:0]==1;
 wire wvalid=!cs_n && byte_end && !(IGNORE_IQ_READ && command==16'hd71b) &&
             !(IGNORE_STATUS_READ && command==16'hd71c) &&
             (byte_count==3 || byte_count==7 || byte_count==9 || word_end);
 wire [3:0] tag=byte_count==3 ? 1 : byte_count==7 ? 2 : byte_count==9 ? 3 : last_word ? 8 : 0;
 wire [31:0] value=body ? payload_word : byte_count==9 ? {16'd0,shift[7:0],octet} : header_word;
 wire wrdy;
 reg sticky;
 (* async_reg="true" *) reg fault1,fault2;
 always @(posedge spi_clk or negedge resetn) begin
  if(!resetn) sticky<=0;
  else if((wvalid&&!wrdy) || (!cs_n && byte_end && is_write && byte_count>=4106)) sticky<=1;
 end
 always @(posedge clk or negedge resetn) begin
  if(!resetn) begin fault1<=0;fault2<=0;end
  else begin fault1<=sticky;fault2<=fault1;end
 end
 assign overflow=fault2;
 always @(posedge spi_clk or posedge frame_reset) begin
  if(frame_reset) begin byte_count<=0;nibble<=0;high_nibble<=0;shift<=0;command<=0;end
  else begin
   if(LANES==4) begin nibble<=!nibble;high_nibble<=dq[3:0];end
   if(byte_end) begin
    if(byte_count!=14'h3fff) byte_count<=byte_count+1'b1;
    shift<=byte_count<10 ? header_word : payload_word;
    if(byte_count==1) command<={shift[7:0],octet};
   end
  end
 end
 s3_async_fifo #(.W(36),.AW(FIFO_AW)) fifo(
  spi_clk,clk,resetn,wvalid,wrdy,{tag,value},valid,ready,token);
endmodule
