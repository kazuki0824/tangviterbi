module top(input wire clk27,resetn,
 input wire spi2_sclk,spi2_cs_n,input wire[7:0]spi2_d,
 input wire spi3_sclk,spi3_cs_n,inout wire[3:0]spi3_d,output wire activity,
 output wire[2:0]RF_credit_gray,output wire[1:0]IQ_publish_gray);
 wire clk,unused,rst;s3_psram_clock clocks(clk27,resetn,clk,unused,rst);
 wire spi2_clock,spi3_clock;
 BUFG global2(.I(spi2_sclk),.O(spi2_clock));BUFG global3(.I(spi3_sclk),.O(spi3_clock));
 wire v,last,fault,fftv,fftl,en,ibr,iwr;wire[31:0]data,offset,fftd,ffto;wire[15:0]ep;
 reg[31:0]checksum,iqoff;reg[9:0]iqidx;reg loading;reg[63:0]lfsr;
 wire ib=1'b0;
 wire iw=1'b0;
 s3_spi_runtime_endpoint #(.IMAGE_ID(1)) bridge(clk,rst,1'b1,1'b1,1'b0,
 spi2_clock,spi2_cs_n,spi2_d,spi3_clock,spi3_cs_n,spi3_d,
 v,1'b1,data,offset,last,fftv,1'b1,fftd,ffto,fftl,
 ib,ibr,iqoff,iw,iwr,lfsr[31:0],en,fault,ep,RF_credit_gray,IQ_publish_gray);
 always @(posedge clk or negedge rst)
 if(!rst)begin checksum<=0;lfsr<=64'hc14fb4391aceb00c;iqoff<=0;iqidx<=0;loading<=0;end
 else begin
  if(v)checksum<={checksum[30:0],checksum[31]}^data;
  if(fftv)checksum<=checksum^fftd;
  lfsr<={lfsr[62:0],lfsr[63]^lfsr[62]^lfsr[60]^lfsr[59]};
  if(ib&&ibr)begin loading<=1;iqidx<=0;end
  if(iw&&iwr)begin iqidx<=iqidx+1'b1;if(iqidx==1023)begin loading<=0;iqoff<=iqoff+4096;end end
 end
wire mr,mv,vr,vv,rr,rv,rf;wire[35:0] costs;wire[3:0] b1;
 wire[1:0] bits_out;wire[7:0] rd;
 s3_tc8psk_metric_folded metric(clk,rst,1'b1,mr,lfsr[15:0],lfsr[31:16],mv,vr,costs,b1);
 s3_tc8psk vit(clk,rst,mv,vr,costs,b1,vv,bits_out);
 rs204_188_compact rs(clk,rst,1'b1,rr,lfsr[23:16],rv,rd,rf);
 assign activity=^{checksum,offset,last,fault,ffto,fftl,en,ep,mr,mv,vv,bits_out,rr,rv,rd,rf};
endmodule
