// Scan stimulus and individually registered observation of all outputs.
module shared_tc8_k7_connected_probe(input wire clk,resetn,scan_enable,scan_in,output wire signature);
 reg[56:0]stimulus;wire[11:0]observed;
 reg[11:0]observed_capture;reg digest_chunk,digest;
 always @(posedge clk)begin
  if(!resetn)begin stimulus<=0;observed_capture<=0;digest_chunk<=0;digest<=0;end
  else begin
   if(scan_enable)stimulus<={stimulus[55:0],scan_in};
   observed_capture<=observed;digest_chunk<=^observed_capture;digest<=digest^digest_chunk;
  end
 end
 assign signature=digest;
 shared_tc8_k7_depuncture_stream dut(
 .clk(clk),.resetn(resetn),.rates(stimulus[11:0]),.s_tc8_mode(stimulus[12]),
 .iq_valid(stimulus[13]),.iq_ready(observed[0]),.in_i(stimulus[29:14]),.in_q(stimulus[45:30]),
 .in_valid(stimulus[46]),.in_ready(observed[1]),.in_context(stimulus[48:47]),.in_soft(stimulus[56:49]),
 .out_valid(observed[2]),.out_bit(observed[3]),.out_context(observed[5:4]),
 .out_b1(observed[6]),.out_tc8(observed[7]),.fault(observed[11:8]));
endmodule
