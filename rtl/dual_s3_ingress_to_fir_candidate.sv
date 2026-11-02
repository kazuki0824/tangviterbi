// Actual ready/valid connection of T 32-KiB and S 16-KiB S3 transport,
// native I10/Q10 unpackers, and two folded 33-tap complex FIR arithmetic
// kernels. The next OFDM/satellite synchronization, resampling, FEC and TS
// connections do not exist here. All exposed FIR outputs are area-probe ports.
module dual_s3_ingress_to_fir_candidate(
 input wire clk,resetn,
 input wire [1:0]frontend_idle,frontend_locked,frontend_fault,
 input wire t_spi2_clk,t_spi2_cs_n,inout wire [7:0]t_spi2_d,
 input wire s_spi2_clk,s_spi2_cs_n,input wire [7:0]s_spi2_d,
 input wire s_spi3_clk,s_spi3_cs_n,inout wire [3:0]s_spi3_d,
 input wire [1:0]fir_ready,output wire [1:0]fir_valid,
 output wire signed[63:0]fir_i,fir_q,
 input wire [1:0]coeff_valid,output wire [1:0]coeff_ready,
 input wire [11:0]coeff_addr,input wire signed[31:0]coeff_value,
 output wire [1:0]stream_enable,fault,RF_last,
 output wire [63:0]RF_offset,output wire [31:0]epoch
);
 wire [1:0]iq_valid,iq_ready;
 wire [19:0]iq_i,iq_q;
 dual_s3_26pin_iq_ingress_candidate ingress(
  .clk(clk),.resetn(resetn),
  .frontend_idle(frontend_idle),.frontend_locked(frontend_locked),
  .frontend_fault(frontend_fault),
  .t_spi2_clk(t_spi2_clk),.t_spi2_cs_n(t_spi2_cs_n),.t_spi2_d(t_spi2_d),
  .s_spi2_clk(s_spi2_clk),.s_spi2_cs_n(s_spi2_cs_n),.s_spi2_d(s_spi2_d),
  .s_spi3_clk(s_spi3_clk),.s_spi3_cs_n(s_spi3_cs_n),.s_spi3_d(s_spi3_d),
  .iq_ready(iq_ready),.iq_valid(iq_valid),.iq_i(iq_i),.iq_q(iq_q),
  .stream_enable(stream_enable),.fault(fault),
  .RF_last(RF_last),.RF_offset(RF_offset),.epoch(epoch)
 );
 dual_isdb_complex_fir33 fir(
  .clk(clk),.resetn(resetn),
  .in_valid(iq_valid),.in_ready(iq_ready),
  .in_i(iq_i),.in_q(iq_q),
  .out_valid(fir_valid),.out_ready(fir_ready),
  .out_i(fir_i),.out_q(fir_q),
  .coeff_valid(coeff_valid),.coeff_ready(coeff_ready),
  .coeff_addr(coeff_addr),.coeff_value(coeff_value)
 );
endmodule
