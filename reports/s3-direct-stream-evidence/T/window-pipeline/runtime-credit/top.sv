module top(input wire clk27,resetn,
 input wire spi2_sclk,spi2_cs_n,input wire[7:0] spi2_d,
 input wire spi3_sclk,spi3_cs_n,input wire[3:0] spi3_d,output wire activity,output wire[1:0] RF_credit_gray);
 wire clk,unused,rst; s3_psram_clock clocks(clk27,resetn,clk,unused,rst);
 wire spi2_clock,spi3_clock;
 BUFG global2(.I(spi2_sclk),.O(spi2_clock));BUFG global3(.I(spi3_sclk),.O(spi3_clock));
 wire v,last,fault;wire[31:0] data,offset;
 s3_spi_direct_bridge #(.WINDOW_PIPELINE(1)) bridge(clk,rst,16'd1,spi2_clock,spi2_cs_n,spi2_d,
 spi3_clock,spi3_cs_n,spi3_d,v,1'b1,data,last,offset,fault);
 reg[31:0] checksum;reg[63:0] lfsr;
 always @(posedge clk or negedge rst)
  if(!rst)begin checksum<=0;lfsr<=64'hc14fb4391aceb00c;end
  else begin
   if(v)checksum<={checksum[30:0],checksum[31]}^data;
   lfsr<={lfsr[62:0],lfsr[63]^lfsr[62]^lfsr[60]^lfsr[59]};
  end
 s3_rf_credit credit(clk,rst,v&&last,RF_credit_gray);
wire vr,vv,bit_out,rr,rv,rf;wire[7:0] rd;
 s3_viterbi_traceback vit(clk,rst,1'b1,vr,lfsr[7:0],lfsr[15:8],vv,bit_out);
 rs204_188_compact rs(clk,rst,1'b1,rr,lfsr[23:16],rv,rd,rf);
 assign activity=^{checksum,offset,last,fault,vr,vv,bit_out,rr,rv,rd,rf};
endmodule
