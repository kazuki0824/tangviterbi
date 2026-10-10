// Mode-0 Octal credit snapshot. Query: D71C | epoch16 | zero32 | length16=16.
// Follow with 16 dummy SCK edges, then 16 response bytes. The first 8 bytes
// are C7A1 | epoch16 | retired_sequence20 | window4=WINDOW | flags8; the remaining
// 8 are their bitwise complement. This detects single-bit wire errors; it is
// not a CRC or an electrical timing qualification. No page is retired here.
// A toggle handshake captures one immutable core snapshot. The SPI clock may
// stop between transactions; publication does not depend on a trailing edge.
module s3_spi_page_status #(parameter WINDOW=2)(
 input wire clk,resetn,input wire [15:0] epoch,
 input wire [19:0] retired_sequence,input wire receiver_fault,
 input wire spi_clk,cs_n,input wire [7:0] dq_in,
 output reg [7:0] dq_out,output wire dq_oe,output reg fault
);
 localparam [3:0] WINDOW_BITS=WINDOW;
 initial if(WINDOW!=2 && WINDOW!=4 && WINDOW!=8)$fatal(1,"invalid credit window");
 reg request,acknowledged;
 (* async_reg="true" *) reg request1,request2;
 (* async_reg="true" *) reg ack1,ack2;
 reg [63:0] snapshot;
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin request1<=0;request2<=0;acknowledged<=0;snapshot<=0;end
  else begin
   request1<=request;request2<=request1;
   if(request2!=acknowledged)begin
    snapshot<={16'hc7a1,epoch,retired_sequence,WINDOW_BITS,7'd0,receiver_fault};
    acknowledged<=request2;
   end
  end
 end
 reg [6:0] beat;
 reg [79:0] header;
 reg selected,oe;
 wire frame_reset=cs_n||!resetn;
 wire [79:0] next_header={header[71:0],dq_in};
 wire is_status=next_header[79:64]==16'hd71c;
 wire good_header=next_header[63:48]==epoch&&epoch!=0&&
                  next_header[47:16]==0&&next_header[15:0]==16;
 wire last_header=!cs_n&&beat==9;
 // Load the bundled, acknowledged snapshot once in the dummy phase, then
 // shift bytes. No beat subtraction or 16:1 byte mux crosses a half SCK.
 reg [127:0] response_shift;
 reg response_active;
 always @(posedge spi_clk or negedge resetn)begin
  if(!resetn)begin request<=0;ack1<=0;ack2<=0;fault<=0;end
  else begin
   ack1<=acknowledged;ack2<=ack1;
   if(last_header&&is_status)begin
    if(!good_header||request!=ack2)fault<=1;
    else request<=~request;
   end
   if(!cs_n&&selected&&((beat==26&&request!=ack2)||beat>=42))fault<=1;
  end
 end
 always @(posedge spi_clk or posedge frame_reset)begin
  if(frame_reset)begin beat<=0;header<=0;selected<=0;response_shift<=0;response_active<=0;end
  else begin
   if(beat!=127)beat<=beat+1'b1;
   if(beat<10)header<=next_header;
   if(last_header)selected<=is_status&&good_header&&!fault;
   if(beat==25)begin
    response_shift<={snapshot,~snapshot};
    response_active<=selected&&request==ack2&&!fault;
   end else if(beat>=26 && beat<41)response_shift<={response_shift[119:0],8'd0};
   if(beat==41)response_active<=0;
  end
 end
 // Snapshot is held until another query reaches the core. The next query
 // cannot be issued while this transaction's response is being sampled.
 always @(negedge spi_clk or posedge frame_reset)begin
  if(frame_reset)begin dq_out<=0;oe<=0;end
  else begin dq_out<=response_shift[127:120];oe<=response_active&&!fault;end
 end
 assign dq_oe=oe&&!cs_n&&!fault;
endmodule
