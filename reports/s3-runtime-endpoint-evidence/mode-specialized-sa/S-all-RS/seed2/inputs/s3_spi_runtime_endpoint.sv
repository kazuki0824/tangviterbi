// Connected RF/FFT/IQ/control transport. DSP/TS attach separately.
// Epoch reset clears RF/FFT slots, consumer credit and IQ publication together.
module s3_spi_runtime_endpoint #(
 parameter[7:0]IMAGE_ID=0,parameter[31:0]BUILD_TAG=1,parameter T_OCTAL_ONLY=1
)(
 input wire clk,resetn,input wire frontend_idle,frontend_locked,frontend_fault,
 input wire spi2_clk,spi2_cs_n,input wire[7:0]spi2_d,
 input wire spi3_clk,spi3_cs_n,inout wire[3:0]spi3_d,
 output wire RF_valid,input wire RF_ready,output wire[31:0]RF_data,RF_offset,output wire RF_last,
 output wire FFT_valid,input wire FFT_ready,output wire[31:0]FFT_data,FFT_offset,output wire FFT_last,
 input wire IQ_begin,output wire IQ_begin_ready,input wire[31:0]IQ_begin_offset,
 input wire IQ_word_valid,output wire IQ_word_ready,input wire[31:0]IQ_word_data,
 output wire stream_enable,fault,output wire[15:0]epoch,output wire[2:0]RF_credit_gray,output wire[1:0]IQ_publish_gray
);
 wire epoch_reset,control_fault,pool_fault,iq_fault,pool_idle;
 wire[3:0]ctrl_d,iq_d;wire ctrl_oe,iq_oe;
 wire[1:0]iq_ready;wire iq_sent,iq_begin_ready,iq_word_ready;
 reg[31:0]iq_next_offset;reg[9:0]iq_fill_index;reg[1:0]iq_publications;
 wire streams_resetn=resetn&&epoch!=0&&!epoch_reset;
 wire[35:0]tok0,tok1;wire[1:0]tv,tr,overflow;
 s3_spi_rx #(.LANES(8),.FIFO_AW(7),.IGNORE_IQ_READ(1),.IGNORE_CONTROL(1)) r0(
  spi2_clk,spi2_cs_n,clk,streams_resetn,spi2_d,tv[0],tr[0],tok0,overflow[0]);
 generate if(IMAGE_ID==0&&T_OCTAL_ONLY)begin:octal_only
  // Actual T scheduler writes RF/FFT only on Octal; Quad is IQ/status input.
  assign tv[1]=0;assign tok1=0;assign overflow[1]=0;
 end else begin:quad_write
  s3_spi_rx #(.LANES(4),.FIFO_AW(7),.IGNORE_IQ_READ(1),.IGNORE_CONTROL(1)) r1(
   spi3_clk,spi3_cs_n,clk,streams_resetn,spi3_d,tv[1],tr[1],tok1,overflow[1]);
 end endgenerate
 s3_pooled_page_store #(.ALLOW_FFT(IMAGE_ID==0),.INPUT_PORTS(IMAGE_ID==0&&T_OCTAL_ONLY?1:2)) pool(clk,streams_resetn,epoch,tv,tr,tok0,tok1,|overflow,
  RF_valid,RF_ready,RF_data,RF_offset,RF_last,FFT_valid,FFT_ready,FFT_data,FFT_offset,FFT_last,pool_idle,pool_fault);
 s3_rf_credit #(.BITS(3)) credit(clk,streams_resetn,RF_valid&&RF_ready&&RF_last,RF_credit_gray);
 s3_spi_iq_pingpong iq(clk,streams_resetn,IQ_begin&&stream_enable,iq_begin_ready,epoch,IQ_begin_offset,
  IQ_word_valid&&stream_enable,iq_word_ready,IQ_word_data,iq_ready,iq_sent,iq_fault,frontend_fault,
  spi3_clk,spi3_cs_n,spi3_d,iq_d,iq_oe);
 always @(posedge clk or negedge streams_resetn)begin
  if(!streams_resetn)begin iq_next_offset<=0;iq_fill_index<=0;iq_publications<=0;end
  else begin
   if(iq_sent)iq_next_offset<=iq_next_offset+4096;
   if(IQ_begin&&IQ_begin_ready)iq_fill_index<=0;
   if(IQ_word_valid&&IQ_word_ready)begin iq_fill_index<=iq_fill_index+1'b1;if(iq_fill_index==1023)iq_publications<=iq_publications+1'b1;end
  end
 end
 s3_spi_control #(.IMAGE_ID(IMAGE_ID),.BUILD_TAG(BUILD_TAG)) control(clk,resetn,
  frontend_idle&&pool_idle&&!iq_ready&&iq_begin_ready,frontend_locked,frontend_fault||pool_fault||iq_fault,
  iq_ready[iq_next_offset[12]],iq_next_offset,epoch,epoch_reset,stream_enable,control_fault,
  spi3_clk,spi3_cs_n,spi3_d,ctrl_d,ctrl_oe);
 assign IQ_publish_gray=iq_publications^(iq_publications>>1);
 assign spi3_d=ctrl_oe?ctrl_d:iq_oe?iq_d:4'bzzzz;
 assign IQ_begin_ready=stream_enable&&iq_begin_ready;assign IQ_word_ready=stream_enable&&iq_word_ready;
 assign fault=frontend_fault||pool_fault||iq_fault||control_fault;
endmodule
