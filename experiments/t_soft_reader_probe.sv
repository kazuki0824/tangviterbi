// CAD-only independent serial stimulus and pipelined output observation.
module t_soft_reader_probe(input wire clk,resetn,scan_enable,scan_in,output wire signature);
 reg[370:0]stimulus;
 wire[38:0]observed;reg[38:0]observed_capture;
 reg[1:0]digest_chunks;reg digest;
 always @(posedge clk)begin
  if(!resetn)begin stimulus<=0;observed_capture<=0;digest_chunks<=0;digest<=0;end
  else begin
   if(scan_enable)stimulus<={stimulus[369:0],scan_in};
   observed_capture<=observed;
   digest_chunks[0]<=^observed_capture[31:0];digest_chunks[1]<=^observed_capture[38:32];
   digest<=digest^(^digest_chunks);
  end
 end
 assign signature=digest;
 t_soft_reader dut(.clk(clk),.resetn(resetn),
 .commit_valid(stimulus[0]),.commit_ready(observed[0]),.commit_addresses(stimulus[63:1]),
 .commit_lengths(stimulus[111:64]),.bank_live(observed[2:1]),.reuse_blocked(observed[3]),
 .req_valid(observed[4]),.req_ready(stimulus[112]),.req_address(observed[25:5]),
 .rsp_valid(stimulus[113]),.rsp_ready(observed[26]),.rsp_data(stimulus[369:114]),
 .soft_valid(observed[27]),.soft_ready(stimulus[370]),.soft_context(observed[29:28]),
 .soft_data(observed[37:30]),.fault(observed[38]));
endmodule
