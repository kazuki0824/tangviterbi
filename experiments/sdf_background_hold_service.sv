// Experimental alternative: five request slots added to the same service.
// This is not a claim that every producer needs an extra copy.
module sdf_sdram_service(
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
 wire[4:0] held_valid,held_ready,held_write,slot_fault;
 wire[104:0]held_address;
 wire[1279:0]held_data;
 wire[159:0]held_dqm;
 wire service_fault;
 genvar i;
 generate for(i=0;i<5;i=i+1)begin: request_holding
  sdram_request_slot #(.READ_ONLY(i==1)) slot(
   .clk(clk),.resetn(resetn),.in_valid(bg_valid[i]),.in_ready(bg_ready[i]),
   .in_write(bg_write[i]),.in_address(bg_address[i*21+:21]),
   .in_data(bg_data[i*256+:256]),.in_dqm(bg_dqm[i*32+:32]),
   .out_valid(held_valid[i]),.out_ready(held_ready[i]),.out_write(held_write[i]),
   .out_address(held_address[i*21+:21]),.out_data(held_data[i*256+:256]),
   .out_dqm(held_dqm[i*32+:32]),.fault(slot_fault[i]));
 end endgenerate
 sdf_sdram_service_unbuffered service(
  .clk(clk),.resetn(resetn),.sample_accept(sample_accept),.external_ready(external_ready),
  .read_enable(read_enable),.read_address(read_address),.read_data(read_data),
  .write_enable(write_enable),.write_address(write_address),.write_data(write_data),
  .bg_valid(held_valid),.bg_ready(held_ready),.bg_write(held_write),
  .bg_address(held_address),.bg_data(held_data),.bg_dqm(held_dqm),
  .bg_rsp_valid(bg_rsp_valid),.bg_rsp_ready(bg_rsp_ready),.bg_rsp_data(bg_rsp_data),
  .initialized(initialized),.fault(service_fault),.sd_cmd(sd_cmd),.sd_bank(sd_bank),
  .sd_address(sd_address),.sd_cke(sd_cke),.sd_dqm(sd_dqm),.dq_oe(dq_oe),
  .dq_out(dq_out),.dq_in(dq_in));
 assign fault=service_fault | (|slot_fault);
endmodule
