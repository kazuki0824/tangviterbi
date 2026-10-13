// Tang Nano 9K 27 MHz -> 90 MHz core and 90 MHz +90-degree memory CK launch.
// VCO=720 MHz, static configuration from Gowin UG286. Lock assertion is
// synchronized; reset/lock loss asserts reset asynchronously in both domains.
module s3_psram_clock(input wire clk27,resetn,output wire clk,clk_ck,ready);
 wire locked;
 rPLL #(.FCLKIN("27"),.IDIV_SEL(2),.FBDIV_SEL(9),.ODIV_SEL(8),
  .PSDA_SEL("0100"),.DUTYDA_SEL("1000"),.DEVICE("GW1N-9C")) pll(
  .CLKIN(clk27),.CLKFB(1'b0),.RESET(!resetn),.RESET_P(1'b0),
  .FBDSEL(6'd0),.IDSEL(6'd0),.ODSEL(6'd0),.DUTYDA(4'd0),.PSDA(4'd0),.FDLY(4'd0),
  .CLKOUT(clk),.CLKOUTP(clk_ck),.CLKOUTD(),.CLKOUTD3(),.LOCK(locked));
 (* async_reg="true" *) reg [2:0] release_reset;
 wire reset_locked=resetn&&locked;
 always @(posedge clk or negedge reset_locked)
  if(!reset_locked)release_reset<=0;else release_reset<={release_reset[1:0],1'b1};
 assign ready=release_reset[2];
endmodule
