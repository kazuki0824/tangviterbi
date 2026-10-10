// Area experiment only: S transport in two on-chip pages, independent FEC.
// The FEC input is LFSR-driven; no RF demodulation or deadline is proved.
module s3_memory_bram2_fec_benchmark(
 input wire clk27,resetn,spi2_sclk,spi2_cs_n,inout wire [7:0] spi2_d,
 input wire lcd_wr,lcd_cs_n,lcd_dc,input wire [15:0] lcd_d,
 output wire activity
);
 wire clk,clk_ck,rst;
 s3_psram_clock clocking(clk27,resetn,clk,clk_ck,rst);
 wire v,last,fault;
 wire [31:0] data,offset;
 wire [19:0] retired_sequence;
 wire spi2_clock_global;
 s3_bram2_memory_bridge #(.PIPE_WINDOW(1),.SLOT_BITS(3),.FIXED_ARBITER(1)) bridge(clk,rst,16'd1,
  spi2_sclk,spi2_cs_n,spi2_d,lcd_wr,lcd_cs_n,lcd_dc,lcd_d,
  v,1'b1,data,last,offset,fault,retired_sequence,spi2_clock_global);
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
 wire [127:0] syndromes;wire synd_valid,chien_ready,done_valid;wire [3:0] roots;
 s3_rs_syndrome syndrome(clk,rst,1'b1,rs_ready,lfsr[23:16],synd_valid,chien_ready,syndromes);
 s3_rs_chien chien(clk,rst,synd_valid,chien_ready,{syndromes[71:8],8'd1},4'd8,
  rs_valid,1'b1,rs_out,done_valid,1'b1,rs_fail,roots);
 wire [7:0] status_data;wire status_oe,status_fault;
 s3_spi_page_status #(.WINDOW(8)) status(clk,rst,16'd1,retired_sequence,fault,
  spi2_clock_global,spi2_cs_n,spi2_d,status_data,status_oe,status_fault);
 assign spi2_d=status_oe?status_data:8'bz;
 wire correction_ready,correction_error,correction_in_ready;
 wire correction_valid,correction_last,correction_failed;wire [7:0] correction_data;
 s3_rs_correction correction(clk,rst,1'b1,correction_ready,syndromes[3:0],
  syndromes[63:0],syndromes[127:64],rs_fail,correction_error,
  1'b1,correction_in_ready,lfsr[31:24],correction_valid,1'b1,
  correction_data,correction_last,correction_failed);
 assign activity=^{status_fault,correction_ready,correction_error,correction_in_ready,correction_valid,correction_data,correction_last,correction_failed,checksum,offset,last,fault,lfsr[0],bits_out,vit_valid,rs_out,rs_valid,rs_fail,syndromes,synd_valid,done_valid,roots};
endmodule
