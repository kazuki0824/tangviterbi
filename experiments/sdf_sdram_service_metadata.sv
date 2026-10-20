// Integration boundary: outer FFT delay cache + six-client arbiter + controller.
// Background 0=T spill write, 1=T spill read, 2=T deinterleave, 3=S frame,
// 4=management. Port 1 is read-only and must retain its address until ready.
// Other clients must retain descriptors until ready. No PHY or
// background producer storage is included. Reset all clients together.
module sdf_sdram_service_metadata(
 input wire clk,resetn,sample_accept,output wire external_ready,
 input wire read_enable,input wire[11:0] read_address,output wire[31:0]read_data,
 input wire write_enable,input wire[11:0]write_address,input wire[31:0]write_data,
 input wire[4:0]bg_valid,output wire[4:0]bg_ready,input wire[4:0]bg_write,
 input wire[104:0]bg_address,input wire[1279:0]bg_data,input wire[159:0]bg_dqm,
 output wire[4:0]bg_rsp_valid,input wire[4:0]bg_rsp_ready,output wire[255:0]bg_rsp_data,
 output wire initialized,fault,output wire[2:0]sd_cmd,output wire[1:0]sd_bank,
 output wire[10:0]sd_address,output wire sd_cke,output wire[3:0]sd_dqm,
 output wire dq_oe,output wire[31:0]dq_out,input wire[31:0]dq_in
);
 reg read_port_fault;
 always @(posedge clk)begin
  if(!resetn)read_port_fault<=0;
  else if(bg_valid[1] && bg_write[1])read_port_fault<=1;
 end
 wire[4:0] safe_valid=bg_valid & {3'b111,!bg_write[1],1'b1};
 wire[4:0] safe_write={bg_write[4:2],1'b0,bg_write[0]};
 wire[1279:0] safe_data={bg_data[1279:512],256'd0,bg_data[255:0]};
 wire[159:0] safe_dqm={bg_dqm[159:64],32'd0,bg_dqm[31:0]};
 wire cv,cw,cf,qv,qr,qw,rv,rr,mf;wire[20:0]ca,qa;wire[255:0]cd,qd,rd;
 wire[5:0]cr,crv;wire[31:0]qm;
 sdf_delay_cache cache(clk,resetn,sample_accept,external_ready,
 read_enable,read_address,read_data,write_enable,write_address,write_data,
 cv,cr[5],cw,ca,cd,crv[5],rd,cf);
 sdram_client_arbiter_metadata arb(clk,resetn,{cv,safe_valid},cr,{cw,safe_write},
 {ca,bg_address},{cd,safe_data},{32'd0,safe_dqm},crv,{1'b1,bg_rsp_ready},
 bg_rsp_data,qv,qr,qw,qa,qd,qm,rv,rr,rd);
 dual_sdram_burst #(.INIT_CYCLES(30858),.REFRESH_CYCLES(1203),
 .TRP(4),.TRCD(4),.TRFC(12),.TWR(4),.TMRD(4)) controller(
 clk,resetn,qv,qr,qw,qa,qd,qm,rv,rr,rd,initialized,mf,
 sd_cmd,sd_bank,sd_address,sd_cke,sd_dqm,dq_oe,dq_out,dq_in);
 assign bg_ready=cr[4:0] & {3'b111,!bg_write[1],1'b1};assign bg_rsp_valid=crv[4:0];assign fault=cf|mf|read_port_fault;
endmodule
