// CAD-only co-residency probe of three real but DISCONNECTED subassemblies:
// (1) T/S 26-pin SPI2/3 -> lossless I10/Q10 -> 33tap complex FIR,
// (2) separately scan-driven FFT/SDRAM/K7 fixture,
// (3) independently driven RS(204,188) -> T/S serial TS.
//
// This is a resource interference screening experiment, NOT a receiver top.
// The scan/RS stimuli are not valid operational pins. T/S FIR does not feed
// FFT; K7 does not feed RS. No conclusion about complete receiver operation,
// physical pin fit, or all required modes is permitted from this source.
module stage2_cocurrent_selected_subassemblies_area_top(
 input wire clk,resetn,
 input wire [1:0]frontend_idle,frontend_locked,frontend_fault,
 input wire t_spi2_clk,t_spi2_cs_n,inout wire [7:0]t_spi2_d,
 input wire s_spi2_clk,s_spi2_cs_n,input wire [7:0]s_spi2_d,
 input wire s_spi3_clk,s_spi3_cs_n,inout wire [3:0]s_spi3_d,
 input wire [1:0]fir_ready,output wire [1:0]fir_valid,
 output wire signed [63:0]fir_i,fir_q,
 input wire [1:0]coeff_valid,output wire [1:0]coeff_ready,
 input wire [11:0]coeff_addr,input wire signed[31:0]coeff_value,
 output wire [1:0]stream_enable,ingress_fault,RF_last,
 output wire [63:0]RF_offset,output wire [31:0]epoch,
 input wire scan_enable,scan_in,output wire fft_k7_signature,
 input wire [1:0]rs_input_valid,output wire [1:0]rs_input_ready,
 input wire [15:0]rs_input_byte,
 output wire [1:0]ts_clk,ts_data,ts_valid,ts_fault
);
 dual_s3_ingress_to_fir_candidate candidate_input_fir(
  .clk(clk),.resetn(resetn),
  .frontend_idle(frontend_idle),.frontend_locked(frontend_locked),
  .frontend_fault(frontend_fault),
  .t_spi2_clk(t_spi2_clk),.t_spi2_cs_n(t_spi2_cs_n),.t_spi2_d(t_spi2_d),
  .s_spi2_clk(s_spi2_clk),.s_spi2_cs_n(s_spi2_cs_n),.s_spi2_d(s_spi2_d),
  .s_spi3_clk(s_spi3_clk),.s_spi3_cs_n(s_spi3_cs_n),.s_spi3_d(s_spi3_d),
  .fir_ready(fir_ready),.fir_valid(fir_valid),.fir_i(fir_i),.fir_q(fir_q),
  .coeff_valid(coeff_valid),.coeff_ready(coeff_ready),
  .coeff_addr(coeff_addr),.coeff_value(coeff_value),
  .stream_enable(stream_enable),.fault(ingress_fault),
  .RF_last(RF_last),.RF_offset(RF_offset),.epoch(epoch)
 );
 shared_receiver_fft_metadata_probe candidate_fft_k7_fixture(
  .clk(clk),.resetn(resetn),.scan_enable(scan_enable),
  .scan_in(scan_in),.signature(fft_k7_signature)
 );
 shared_rs2_dual_ts candidate_rs_ts(
  .clk(clk),.resetn(resetn),
  .input_valid(rs_input_valid),.input_ready(rs_input_ready),
  .input_byte(rs_input_byte),
  .ts_clk(ts_clk),.ts_data(ts_data),.ts_valid(ts_valid),.ts_fault(ts_fault)
 );
endmodule
