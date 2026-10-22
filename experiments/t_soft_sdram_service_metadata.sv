// Same-clock integration of the existing service and T soft reader.
// External background lanes map to service clients 0,2,3,4. The reader owns
// client 1; FFT cache owns client 5. Other producer holding and PHY are absent.
module t_soft_sdram_service_metadata(
 input wire clk,resetn,sample_accept,output wire external_ready,
 input wire read_enable,input wire[11:0]read_address,output wire[31:0]read_data,
 input wire write_enable,input wire[11:0]write_address,input wire[31:0]write_data,
 input wire[3:0]bg_valid,output wire[3:0]bg_ready,input wire[3:0]bg_write,
 input wire[83:0]bg_address,input wire[1023:0]bg_data,input wire[127:0]bg_dqm,
 output wire[3:0]bg_rsp_valid,input wire[3:0]bg_rsp_ready,output wire[255:0]bg_rsp_data,
 input wire commit_valid,output wire commit_ready,
 input wire[62:0]commit_addresses,input wire[47:0]commit_lengths,
 output wire[1:0]bank_live,output wire reuse_blocked,
 output wire soft_valid,input wire soft_ready,output wire[1:0]soft_context,
 output wire[7:0]soft_data,
 output wire initialized,fault,output wire[2:0]sd_cmd,output wire[1:0]sd_bank,
 output wire[10:0]sd_address,output wire sd_cke,output wire[3:0]sd_dqm,
 output wire dq_oe,output wire[31:0]dq_out,input wire[31:0]dq_in
);
 wire reader_valid,reader_rsp_ready,reader_fault,service_fault;
 wire[20:0]reader_address;
 wire[4:0]ready,response_valid;
 t_soft_reader_buffered reader(
 .clk(clk),.resetn(resetn),.commit_valid(commit_valid),.commit_ready(commit_ready),
 .commit_addresses(commit_addresses),.commit_lengths(commit_lengths),
 .bank_live(bank_live),.reuse_blocked(reuse_blocked),
 .req_valid(reader_valid),.req_ready(ready[1]),.req_address(reader_address),
 .rsp_valid(response_valid[1]),.rsp_ready(reader_rsp_ready),.rsp_data(bg_rsp_data),
 .soft_valid(soft_valid),.soft_ready(soft_ready),.soft_context(soft_context),
 .soft_data(soft_data),.fault(reader_fault));
 sdf_sdram_service_metadata service(
 .clk(clk),.resetn(resetn),.sample_accept(sample_accept),.external_ready(external_ready),
 .read_enable(read_enable),.read_address(read_address),.read_data(read_data),
 .write_enable(write_enable),.write_address(write_address),.write_data(write_data),
 .bg_valid({bg_valid[3:1],reader_valid,bg_valid[0]}),.bg_ready(ready),
 .bg_write({bg_write[3:1],1'b0,bg_write[0]}),
 .bg_address({bg_address[83:21],reader_address,bg_address[20:0]}),
 .bg_data({bg_data[1023:256],256'd0,bg_data[255:0]}),
 .bg_dqm({bg_dqm[127:32],32'd0,bg_dqm[31:0]}),
 .bg_rsp_valid(response_valid),.bg_rsp_ready({bg_rsp_ready[3:1],reader_rsp_ready,bg_rsp_ready[0]}),
 .bg_rsp_data(bg_rsp_data),.initialized(initialized),.fault(service_fault),
 .sd_cmd(sd_cmd),.sd_bank(sd_bank),.sd_address(sd_address),.sd_cke(sd_cke),
 .sd_dqm(sd_dqm),.dq_oe(dq_oe),.dq_out(dq_out),.dq_in(dq_in));
 assign bg_ready={ready[4:2],ready[0]};
 assign bg_rsp_valid={response_valid[4:2],response_valid[0]};
 assign fault=reader_fault|service_fault;
endmodule
