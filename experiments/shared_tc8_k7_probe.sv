// Same observer construction for both boundaries; unused baseline lanes may prune.
module shared_tc8_k7_probe #(parameter USE_TC8=1)(input wire clk,resetn,scan_enable,scan_in,output wire signature);
 reg[62:0]stimulus;wire[6:0]observed;
 reg[6:0]observed_capture;reg digest_chunk,digest;
 always @(posedge clk)begin
  if(!resetn)begin stimulus<=0;observed_capture<=0;digest_chunk<=0;digest<=0;end
  else begin
   if(scan_enable)stimulus<={stimulus[61:0],scan_in};
   observed_capture<=observed;digest_chunk<=^observed_capture;digest<=digest^digest_chunk;
  end
 end
 assign signature=digest;
 shared_tc8_k7_boundary #(.USE_TC8(USE_TC8)) dut(
 clk,resetn,stimulus[0],observed[0],stimulus[2:1],observed[3:2],stimulus[3],observed[1],
 stimulus[11:4],stimulus[19:12],stimulus[21:20],observed[4],observed[5],
 stimulus[22],stimulus[58:23],stimulus[62:59],observed[6]);
endmodule
