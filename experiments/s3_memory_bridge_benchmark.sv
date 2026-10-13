// Physical-pin transport benchmark with actual PSRAM datapath, PLL and page
// reads. Checksum sink retains the complete data path but is not a demodulator.
module s3_memory_bridge_benchmark(
 input wire clk27,resetn,input wire spi2_sclk,spi2_cs_n,input wire [7:0] spi2_d,
 input wire spi3_sclk,spi3_cs_n,input wire [3:0] spi3_d,output wire activity,
 output wire [1:0] O_psram_ck,O_psram_ck_n,O_psram_cs_n,O_psram_reset_n,
 inout wire [15:0] IO_psram_dq,inout wire [1:0] IO_psram_rwds
);
 wire clk,clk_ck,rst;
 s3_psram_clock clocking(clk27,resetn,clk,clk_ck,rst);
 wire v,last,init,fault;wire[31:0] data,offset;
 s3_spi_memory_bridge bridge(clk,clk_ck,rst,16'd1,
  spi2_sclk,spi2_cs_n,spi2_d,spi3_sclk,spi3_cs_n,spi3_d,
  v,1'b1,data,last,offset,init,fault,
  O_psram_ck,O_psram_ck_n,O_psram_cs_n,O_psram_reset_n,IO_psram_dq,IO_psram_rwds);
 reg[31:0] checksum;
 always @(posedge clk or negedge rst)
  if(!rst)checksum<=0;else if(v)checksum<={checksum[30:0],checksum[31]}^data;
 assign activity=^{checksum,offset,last,init,fault};
endmodule
