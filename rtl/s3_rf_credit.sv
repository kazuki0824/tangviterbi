// Consumer retirement, not wire completion or producer issuance, returns RF
// credit. The host caps outstanding pages at THREE; two-bit Gray therefore
// has no four-page alias. Retire is sampled in the FPGA consumer's core domain.
// Outputs go to the two proposed control GPIOs; electrical/epoch setup remains
// part of the board control driver, not an automatic reset acknowledgement.
module s3_rf_credit(input wire clk,resetn,retire,output wire [1:0] gray);
 reg [1:0] count;
 always @(posedge clk or negedge resetn)
  if(!resetn)count<=0;else if(retire)count<=count+1'b1;
 assign gray=count^(count>>1);
endmodule
