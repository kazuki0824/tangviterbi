// CAD-only scan stimulus and pipelined observation of the integrated block.
module shared_receiver_service_probe(input wire clk,resetn,scan_enable,scan_in,output wire signature);
 reg[1496:0]stimulus;
 wire[363:0]observed;reg[363:0]observed_capture;
 reg[11:0]digest_chunks;reg digest;
 genvar i;
 generate for(i=0;i<12;i=i+1)begin: chunk
  localparam START=i*32;
  localparam WIDTH=364-START<32 ? 364-START : 32;
  always @(posedge clk)begin
   if(!resetn)digest_chunks[i]<=0;
   else digest_chunks[i]<=^observed_capture[START+:WIDTH];
  end
 end endgenerate
 always @(posedge clk)begin
  if(!resetn)begin stimulus<=0;observed_capture<=0;digest<=0;end
  else begin
   if(scan_enable)stimulus<={stimulus[1495:0],scan_in};
   observed_capture<=observed;digest<=digest^(^digest_chunks);
  end
 end
 assign signature=digest;
 shared_receiver_service dut(.clk(clk),.resetn(resetn),
 .sample_accept(stimulus[0]),
 .read_enable(stimulus[1]),
 .read_address(stimulus[13:2]),
 .write_enable(stimulus[14]),
 .write_address(stimulus[26:15]),
 .write_data(stimulus[58:27]),
 .bg_valid(stimulus[62:59]),
 .bg_write(stimulus[66:63]),
 .bg_address(stimulus[150:67]),
 .bg_data(stimulus[1174:151]),
 .bg_dqm(stimulus[1302:1175]),
 .bg_rsp_ready(stimulus[1306:1303]),
 .dq_in(stimulus[1338:1307]),
 .commit_valid(stimulus[1339]),
 .commit_addresses(stimulus[1402:1340]),
 .commit_lengths(stimulus[1450:1403]),
 .rates(stimulus[1462:1451]),.s_tc8_mode(stimulus[1463]),
 .s_valid(stimulus[1464]),.s_data(stimulus[1496:1465]),.s_ready(observed[357]),
 .external_ready(observed[0]),
 .read_data(observed[32:1]),
 .bg_ready(observed[36:33]),
 .bg_rsp_valid(observed[40:37]),
 .bg_rsp_data(observed[296:41]),
 .initialized(observed[297]),
 .fault(observed[298]),
 .sd_cmd(observed[301:299]),
 .sd_bank(observed[303:302]),
 .sd_address(observed[314:304]),
 .sd_cke(observed[315]),
 .sd_dqm(observed[319:316]),
 .dq_oe(observed[320]),
 .dq_out(observed[352:321]),
 .commit_ready(observed[353]),
 .bank_live(observed[355:354]),
 .reuse_blocked(observed[356]),
 .out_valid(observed[358]),.out_bit(observed[359]),.out_b1(observed[360]),
 .out_tc8(observed[361]),.out_context(observed[363:362]));
endmodule
