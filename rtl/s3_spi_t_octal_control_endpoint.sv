// Stage-2 physical T input/control candidate: ONE SPI2 Octal connector, 10 pins.
// D711 RF write and D71C/D71D/D71E control share CLK/CS/D[7:0].
// RF retirement credit is returned in status word3[7:5], not GPIO pins.
// This 4-KiB endpoint is a functional control/transport prototype only:
// no bulk 16/32-KiB receive, FIR/sync/FEC/TS, pin CST or 80-MHz STA.
module s3_spi_t_octal_control_endpoint #(parameter integer WRITE_BYTES=4096) (
 input wire clk,resetn,
 input wire frontend_idle,frontend_locked,frontend_fault,
 input wire spi2_clk,spi2_cs_n,inout wire [7:0] spi2_d,
 output wire RF_valid,input wire RF_ready,
 output wire [31:0] RF_data,RF_offset,output wire RF_last,
 output wire stream_enable,fault,output wire [15:0] epoch
);
 wire ctrl_oe,epoch_reset,control_fault,pool_fault,pool_idle;
 wire [7:0]ctrl_d;
 wire [2:0]credit_gray;
 wire streams_resetn=resetn && epoch!=0 && !epoch_reset;
 wire token_valid,token_ready,token_ready_unused,overflow,raw_valid,raw_last;
 wire [35:0] transport_token;
 wire transport_valid,transport_ready,split_fault;
 wire [35:0]token;
 wire [31:0]raw_data,raw_offset;
 wire ignored_fft_valid,ignored_fft_last;
 wire [31:0]ignored_fft_data,ignored_fft_offset;
 assign spi2_d=ctrl_oe?ctrl_d:8'bzzzzzzzz;
 s3_spi_control #(.IMAGE_ID(0),.BUILD_TAG(32'h20c2026),.LANES(8)) control (
  .clk(clk),.resetn(resetn),.streams_idle(frontend_idle && pool_idle),
  .locked(frontend_locked),.receiver_fault(frontend_fault || pool_fault),
  .iq_ready(1'b0),.iq_offset(32'd0),.rf_credit_gray(credit_gray),
  .epoch(epoch),.epoch_reset(epoch_reset),.stream_enable(stream_enable),
  .control_fault(control_fault),.spi_clk(spi2_clk),.cs_n(spi2_cs_n),
  .dq_in(spi2_d),.dq_out(ctrl_d),.dq_oe(ctrl_oe)
 );
 s3_spi_rx #(.LANES(8),.FIFO_AW(7),.IGNORE_IQ_READ(1),.IGNORE_CONTROL(1),.WRITE_BYTES(WRITE_BYTES)) receiver (
  .spi_clk(spi2_clk),.cs_n(spi2_cs_n),.clk(clk),.resetn(streams_resetn),
  .dq(spi2_d),.valid(transport_valid),.ready(transport_ready),.token(transport_token),.overflow(overflow)
 );
 generate if(WRITE_BYTES==4096) begin: standard_pages
   assign token_valid=transport_valid;
   assign transport_ready=token_ready;
   assign token=transport_token;
   assign split_fault=1'b0;
 end else begin: bulk_pages
   s3_bulk_page_split #(.WRITE_BYTES(WRITE_BYTES)) splitter(
     .clk(clk),.resetn(streams_resetn),.epoch(epoch),
     .valid(transport_valid),.ready(transport_ready),.token(transport_token),
     .out_valid(token_valid),.out_ready(token_ready),.out_token(token),
     .fault(split_fault)
   );
 end endgenerate
 s3_pooled_page_store #(.ALLOW_FFT(0),.INPUT_PORTS(1)) pool (
  .clk(clk),.resetn(streams_resetn),.epoch(epoch),
  .in_valid({1'b0,token_valid}),.in_ready({token_ready_unused,token_ready}),
  .token0(token),.token1(36'd0),.upstream_fault(overflow || split_fault),
  .RF_valid(raw_valid),.RF_ready(RF_ready && stream_enable && !fault),
  .RF_data(raw_data),.RF_offset(raw_offset),.RF_last(raw_last),
  .FFT_valid(ignored_fft_valid),.FFT_ready(1'b0),
  .FFT_data(ignored_fft_data),.FFT_offset(ignored_fft_offset),
  .FFT_last(ignored_fft_last),.idle(pool_idle),.fault(pool_fault)
 );
 assign fault=frontend_fault || pool_fault || control_fault || split_fault;
 assign RF_valid=raw_valid && stream_enable && !fault;
 assign RF_data=raw_data;
 assign RF_offset=raw_offset;
 assign RF_last=raw_last;
 s3_rf_credit #(.BITS(3)) credit (
  .clk(clk),.resetn(streams_resetn),.retire(RF_valid && RF_ready && RF_last),
  .gray(credit_gray)
 );
endmodule
