// CAD-only scan stimulus/signature wrapper. Not a receiver or SDRAM PHY.
// All service input bits are independent scan positions, all outputs observable.
module sdf_sdram_service_probe(input wire clk,resetn,scan_enable,scan_in,
 output wire signature);
 reg [1650:0] stimulus;
 wire [354:0] observed;
 // Capture service outputs before reducing them. Service timing ends at these
 // registers, rather than traversing the full 355-bit signature XOR tree.
 reg [354:0] observed_capture;
 reg [11:0] digest_chunks;
 reg digest;
 genvar group_index;
 generate for(group_index=0;group_index<12;group_index=group_index+1)begin: chunk
  localparam START=group_index*32;
  localparam WIDTH=(355-START<32) ? 355-START : 32;
  always @(posedge clk)begin
   if(!resetn)digest_chunks[group_index]<=0;
   else digest_chunks[group_index]<=^observed_capture[START+:WIDTH];
  end
 end endgenerate
 always @(posedge clk)begin
  if(!resetn)begin stimulus<=0;observed_capture<=0;digest<=0;end
  else begin
   if(scan_enable)stimulus<={stimulus[1649:0],scan_in};
   observed_capture<=observed;
   digest<=digest ^ (^digest_chunks);
  end
 end
 assign signature=digest;
 sdf_sdram_service dut(
 .clk(clk),.resetn(resetn),.sample_accept(stimulus[0]),.external_ready(observed[0]),
 .read_enable(stimulus[1]),.read_address(stimulus[13:2]),.read_data(observed[32:1]),
 .write_enable(stimulus[14]),.write_address(stimulus[26:15]),.write_data(stimulus[58:27]),
 .bg_valid(stimulus[63:59]),.bg_ready(observed[37:33]),.bg_write(stimulus[68:64]),
 .bg_address(stimulus[173:69]),.bg_data(stimulus[1453:174]),.bg_dqm(stimulus[1613:1454]),
 .bg_rsp_valid(observed[42:38]),.bg_rsp_ready(stimulus[1618:1614]),.bg_rsp_data(observed[298:43]),
 .initialized(observed[299]),.fault(observed[300]),.sd_cmd(observed[303:301]),
 .sd_bank(observed[305:304]),.sd_address(observed[316:306]),.sd_cke(observed[317]),
 .sd_dqm(observed[321:318]),.dq_oe(observed[322]),.dq_out(observed[354:323]),
 .dq_in(stimulus[1650:1619]));
endmodule
