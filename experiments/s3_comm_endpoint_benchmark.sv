// PIN/TIMING BENCHMARK ONLY: no RF demodulator or physical PSRAM.
// Two real SPI RX endpoints feed acknowledged write arbitration/reorder.
// Memory writes fold into a checksum and are acknowledged after one cycle;
// ordered page descriptors are immediately retired, not physically read.
// The IQ read RAM is filled with a synthetic data source, not real RF symbols.
module s3_comm_endpoint_benchmark #(parameter PINGPONG=0)(input wire clk,resetn,
 input wire spi2_sclk,spi2_cs_n,input wire [7:0] spi2_d,
 input wire spi3_sclk,spi3_cs_n,inout wire [3:0] spi3_d,
 output wire activity);
 wire spi2_clock,spi3_clock;
 BUFG spi2_global(.I(spi2_sclk),.O(spi2_clock));
 BUFG spi3_global(.I(spi3_sclk),.O(spi3_clock));
 wire [35:0] tok[0:1];wire [1:0] v,r,overflow;
 s3_spi_rx #(.LANES(8)) p2(spi2_clock,spi2_cs_n,clk,resetn,spi2_d,v[0],r[0],tok[0],overflow[0]);
 s3_spi_rx #(.LANES(4),.IGNORE_IQ_READ(1)) p3(spi3_clock,spi3_cs_n,clk,resetn,spi3_d,v[1],r[1],tok[1],overflow[1]);
 wire mv,mt,pv,store_fault;wire [13:0] ma;wire [31:0] md,po;wire [3:0] ps;
 reg av,at;reg [31:0] hash,lfsr;
 s3_rx_page_store store(clk,resetn,16'd1,v,r,tok[0],tok[1],|overflow,
  mv,1'b1,ma,md,mt,av,at,pv,po,ps,pv,store_fault);
 wire begin_ready,word_ready,iq_sent,iq_fault,oe;wire [1:0] iq_ready;
 wire [3:0] dq;reg [31:0] iq_offset;
 generate if(PINGPONG)begin:double_buffer
  s3_spi_iq_pingpong tx(clk,resetn,begin_ready,begin_ready,16'd1,iq_offset,
   1'b1,word_ready,lfsr,iq_ready,iq_sent,iq_fault,1'b0,
   spi3_clock,spi3_cs_n,spi3_d,dq,oe);
 end else begin:single_buffer
  assign iq_ready[1]=0;
  s3_spi_iq_tx tx(clk,resetn,begin_ready,begin_ready,16'd1,iq_offset,
   1'b1,word_ready,lfsr,iq_ready[0],iq_sent,iq_fault,1'b0,
   spi3_clock,spi3_cs_n,spi3_d,dq,oe);
 end endgenerate
 assign spi3_d=oe?dq:4'bzzzz;
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin av<=0;at<=0;hash<=0;lfsr<=32'h5938172d;iq_offset<=0;end
  else begin
   av<=mv;at<=mt;
   if(mv)hash<={hash[30:0],hash[31]}^md^{17'd0,mt,ma};
   lfsr<={lfsr[30:0],lfsr[31]^lfsr[21]^lfsr[1]^lfsr[0]};
   if(begin_ready)iq_offset<=iq_offset+4096;
  end
 end
 assign activity=^{hash,po,ps,iq_ready,iq_sent,iq_fault,store_fault};
endmodule
