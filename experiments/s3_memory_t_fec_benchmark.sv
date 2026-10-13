// T FEC plus the physical PSRAM/SPI path, before FFT/FIR/sync/demap.
// Independent synthetic FEC activity is retained; this is not a receiver.
module s3_memory_fec_benchmark(
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
 reg[31:0] checksum,lfsr;
 always @(posedge clk or negedge rst)
  if(!rst)begin checksum<=0;lfsr<=32'h1aceb00c;end
  else begin
   if(v)checksum<={checksum[30:0],checksum[31]}^data;
   lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
  end
 wire vit_ready,vit_valid,vit_bit,rs_ready,rs_valid,rs_fail;wire[7:0]rs_out;
 s3_viterbi_traceback vit(clk,rst,1'b1,vit_ready,lfsr[7:0],lfsr[15:8],vit_valid,vit_bit);
 rs204_188_compact rs(clk,rst,1'b1,rs_ready,lfsr[23:16],rs_valid,rs_out,rs_fail);
 assign activity=^{checksum,offset,last,init,fault,vit_ready,vit_valid,vit_bit,rs_ready,rs_valid,rs_out,rs_fail};
endmodule
