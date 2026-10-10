// Edge models for the subset instantiated by s3_psram_phy, per UG289
// 4.2.1/4.3.1. No analog timing, metastability or device setup/hold model.
module ODDR(input CLK,D0,D1,TX,output reg Q0,Q1);
 reg second;parameter TXCLK_POL=0,INIT=0;
 initial begin Q0=INIT;Q1=1;second=0;end
 always @(posedge CLK)begin Q0<=D0;second<=D1;if(TXCLK_POL==0)Q1<=TX;end
 always @(negedge CLK)begin Q0<=second;if(TXCLK_POL==1)Q1<=TX;end
endmodule
module IDDR(input D,CLK,output reg Q0,Q1);
 parameter Q0_INIT=0,Q1_INIT=0;
 reg first,second;
 initial begin Q0=Q0_INIT;Q1=Q1_INIT;first=Q0_INIT;second=Q1_INIT;end
 always @(posedge CLK)begin first<=D;Q0<=first;Q1<=second;end
 always @(negedge CLK)second<=D;
endmodule
