// Experimental streaming radix-2 DIF FFT, selectable at elaboration for
// LOGN=11/12/13. Natural-order complex Q15 input; bit-reversed-bin output.
// NO input decimation/requantization. Arithmetic normalizes each stage by 2.
// The outermost delay stage is an IDEAL synchronous external RAM interface;
// this is NOT an SDRAM controller, DMA, integrated receiver or physical timing
// acceptance. During steady streaming each stage needs >=2 core clocks/sample.
module research_sdf_fft #(
 parameter integer LOGN=13
)(
 input wire clk,resetn,
 input wire in_valid,output wire in_ready,input wire [31:0] in_data,
 output wire out_valid,input wire out_ready,output wire [31:0] out_data,
 output wire [LOGN-1:0] out_bin,output wire out_frame_end,
 input wire external_ready,
 output wire external_read_enable,
 output wire [LOGN-2:0] external_read_addr,
 input wire [31:0] external_read_data,
 output wire external_write_enable,
 output wire [LOGN-2:0] external_write_addr,
 output wire [31:0] external_write_data,
 output wire overflow
);
 wire [31:0] sample[0:LOGN];
 wire v[0:LOGN];
 wire r[0:LOGN];
 wire [LOGN-1:0] over;
 assign sample[0]=in_data;assign v[0]=in_valid;assign in_ready=r[0];
 assign out_data=sample[LOGN];assign out_valid=v[LOGN];
 assign r[LOGN]=out_ready;
 genvar st;
 generate for(st=0;st<LOGN;st=st+1) begin: stages
   localparam integer SHIFT=LOGN-1-st;
   if(st==0) begin: outer
     research_sdf_stage #(.SHIFT(SHIFT),.EXTERNAL(1)) core (
       .clk(clk),.resetn(resetn),
       .in_valid(v[st]),.in_ready(r[st]),.in_data(sample[st]),
       .out_valid(v[st+1]),.out_ready(r[st+1]),.out_data(sample[st+1]),
       .external_ready(external_ready),
       .external_read_enable(external_read_enable),
       .external_read_addr(external_read_addr),
       .external_read_data(external_read_data),
       .external_write_enable(external_write_enable),
       .external_write_addr(external_write_addr),
       .external_write_data(external_write_data),.overflow(over[st]));
   end else begin: inner
     research_sdf_stage #(.SHIFT(SHIFT),.EXTERNAL(0)) core (
       .clk(clk),.resetn(resetn),
       .in_valid(v[st]),.in_ready(r[st]),.in_data(sample[st]),
       .out_valid(v[st+1]),.out_ready(r[st+1]),.out_data(sample[st+1]),
       .external_ready(1'b1),.external_read_data(32'd0),
       .external_read_enable(),.external_read_addr(),
       .external_write_enable(),.external_write_addr(),
       .external_write_data(),.overflow(over[st]));
   end
 end endgenerate
 reg [LOGN-1:0] output_seq;
 integer bit_no;
 reg [LOGN-1:0] reversed;
 always @(*) begin
   for(integer j=0;j<LOGN;j=j+1) reversed[j]=output_seq[LOGN-1-j];
 end
 assign out_bin=reversed;
 assign out_frame_end=&output_seq;
 always @(posedge clk) begin
   if(!resetn) output_seq<=0;
   else if(out_valid&&out_ready) output_seq<=output_seq+1'b1;
 end
 reg overflow_reg;
 always @(posedge clk) begin
   if(!resetn) overflow_reg<=0;
   else if(|over) overflow_reg<=1;
 end
 assign overflow=overflow_reg;
endmodule
