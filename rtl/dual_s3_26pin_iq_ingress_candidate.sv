// ② 26-pin T/S transport candidate connected to two genuine lossless
// native I10/Q10 unpackers. The missing ISDB-T/S demodulators and TS are
// NOT replaced by a fake model; I/Q samples are exported for area probing.
module dual_s3_26pin_iq_ingress_candidate(
 input wire clk,resetn,
 input wire [1:0] frontend_idle,frontend_locked,frontend_fault,
 input wire t_spi2_clk,t_spi2_cs_n,inout wire [7:0] t_spi2_d,
 input wire s_spi2_clk,s_spi2_cs_n,input wire [7:0] s_spi2_d,
 input wire s_spi3_clk,s_spi3_cs_n,inout wire [3:0] s_spi3_d,
 input wire [1:0] iq_ready,
 output wire [1:0] iq_valid,output wire [19:0] iq_i,iq_q,
 output wire [1:0] stream_enable,fault,RF_last,
 output wire [63:0] RF_offset,output wire [31:0] epoch
);
 wire [1:0]rf_valid,rf_ready;
 wire [63:0]rf_data;
 dual_s3_26pin_transport_candidate ingress(
  .clk(clk),.resetn(resetn),
  .frontend_idle(frontend_idle),.frontend_locked(frontend_locked),
  .frontend_fault(frontend_fault),
  .t_spi2_clk(t_spi2_clk),.t_spi2_cs_n(t_spi2_cs_n),.t_spi2_d(t_spi2_d),
  .s_spi2_clk(s_spi2_clk),.s_spi2_cs_n(s_spi2_cs_n),.s_spi2_d(s_spi2_d),
  .s_spi3_clk(s_spi3_clk),.s_spi3_cs_n(s_spi3_cs_n),.s_spi3_d(s_spi3_d),
  .RF_valid(rf_valid),.RF_ready(rf_ready),.RF_data(rf_data),
  .RF_offset(RF_offset),.RF_last(RF_last),
  .stream_enable(stream_enable),.fault(fault),.epoch(epoch)
 );
 genvar k;
 generate for(k=0;k<2;k=k+1)begin: iq
  wire active=resetn && stream_enable[k] && !fault[k];
  s3_iq10_unpack unpack(
   .clk(clk),.resetn(active),.in_valid(rf_valid[k]),.in_ready(rf_ready[k]),
   .in_data(rf_data[k*32+:32]),
   .out_valid(iq_valid[k]),.out_ready(iq_ready[k]),
   .out_i(iq_i[k*10+:10]),.out_q(iq_q[k*10+:10])
  );
 end endgenerate
endmodule
