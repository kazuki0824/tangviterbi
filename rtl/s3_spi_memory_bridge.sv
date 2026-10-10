// Executable RF transport subsystem: two SPI inputs, ordered 64-KiB page
// ring, burst coalescing, physical DDR PSRAM and a backpressured word output.
// Output data remains native packed I10/Q10. No decimation/requantization.
// This is not the RF demodulator, and FFT/IQ streams are not routed here.
module s3_spi_memory_bridge(
 input wire clk,clk_ck,resetn,input wire [15:0] epoch,
 input wire spi2_sclk,spi2_cs_n,input wire [7:0] spi2_d,
 input wire spi3_sclk,spi3_cs_n,input wire [3:0] spi3_d,
 output wire out_valid,input wire out_ready,output wire [31:0] out_data,
 output wire out_last,output wire [31:0] out_offset,
 output wire initialized,fault,
 output wire [1:0] O_psram_ck,O_psram_ck_n,O_psram_cs_n,O_psram_reset_n,
 inout wire [15:0] IO_psram_dq,inout wire [1:0] IO_psram_rwds
);
 wire spi2_clock,spi3_clock;
 BUFG spi2_global(.I(spi2_sclk),.O(spi2_clock));
 BUFG spi3_global(.I(spi3_sclk),.O(spi3_clock));
 wire [35:0] tok[0:1];wire [1:0] v,r,overflow;
 // DDR completion plus 64 tagged acks may cross the next SPI page header.
 // 128 tokens absorb that bounded gap without adding another BSRAM block.
 s3_spi_rx #(.LANES(8),.FIFO_AW(7)) p2(spi2_clock,spi2_cs_n,clk,resetn,spi2_d,v[0],r[0],tok[0],overflow[0]);
 s3_spi_rx #(.LANES(4),.FIFO_AW(7)) p3(spi3_clock,spi3_cs_n,clk,resetn,spi3_d,v[1],r[1],tok[1],overflow[1]);
 wire mv,mr,mt,av,at,pv,retire,sf,rf,qf,bf,pf;
 wire [13:0] ma;wire [31:0] md,po;wire [3:0] ps;
 wire rr,rready,rvalid,rtake,rlast;wire [20:0] ra;wire [31:0] rdata;
 wire cv,cr,cw,wv,wr,rv,done,pr,pc,pk,pd,pw,re;
 wire [20:0] ca;wire [31:0] wd,rd;wire [15:0] tf,ts,x0,x1;wire [1:0] xv;
 reg stopped;
 wire reader_valid;
 reg write_pending,write_tag;
 reg [13:0] write_address;
 reg [31:0] write_data;
 wire queue_ready;
 assign mr=!write_pending&&!stopped;
 // Cut guard/port arbitration -> address check/RAM-enable timing. One word
 // per two 99-MHz cycles still exceeds 30 Mword/s aggregate wire payload.
 always @(posedge clk or negedge resetn)begin
  if(!resetn)begin write_pending<=0;write_tag<=0;write_address<=0;write_data<=0;end
  else if(!stopped)begin
   if(mv&&mr)begin write_pending<=1;write_tag<=mt;write_address<=ma;write_data<=md;end
   if(write_pending&&queue_ready)write_pending<=0;
  end
 end
 assign fault=sf||rf||qf||bf||pf||(|overflow);
 assign out_valid=reader_valid&&!fault;
 // Each component's fault output includes its upstream input. Feeding those
 // outputs around a combinational ring is invalid. A sticky registered fanout
 // stops every component; public output validity is masked immediately.
 always @(posedge clk or negedge resetn)
  if(!resetn)stopped<=0;else if(fault)stopped<=1;
 s3_rx_page_store store(clk,resetn,epoch,v,r,tok[0],tok[1],stopped||(|overflow),
  mv,mr,ma,md,mt,av,at,pv,po,ps,retire,sf);
 s3_psram_page_reader reader(clk,resetn,stopped,pv,ps,po,retire,
  rr,rready,ra,rvalid,rtake,rdata,rlast,reader_valid,out_ready&&!fault,out_data,out_last,out_offset,rf);
 s3_psram_queue queue(clk,resetn,stopped,write_pending,queue_ready,write_tag,{7'd0,write_address},write_data,av,at,
  rr,rready,ra,rvalid,rtake,rdata,rlast,cv,cr,cw,ca,wv,wr,wd,rv,rd,done,bf,qf);
 s3_psram_burst controller(clk,resetn,stopped,cv,cw,ca,cr,wv,wd,wr,rv,rd,done,initialized,bf,
  pr,pc,pk,pd,pw,tf,ts,re,xv,x0,x1,pf);
 s3_psram_phy phy(clk,clk_ck,resetn,pr,pc,pk,pd,pw,tf,ts,re,xv,x0,x1,pf,
  O_psram_ck,O_psram_ck_n,O_psram_cs_n,O_psram_reset_n,IO_psram_dq,IO_psram_rwds);
endmodule
