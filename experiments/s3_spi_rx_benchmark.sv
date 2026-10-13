// Placement probe for the two physical RX ports and their CDC/page guards.
// Data folds into checksums; this is NOT a receiver or a PSRAM controller.
module s3_spi_rx_benchmark(input wire clk,resetn,
 input wire spi2_sclk,spi2_cs_n,input wire [7:0] spi2_d,
 input wire spi3_sclk,spi3_cs_n,input wire [3:0] spi3_d,
 output wire activity);
 wire [35:0] tok[0:1]; wire [1:0] v,r,ov,start,dv,commit,fault,request;
 wire [1:0] stream[0:1];wire [31:0] offset[0:1],data[0:1];
 s3_spi_rx #(.LANES(8)) p2(spi2_sclk,spi2_cs_n,clk,resetn,spi2_d,v[0],r[0],tok[0],ov[0]);
 s3_spi_rx #(.LANES(4)) p3(spi3_sclk,spi3_cs_n,clk,resetn,spi3_d,v[1],r[1],tok[1],ov[1]);
 reg [31:0] hash[0:1];
 genvar i;generate for(i=0;i<2;i=i+1)begin:g
  s3_page_guard guard(clk,resetn,16'd1,v[i],r[i],tok[i],1'b1,start[i],stream[i],offset[i],dv[i],1'b1,data[i],commit[i],fault[i],request[i]);
  always @(posedge clk or negedge resetn)
   if(!resetn) hash[i]<=0;
   else if(start[i]) hash[i]<=hash[i]^offset[i]^{30'd0,stream[i]};
   else if(dv[i]) hash[i]<={hash[i][30:0],hash[i][31]}^data[i];
 end endgenerate
 assign activity=^{hash[0],hash[1],commit,ov,fault};
endmodule
