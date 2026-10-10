// Partial co-placement with RS BM/Omega/Forney assigned to the host.
// RPC queues, codeword buffers, correction writes and TS framing are absent.
// No RF demodulator, interleaver or TS chain connects these workloads.
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
 reg[31:0] checksum;
 always @(posedge clk or negedge rst)
  if(!rst)checksum<=0;else if(v)checksum<={checksum[30:0],checksum[31]}^data;
 reg [63:0] lfsr;
 wire metric_ready,mv,vit_ready,vit_valid,rs_ready,rs_valid,rs_fail;
 wire [35:0] costs;wire [3:0] b1;wire [1:0] bits_out;wire [7:0] rs_out;
 always @(posedge clk or negedge rst)
  if(!rst)lfsr<=64'hc14fb4391aceb00c;
  else if(metric_ready)lfsr<={lfsr[62:0],lfsr[63]^lfsr[62]^lfsr[60]^lfsr[59]};
 s3_tc8psk_metric metric(clk,rst,1'b1,metric_ready,lfsr[15:0],lfsr[31:16],mv,vit_ready,costs,b1);
 s3_tc8psk vit(clk,rst,mv,vit_ready,costs,b1,vit_valid,bits_out);
 wire[127:0] syndromes;wire synd_valid,chien_ready,done_valid;wire[3:0] roots;
 s3_rs_syndrome syndrome(clk,rst,1'b1,rs_ready,lfsr[23:16],synd_valid,chien_ready,syndromes);
 // Synthetic locator input only. No CPU solver/RPC is emulated by this top.
 s3_rs_chien chien(clk,rst,synd_valid,chien_ready,{syndromes[71:8],8'd1},4'd8,
  rs_valid,1'b1,rs_out,done_valid,1'b1,rs_fail,roots);
 assign activity=^{checksum,offset,last,init,fault,lfsr[0],bits_out,vit_valid,rs_out,rs_valid,rs_fail,syndromes,synd_valid,done_valid,roots};
endmodule
