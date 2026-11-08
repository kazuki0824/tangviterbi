// Serial 3-wire MPEG-TS pin sink for ISDB-T or ISDB-S.
// Internal clock 154.285714 MHz -> 77.142857-MHz serial TS clock.
// Each input is a whole 188-byte TS packet stream, MSB-first per byte.
// Byte producer must honor valid/ready. A finite 256-byte FIFO absorbs
// short decoder bursts, but cannot guarantee arbitrary upstream RS stalls.
// The sync byte 0x47 is checked at every 188-byte packet boundary.
// Fault is fail-closed until the stopped-epoch reset; there is no CAS/AV.
module isdb_serial_ts_sink(
 input wire clk, resetn,
 input wire byte_valid, output wire byte_ready,
 input wire [7:0] byte_data,
 output reg ts_clk, output reg ts_data, output wire ts_valid,
 output reg fault
);
 (* ram_style="block" *) reg [7:0] fifo [0:255];
 reg [7:0] write_ptr,read_ptr,head_data;
 reg [8:0] occupancy;
 reg [7:0] packet_byte;
 reg [7:0] shift;
 reg [2:0] remaining_bits;
 reg head_valid,read_pending,bit_valid;

 assign ts_valid=bit_valid && !fault && resetn;
 assign byte_ready=resetn && !fault && occupancy!=9'd256;
 wire push=byte_valid && byte_ready;
 wire prefetch=resetn && !fault && occupancy!=0 && !head_valid && !read_pending;
 wire start=resetn && !fault && ts_clk && remaining_bits==0 && head_valid;

 always @(posedge clk) begin
  if(push)fifo[write_ptr]<=byte_data;
  if(prefetch)head_data<=fifo[read_ptr];
 end
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin
   write_ptr<=0;read_ptr<=0;occupancy<=0;packet_byte<=0;
   shift<=0;remaining_bits<=0;head_valid<=0;read_pending<=0;
   ts_clk<=0;ts_data<=0;bit_valid<=0;fault<=0;
  end else begin
   ts_clk<=!ts_clk;
   if(push)write_ptr<=write_ptr+1'b1;
   if(prefetch)begin read_ptr<=read_ptr+1'b1;read_pending<=1;end
   if(read_pending)begin read_pending<=0;head_valid<=1;end
   if(start)head_valid<=0;
   case({push,prefetch})
    2'b10:occupancy<=occupancy+1'b1;
    2'b01:occupancy<=occupancy-1'b1;
    default:begin end
   endcase
   if(push)begin
    if(packet_byte==0 && byte_data!=8'h47)fault<=1;
    if(packet_byte==187)packet_byte<=0;
    else packet_byte<=packet_byte+1'b1;
   end
   // Data/valid change on the TS clock falling edge and are held stable
   // for the subsequent rising sampling edge.
   if(ts_clk)begin
    if(fault)bit_valid<=0;
    else if(remaining_bits!=0)begin
     ts_data<=shift[7];shift<=shift<<1;
     remaining_bits<=remaining_bits-1'b1;
     bit_valid<=1;
    end else if(head_valid)begin
     ts_data<=head_data[7];shift<={head_data[6:0],1'b0};
     remaining_bits<=7;bit_valid<=1;
    end else bit_valid<=0;
   end
  end
 end
endmodule

// T and S have independent serial TS clocks/data/valid and fault latches.
// Six output pins total. This is not the missing RF demodulator/RS source.
module dual_isdb_serial_ts_sinks(
 input wire clk, resetn,
 input wire [1:0] byte_valid, output wire [1:0] byte_ready,
 input wire [15:0] byte_data,
 output wire [1:0] ts_clk,ts_data,ts_valid,fault
);
 genvar r;
 generate for(r=0;r<2;r=r+1)begin: receiver
  isdb_serial_ts_sink sink(
   .clk(clk),.resetn(resetn),.byte_valid(byte_valid[r]),
   .byte_ready(byte_ready[r]),.byte_data(byte_data[r*8+:8]),
   .ts_clk(ts_clk[r]),.ts_data(ts_data[r]),
   .ts_valid(ts_valid[r]),.fault(fault[r])
  );
 end endgenerate
endmodule
