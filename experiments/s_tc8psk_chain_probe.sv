// CAD-only independent scan input and pipelined observation.
module s_tc8psk_chain_probe(input wire clk,resetn,scan_enable,scan_in,output wire signature);
 reg[32:0]stimulus;wire[3:0]observed;
 reg[3:0]observed_capture;reg digest_chunk,digest;
 always @(posedge clk)begin
  if(!resetn)begin stimulus<=0;observed_capture<=0;digest_chunk<=0;digest<=0;end
  else begin
   if(scan_enable)stimulus<={stimulus[31:0],scan_in};
   observed_capture<=observed;digest_chunk<=^observed_capture;digest<=digest^digest_chunk;
  end
 end
 assign signature=digest;
 s_tc8psk_chain dut(clk,resetn,stimulus[0],observed[0],stimulus[16:1],stimulus[32:17],observed[1],observed[3:2]);
endmodule
