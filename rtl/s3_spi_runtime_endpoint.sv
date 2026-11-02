// Connected RF/FFT/IQ/control transport. DSP/TS attach separately.
// Epoch reset clears RF/FFT slots, consumer credit and IQ publication together.
module s3_spi_runtime_endpoint #(
 parameter[7:0]IMAGE_ID=0,parameter[31:0]BUILD_TAG=1,parameter T_OCTAL_ONLY=1,parameter integer WRITE_BYTES=4096
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
 wire [15:0]rf_retired_pages;
 reg[31:0]iq_next_offset;reg[9:0]iq_fill_index;reg[1:0]iq_publications;
 wire streams_resetn=resetn&&epoch!=0&&!epoch_reset;
 wire[35:0]tok0,tok1,rawtok0,rawtok1;
 wire[1:0]tv,tr,rawtv,rawtr,overflow;
 wire[1:0]split_fault;
 s3_spi_rx #(.LANES(8),.FIFO_AW(7),.IGNORE_IQ_READ(1),.IGNORE_CONTROL(1),.WRITE_BYTES(WRITE_BYTES)) r0(
  spi2_clk,spi2_cs_n,clk,streams_resetn,spi2_d,rawtv[0],rawtr[0],rawtok0,overflow[0]);
 generate if(IMAGE_ID==0&&T_OCTAL_ONLY)begin:octal_only
  // Actual T scheduler writes RF/FFT only on Octal; Quad is IQ/status input.
  assign rawtv[1]=0;assign rawtok1=0;assign overflow[1]=0;
 end else begin:quad_write
  s3_spi_rx #(.LANES(4),.FIFO_AW(7),.IGNORE_IQ_READ(1),.IGNORE_CONTROL(1),.WRITE_BYTES(WRITE_BYTES)) r1(
   spi3_clk,spi3_cs_n,clk,streams_resetn,spi3_d,rawtv[1],rawtr[1],rawtok1,overflow[1]);
 end endgenerate
 generate if(WRITE_BYTES==4096) begin: plain
  assign tv=rawtv;
  assign rawtr=tr;
  assign tok0=rawtok0;assign tok1=rawtok1;
  assign split_fault=0;
 end else begin: bulk
  s3_bulk_page_split #(.WRITE_BYTES(WRITE_BYTES)) split0(
   .clk(clk),.resetn(streams_resetn),.epoch(epoch),
   .valid(rawtv[0]),.ready(rawtr[0]),.token(rawtok0),
   .out_valid(tv[0]),.out_ready(tr[0]),.out_token(tok0),.fault(split_fault[0])
  );
  if(IMAGE_ID==0 && T_OCTAL_ONLY) begin: unused_second
   assign tv[1]=0;assign rawtr[1]=0;assign tok1=0;assign split_fault[1]=0;
  end else begin: second
   s3_bulk_page_split #(.WRITE_BYTES(WRITE_BYTES)) split1(
    .clk(clk),.resetn(streams_resetn),.epoch(epoch),
    .valid(rawtv[1]),.ready(rawtr[1]),.token(rawtok1),
    .out_valid(tv[1]),.out_ready(tr[1]),.out_token(tok1),.fault(split_fault[1])
   );
  end
 end endgenerate
 s3_pooled_page_store #(.ALLOW_FFT(IMAGE_ID==0),.INPUT_PORTS(IMAGE_ID==0&&T_OCTAL_ONLY?1:2)) pool(clk,streams_resetn,epoch,tv,tr,tok0,tok1,(|overflow)||(|split_fault),
  RF_valid,RF_ready,RF_data,RF_offset,RF_last,FFT_valid,FFT_ready,FFT_data,FFT_offset,FFT_last,pool_idle,pool_fault);
 s3_rf_credit #(.BITS(3)) credit(clk,streams_resetn,RF_valid&&RF_ready&&RF_last,RF_credit_gray,rf_retired_pages);
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
 s3_spi_control #(.IMAGE_ID(IMAGE_ID),.BUILD_TAG(BUILD_TAG),.EXTENDED_CREDIT(1)) control(clk,resetn,
  frontend_idle&&pool_idle&&!iq_ready&&iq_begin_ready,frontend_locked,frontend_fault||pool_fault||iq_fault,
  iq_ready[iq_next_offset[12]],iq_next_offset,RF_credit_gray,epoch,epoch_reset,stream_enable,control_fault,
  spi3_clk,spi3_cs_n,spi3_d,ctrl_d,ctrl_oe,rf_retired_pages);
 assign IQ_publish_gray=iq_publications^(iq_publications>>1);
 assign spi3_d=ctrl_oe?ctrl_d:iq_oe?iq_d:4'bzzzz;
 assign IQ_begin_ready=stream_enable&&iq_begin_ready;assign IQ_word_ready=stream_enable&&iq_word_ready;
 assign fault=frontend_fault||pool_fault||iq_fault||control_fault||(|split_fault);
endmodule
