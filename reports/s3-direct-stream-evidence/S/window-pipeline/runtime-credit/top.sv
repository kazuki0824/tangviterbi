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
wire mr,mv,vr,vv,syready,syvalid,cr,rv,done,failed,fr,fv,ff;
 wire[35:0] costs;wire[3:0] b1,roots;wire[1:0] bits_out;wire[7:0] position;
 wire[127:0] syndromes;wire[63:0] magnitudes;
 s3_tc8psk_metric_folded metric(clk,rst,1'b1,mr,lfsr[15:0],lfsr[31:16],mv,vr,costs,b1);
 s3_tc8psk vit(clk,rst,mv,vr,costs,b1,vv,bits_out);
 s3_rs_syndrome syndrome(clk,rst,1'b1,syready,lfsr[23:16],syvalid,cr,syndromes);
 s3_rs_chien chien(clk,rst,syvalid,cr,{syndromes[71:8],8'd1},4'd8,
 rv,1'b1,position,done,1'b1,failed,roots);
 s3_rs_forney forney(clk,rst,syvalid,fr,{syndromes[71:8],8'd1},syndromes,
 roots,roots,lfsr,fv,1'b1,ff,magnitudes);
 assign activity=^{checksum,offset,last,fault,mr,mv,vv,bits_out,syready,syvalid,cr,rv,
 position,done,failed,roots,fr,fv,ff,magnitudes};
endmodule
