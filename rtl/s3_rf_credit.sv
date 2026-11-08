// Consumer retirement, not wire completion or producer issuance, returns RF
// credit. The host caps outstanding pages at THREE; two-bit Gray therefore
// has no four-page alias. Retire is sampled in the FPGA consumer's core domain.
// Gray preserves the legacy small-window credit signal. The separate 16-bit
// total allows distinguishing 8-page bulk retirement from an unchanged count.
module s3_rf_credit #(parameter BITS=2)(input wire clk,resetn,retire,output wire [BITS-1:0] gray,output wire [15:0]retired_pages);
 reg [15:0] count;
 always @(posedge clk or negedge resetn)
  if(!resetn)count<=0;else if(retire)count<=count+1'b1;
 assign gray=count[BITS-1:0]^(count[BITS-1:0]>>1);
 assign retired_pages=count;
endmodule
