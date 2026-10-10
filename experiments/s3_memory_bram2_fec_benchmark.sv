// Area experiment only: S transport in two on-chip pages, independent FEC.
// The FEC input is LFSR-driven; no RF demodulation or deadline is proved.
module s3_memory_bram2_fec_benchmark(
 input wire clk27,resetn,spi2_sclk,spi2_cs_n,input wire [7:0] spi2_d,
 input wire lcd_wr,lcd_cs_n,lcd_dc,input wire [15:0] lcd_d,
 output wire activity
);
 wire clk,clk_ck,rst;
 s3_psram_clock clocking(clk27,resetn,clk,clk_ck,rst);
 wire v,last,fault;
 wire [31:0] data,offset;
 s3_bram2_memory_bridge bridge(clk,rst,16'd1,
  spi2_sclk,spi2_cs_n,spi2_d,lcd_wr,lcd_cs_n,lcd_dc,lcd_d,
  v,1'b1,data,last,offset,fault);
 reg [31:0] checksum;
 always @(posedge clk or negedge rst)
  if(!rst)checksum<=0;else if(v)checksum<={checksum[30:0],checksum[31]}^data;
 reg [63:0] lfsr;
 wire metric_ready,mv,vit_ready,vit_valid,rs_ready,rs_valid,rs_fail;
 wire [35:0] costs;
 wire [3:0] b1;
 wire [1:0] bits_out;
 wire [7:0] rs_out;
 always @(posedge clk or negedge rst)
  if(!rst)lfsr<=64'hc14fb4391aceb00c;
  else if(metric_ready)lfsr<={lfsr[62:0],lfsr[63]^lfsr[62]^lfsr[60]^lfsr[59]};
 s3_tc8psk_metric_folded metric(clk,rst,1'b1,metric_ready,lfsr[15:0],lfsr[31:16],mv,vit_ready,costs,b1);
 s3_tc8psk vit(clk,rst,mv,vit_ready,costs,b1,vit_valid,bits_out);
 rs204_188_compact rs(clk,rst,rs_ready,rs_ready,lfsr[23:16],rs_valid,rs_out,rs_fail);
 assign activity=^{checksum,offset,last,fault,lfsr[0],bits_out,vit_valid,rs_out,rs_valid,rs_fail};
endmodule
