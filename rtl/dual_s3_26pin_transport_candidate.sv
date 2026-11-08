// Scenario 2 candidate: T 10 physical SPI2 Octal pins, S 16 physical
// SPI2 Octal plus SPI3 Quad pins (26 transport GPIOs total).
// T status and credit share its SPI2 bus; S status and credit share SPI3.
// Two TS 3-pin outputs plus two event pins reserve eight more connectors;
// they are NOT implemented in this partial ingress module.
// No RF demod, TS sink, bulk 16/32KiB handling or external IO timing.
module dual_s3_26pin_transport_candidate (
 input wire clk,resetn,
 input wire [1:0] frontend_idle,frontend_locked,frontend_fault,
 input wire t_spi2_clk,t_spi2_cs_n,inout wire [7:0] t_spi2_d,
 input wire s_spi2_clk,s_spi2_cs_n,input wire [7:0] s_spi2_d,
 input wire s_spi3_clk,s_spi3_cs_n,inout wire [3:0] s_spi3_d,
 output wire [1:0] RF_valid,input wire [1:0] RF_ready,
 output wire [63:0] RF_data,RF_offset,output wire [1:0] RF_last,
 output wire [1:0] stream_enable,fault,output wire [31:0] epoch
);
 s3_spi_t_octal_control_endpoint #(.WRITE_BYTES(32768)) t (
  .clk(clk),.resetn(resetn),
  .frontend_idle(frontend_idle[0]),.frontend_locked(frontend_locked[0]),
  .frontend_fault(frontend_fault[0]),
  .spi2_clk(t_spi2_clk),.spi2_cs_n(t_spi2_cs_n),.spi2_d(t_spi2_d),
  .RF_valid(RF_valid[0]),.RF_ready(RF_ready[0]),
  .RF_data(RF_data[31:0]),.RF_offset(RF_offset[31:0]),
  .RF_last(RF_last[0]),.stream_enable(stream_enable[0]),
  .fault(fault[0]),.epoch(epoch[15:0])
 );
 wire s_unused_fft_valid,s_unused_fft_last,s_unused_iq_begin_ready;
 wire s_unused_iq_word_ready;
 wire [31:0]s_unused_fft_data,s_unused_fft_offset;
 wire [2:0]s_status_credit;
 wire [1:0]s_unused_iq_publication;
 s3_spi_runtime_endpoint #(.IMAGE_ID(1),.T_OCTAL_ONLY(0),.WRITE_BYTES(16384)) s (
  .clk(clk),.resetn(resetn),
  .frontend_idle(frontend_idle[1]),.frontend_locked(frontend_locked[1]),
  .frontend_fault(frontend_fault[1]),
  .spi2_clk(s_spi2_clk),.spi2_cs_n(s_spi2_cs_n),.spi2_d(s_spi2_d),
  .spi3_clk(s_spi3_clk),.spi3_cs_n(s_spi3_cs_n),.spi3_d(s_spi3_d),
  .RF_valid(RF_valid[1]),.RF_ready(RF_ready[1]),
  .RF_data(RF_data[63:32]),.RF_offset(RF_offset[63:32]),
  .RF_last(RF_last[1]),.FFT_valid(s_unused_fft_valid),.FFT_ready(1'b0),
  .FFT_data(s_unused_fft_data),.FFT_offset(s_unused_fft_offset),
  .FFT_last(s_unused_fft_last),
  .IQ_begin(1'b0),.IQ_begin_ready(s_unused_iq_begin_ready),
  .IQ_begin_offset(32'd0),.IQ_word_valid(1'b0),
  .IQ_word_ready(s_unused_iq_word_ready),.IQ_word_data(32'd0),
  .stream_enable(stream_enable[1]),.fault(fault[1]),
  .epoch(epoch[31:16]),.RF_credit_gray(s_status_credit),
  .IQ_publish_gray(s_unused_iq_publication)
 );
endmodule
