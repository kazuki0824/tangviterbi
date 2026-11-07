// Resource/timing harness, NOT a receiver or a board connection diagram.
// Every FFT bin/data bit affects the signature. External memory is a stimulus
// port, not SDRAM/PSRAM; these results only qualify the computational block.
module shared_sdf_benchmark #(
 parameter integer EXTERNAL_FIRST=1
)(
 input wire clk,resetn,in_valid,out_ready,external_ready,
 input wire [1:0] mode,input wire [7:0] stimulus,
 output wire [7:0] signature,
 output wire in_ready,out_valid,overflow
);
 reg [31:0] input_word,ext_q,digest;
 assign signature=digest[7:0]^digest[15:8]^digest[23:16]^digest[31:24];
 wire [31:0] data,wd;
 wire [12:0] bin;
 wire [11:0] ra,wa;
 wire re,we,frame_end;
 shared_sdf_fft #(.EXTERNAL_FIRST(EXTERNAL_FIRST)) dut(
  .clk(clk),.resetn(resetn),.mode(mode),
  .in_valid(in_valid),.in_ready(in_ready),.in_data(input_word),
  .out_valid(out_valid),.out_ready(out_ready),.out_data(data),
  .out_bin(bin),.out_frame_end(frame_end),.external_ready(external_ready),
  .external_read_enable(re),.external_read_addr(ra),.external_read_data(ext_q),
  .external_write_enable(we),.external_write_addr(wa),.external_write_data(wd),
  .overflow(overflow));
 always @(posedge clk) begin
  if(!resetn) begin input_word<=0;ext_q<=0;digest<=0;end
  else begin
   input_word<={input_word[23:0],stimulus};
   if(re)ext_q<=input_word^{20'd0,ra};
   digest<={digest[30:0],digest[31]^digest[21]^digest[1]^digest[0]}^
     (out_valid&&out_ready ? data^{18'd0,frame_end,bin} : 32'd0)^
     (we ? wd^{20'd0,wa} : 32'd0);
  end
 end
endmodule
